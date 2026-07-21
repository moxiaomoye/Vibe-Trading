"""Daily-report notification planning and controlled transport dispatch."""

from __future__ import annotations

import json
import smtplib
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol
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
        delivered = failed = 0
        for message in self.repository.claim_due(now, limit, self.max_attempts):
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
