"""One-way Feishu webhook and SMTP notification delivery."""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

from .config import ValueHunterConfig
from .models import ScanResult


def render_text(result: ScanResult) -> str:
    market = result.market
    lines = [
        f"【Value Hunter】A股科技研究提醒",
        f"日期：{market.observation.as_of}",
        f"市场状态：{market.level}（{market.score:.1f}/100）",
        "触发依据：" + "；".join(market.reasons[:4]),
        "",
    ]
    if not result.candidates:
        lines.append("本轮没有达到研究门槛且数据完整的候选。")
    for index, item in enumerate(result.candidates, 1):
        obs = item.observation
        lines.extend([
            f"{index}. {obs.name}（{obs.symbol}）｜{item.bucket}｜{item.score.total:.1f}分",
            "入选依据：" + ("；".join(item.reasons[:4]) or "仅通过初筛，等待补充证据"),
            f"首要否决项：{item.first_rejection}",
            "",
        ])
    lines.extend([
        "状态含义：进入研究名单，不构成买入建议。",
        f"数据源：{market.observation.source}",
    ])
    return "\n".join(lines).strip()


class NotificationSender:
    def __init__(self, config: ValueHunterConfig):
        self.config = config
        self.last_errors: list[str] = []

    def configured_channels(self) -> list[str]:
        channels: list[str] = []
        if self.config.feishu_webhook_url:
            channels.append("feishu")
        if self.config.smtp_host and self.config.email_to:
            channels.append("email")
        return channels

    def send(self, result: ScanResult) -> list[str]:
        text = render_text(result)
        delivered: list[str] = []
        self.last_errors = []
        if self.config.feishu_webhook_url:
            try:
                self._send_feishu(text)
                delivered.append("feishu")
            except Exception as exc:
                self.last_errors.append(f"飞书投递失败: {type(exc).__name__}: {exc}")
        if self.config.smtp_host and self.config.email_to:
            try:
                self._send_email(text)
                delivered.append("email")
            except Exception as exc:
                self.last_errors.append(f"邮件投递失败: {type(exc).__name__}: {exc}")
        return delivered

    def _send_feishu(self, text: str) -> None:
        payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.config.feishu_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310 - explicit configured webhook
            body = json.loads(response.read().decode("utf-8"))
        if body.get("code", body.get("StatusCode", 0)) not in (0, None):
            raise RuntimeError(f"飞书Webhook返回错误: {body.get('msg') or body.get('StatusMessage')}")

    def _send_email(self, text: str) -> None:
        msg = EmailMessage()
        sender = self.config.smtp_from or self.config.smtp_username
        msg["From"] = sender
        msg["To"] = self.config.email_to
        msg["Subject"] = "Value Hunter：A股科技研究提醒"
        msg.set_content(text)
        context = ssl.create_default_context()
        if self.config.smtp_port == 465:
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port, timeout=20, context=context) as client:
                if self.config.smtp_username:
                    client.login(self.config.smtp_username, self.config.smtp_password)
                client.send_message(msg)
        else:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=20) as client:
                client.starttls(context=context)
                if self.config.smtp_username:
                    client.login(self.config.smtp_username, self.config.smtp_password)
                client.send_message(msg)
