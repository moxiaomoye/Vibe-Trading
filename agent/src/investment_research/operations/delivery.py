"""Daily-report notification planning and controlled transport dispatch."""

from __future__ import annotations

import hashlib
import json
import smtplib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Mapping, Protocol
from uuid import NAMESPACE_URL, uuid5

from ..intelligence.daily_research import DailyResearchMarkdownRenderer, DailyResearchReport
from ..repositories.sqlite_operations import SQLiteOperationsRepository
from .models import DeliveryChannel, OutboxMessage, OutboxStatus


class DeliveryTransport(Protocol):
    def send(self, message: OutboxMessage) -> None: ...


@dataclass(slots=True)
class DryRunTransport:
    """Consume shadow messages locally without performing a network request."""

    delivered_count: int = 0

    def send(self, message: OutboxMessage) -> None:
        self.delivered_count += 1


@dataclass(frozen=True, slots=True)
class FeishuWebhookTransport:
    webhook_url: str
    timeout_seconds: float = 10.0

    def send(self, message: OutboxMessage) -> None:
        if not self.webhook_url.startswith("https://open.feishu.cn/open-apis/bot/"):
            raise ValueError("Feishu webhook must use the official HTTPS bot endpoint")
        payload = json.dumps(
            {"msg_type": "text", "content": {"text": f"{message.subject}\n\n{message.body}"}},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        if result.get("code", result.get("StatusCode", 0)) != 0:
            raise RuntimeError(f"Feishu delivery rejected: {result.get('msg', result.get('StatusMessage', 'unknown'))}")


@dataclass(frozen=True, slots=True)
class SMTPTransport:
    host: str
    port: int
    username: str
    authorization_code: str
    recipient: str
    timeout_seconds: float = 15.0

    def send(self, message: OutboxMessage) -> None:
        if not all((self.host, self.username, self.authorization_code, self.recipient)):
            raise ValueError("SMTP delivery configuration is incomplete")
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = self.username
        email["To"] = self.recipient
        email.set_content(message.body)
        with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_seconds) as client:
            client.login(self.username, self.authorization_code)
            client.send_message(email)


@dataclass(frozen=True, slots=True)
class ServerChanTurboTransport:
    """Send one text notification through Server酱 Turbo."""

    send_key: str
    timeout_seconds: float = 10.0

    def send(self, message: OutboxMessage) -> None:
        key = self.send_key.strip()
        if not key.startswith("SCT") or not key.replace("_", "").isalnum():
            raise ValueError("ServerChan Turbo SendKey format is invalid")
        payload = urllib.parse.urlencode(
            {"title": message.subject[:128], "desp": message.body}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://sctapi.ftqq.com/{key}.send",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        if int(result.get("code", -1)) != 0:
            raise RuntimeError(
                f"ServerChan delivery rejected: {result.get('message', 'unknown')}"
            )


class DailyNotificationPlanner:
    def __init__(self, repository: SQLiteOperationsRepository):
        self.repository = repository
        self.renderer = DailyResearchMarkdownRenderer()

    def enqueue(self, report: DailyResearchReport, channels: tuple[DeliveryChannel, ...], now: datetime) -> int:
        body = self.renderer.render(report)
        subject = f"AI Investment Research Daily — {report.trade_date.isoformat()}"
        inserted = 0
        for channel in channels:
            idempotency_key = f"daily:{report.mode}:{report.trade_date.isoformat()}:{channel.value}"
            message = OutboxMessage(
                message_id=str(uuid5(NAMESPACE_URL, idempotency_key)),
                idempotency_key=idempotency_key,
                channel=channel,
                message_type="daily_research",
                subject=subject,
                body=body,
                source_id=report.report_id,
                status=OutboxStatus.PENDING,
                attempt_count=0,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
            inserted += self.repository.enqueue(message)
        return inserted


class OpportunityReportNotificationPlanner:
    """Render and enqueue the focused opportunity report without new storage."""

    def __init__(
        self,
        repository: SQLiteOperationsRepository,
        report_web_url: str = "http://127.0.0.1:8899/investment-research",
    ):
        self.repository = repository
        self.report_web_url = report_web_url

    def preview(self, report: Mapping[str, Any]) -> dict[str, str]:
        return _opportunity_preview(report, self.report_web_url)

    def _legacy_preview(self, report: Mapping[str, Any]) -> dict[str, str]:
        report_date = str(report.get("report_date") or "unknown")
        assets = report.get("assets")
        asset_rows = assets if isinstance(assets, list) else []
        action_candidates = [
            item for item in asset_rows
            if isinstance(item, dict) and item.get("action_level") == "action_candidate"
        ]
        prefix = "【高优先级机会提醒】" if action_candidates else "【每日投资研究简报】"
        subject = f"{prefix}{report_date}"
        lines = [
            subject,
            "",
            str(report.get("conclusion") or "今天没有形成可用研究结论。"),
            "",
            "市场状态",
        ]
        market = report.get("market")
        if isinstance(market, dict):
            lines.extend(
                [
                    f"- 状态：{market.get('regime') or '数据待补齐'}",
                    f"- 上证60日点位变化：{_display(market.get('shanghai_60d_point_change'), '点')}",
                    f"- 当日跌停：{_display(market.get('limit_down_count'), '家')}",
                ]
            )
        lines.extend(["", "研究标的"])
        for asset in asset_rows:
            if not isinstance(asset, dict):
                continue
            entry = asset.get("entry_framework")
            entry = entry if isinstance(entry, dict) else {}
            lines.extend(
                [
                    f"- {asset.get('name', asset.get('symbol', '未知标的'))}"
                    f"（{asset.get('symbol', '—')}）：{asset.get('action_label', '继续观察')}",
                    f"  收盘 {_display(asset.get('latest_close'))}；"
                    f"60日 {_display(asset.get('return_60d_pct'), '%')}",
                    f"  当前判断：{entry.get('summary') or '等待更多证据'}",
                    f"  下一复核：{entry.get('next_review_condition') or asset.get('next_condition') or '下一交易日'}",
                ]
            )
            counter = asset.get("counter_evidence")
            if isinstance(counter, list) and counter:
                lines.append(f"  最强反方：{counter[0]}")
        gaps = report.get("data_gaps")
        if isinstance(gaps, list) and gaps:
            lines.extend(["", f"数据缺口：{len(gaps)}项；页面内可查看完整明细。"])
        lines.extend(
            [
                "",
                "结论属于 Research Candidate / Action Candidate 研究状态，"
                "不是自动交易指令；下单、调度和真实资金操作均未启用。",
            ]
        )
        return {"subject": subject, "body": "\n".join(lines)}

    def enqueue(
        self,
        report: Mapping[str, Any],
        channels: tuple[DeliveryChannel, ...],
        now: datetime,
    ) -> tuple[str, ...]:
        preview = self.preview(report)
        report_date = str(report.get("report_date") or "")
        report_version = str(report.get("report_version") or "")
        if not report_date or not report_version:
            raise ValueError("opportunity report identity is incomplete")
        reason_fingerprint = _opportunity_reason_fingerprint(report)
        source_id = f"opportunity-event:{reason_fingerprint}"
        message_ids: list[str] = []
        for channel in channels:
            idempotency_key = (
                f"opportunity-daily:{report_date}:{reason_fingerprint}:{channel.value}"
            )
            message_id = str(uuid5(NAMESPACE_URL, idempotency_key))
            if self.repository.has_recent_source(
                channel,
                source_id,
                now - timedelta(hours=24),
            ):
                message_ids.append(message_id)
                continue
            if (
                channel == DeliveryChannel.SERVERCHAN
                and self.repository.count_channel_messages_since(
                    channel,
                    now - timedelta(hours=24),
                )
                >= 4
            ):
                message_ids.append(message_id)
                continue
            message_ids.append(message_id)
            self.repository.enqueue(
                OutboxMessage(
                    message_id=message_id,
                    idempotency_key=idempotency_key,
                    channel=channel,
                    message_type="opportunity_daily",
                    subject=preview["subject"],
                    body=preview["body"],
                    source_id=source_id,
                    status=OutboxStatus.PENDING,
                    attempt_count=0,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        return tuple(message_ids)


class OutboxDispatcher:
    def __init__(
        self,
        repository: SQLiteOperationsRepository,
        transports: dict[DeliveryChannel, DeliveryTransport],
        retry_delay: timedelta = timedelta(minutes=15),
        max_attempts: int = 5,
    ):
        self.repository = repository
        self.transports = transports
        self.retry_delay = retry_delay
        self.max_attempts = max_attempts

    def dispatch_due(self, now: datetime, limit: int = 20) -> tuple[int, int]:
        return self._dispatch(self.repository.claim_due(now, limit, self.max_attempts), now)

    def dispatch_message_ids(
        self,
        message_ids: tuple[str, ...],
        now: datetime,
    ) -> tuple[int, int]:
        """Dispatch only messages explicitly confirmed by the caller."""
        return self._dispatch(
            self.repository.claim_message_ids(message_ids, now, self.max_attempts),
            now,
        )

    def _dispatch(
        self,
        messages: tuple[OutboxMessage, ...],
        now: datetime,
    ) -> tuple[int, int]:
        delivered = failed = 0
        for message in messages:
            transport = self.transports.get(message.channel)
            try:
                if transport is None:
                    raise RuntimeError(f"no transport configured for {message.channel.value}")
                transport.send(message)
                self.repository.finish_message(message.message_id, True, now)
                delivered += 1
            except Exception as exc:  # transport boundary must preserve every failure for retry
                self.repository.finish_message(
                    message.message_id, False, now, str(exc), retry_at=now + self.retry_delay
                )
                failed += 1
        return delivered, failed


def _opportunity_preview(
    report: Mapping[str, Any],
    report_web_url: str,
) -> dict[str, str]:
    report_date = str(report.get("report_date") or "unknown")
    market = report.get("market")
    market = market if isinstance(market, dict) else {}
    assets = report.get("assets")
    asset_rows = [item for item in assets if isinstance(item, dict)] if isinstance(assets, list) else []
    priority = [
        item
        for item in asset_rows
        if item.get("action_level") in {"prepare", "action_candidate"}
    ]
    if priority:
        headline = "发现重点研究机会"
        names = "、".join(str(item.get("name") or item.get("symbol")) for item in priority[:2])
        subject = f"【{headline}】{names}｜{report_date}"
    elif bool(market.get("panic")):
        subject = f"【市场恐慌观察】暂无行动候选｜{report_date}"
    else:
        subject = f"【每日投资研究简报】继续等待｜{report_date}"

    lines = [
        f"日期：{report_date}",
        f"结论：{report.get('conclusion') or '当前没有形成可用研究结论。'}",
        "",
        "市场状态",
        f"- 状态：{market.get('regime') or '数据待补齐'}",
        f"- 上证60日点位变化：{_display(market.get('shanghai_60d_point_change'), '点')}",
        f"- 当日跌停：{_display(market.get('limit_down_count'), '家')}",
        f"- 市场数据源：{market.get('market_context_source') or 'unavailable'}",
        "",
        "合并研究候选",
    ]
    for asset in asset_rows:
        entry = asset.get("entry_framework")
        entry = entry if isinstance(entry, dict) else {}
        triggers = asset.get("panic_triggers")
        trigger_text = "；".join(
            str(item.get("label"))
            for item in triggers
            if isinstance(item, dict) and item.get("label")
        ) if isinstance(triggers, list) else ""
        lines.extend(
            [
                f"- {asset.get('name', asset.get('symbol', '未知标的'))}"
                f"（{asset.get('symbol', '—')}）｜{asset.get('action_label', '继续观察')}",
                f"  触发原因：{trigger_text or '未触发既定恐慌条件'}",
                f"  Capability：{asset.get('data_quality') or 'unknown'}",
                f"  数据来源：{asset.get('data_source') or 'unknown'}",
                f"  下一复核：{entry.get('next_review_condition') or asset.get('next_condition') or '下一交易日'}",
            ]
        )
        counter = asset.get("counter_evidence")
        if isinstance(counter, list) and counter:
            lines.append(f"  主要风险：{counter[0]}")

    gaps = report.get("data_gaps")
    if isinstance(gaps, list) and gaps:
        lines.extend(["", f"数据缺口：{len(gaps)}项，网页内查看详情。"])
    lines.extend(
        [
            "",
            f"网页查看：{report_web_url}",
            "",
            "风险提示：这是研究候选与影子评估，不是自动交易指令；"
            "数据和策略有效性仍需持续验证，系统不会执行真实交易。",
        ]
    )
    return {"subject": subject, "body": "\n".join(lines)}


def _opportunity_reason_fingerprint(report: Mapping[str, Any]) -> str:
    market = report.get("market")
    market = market if isinstance(market, dict) else {}
    assets = report.get("assets")
    normalized_assets = []
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            normalized_assets.append(
                {
                    "symbol": item.get("symbol"),
                    "action_level": item.get("action_level"),
                    "trigger_codes": sorted(
                        str(trigger.get("code"))
                        for trigger in item.get("panic_triggers", [])
                        if isinstance(trigger, dict) and trigger.get("code")
                    ),
                }
            )
    payload = {
        "market_panic": bool(market.get("panic")),
        "market_trigger_codes": sorted(
            str(trigger.get("code"))
            for trigger in market.get("panic_triggers", [])
            if isinstance(trigger, dict) and trigger.get("code")
        ),
        "assets": sorted(normalized_assets, key=lambda item: str(item["symbol"])),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _display(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"
