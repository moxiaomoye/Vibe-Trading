from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.value_hunter.config import ValueHunterConfig
from src.value_hunter.notifier import NotificationSender, render_text
from src.value_hunter.providers import DemoProvider
from src.value_hunter.scheduler import ValueHunterScheduler
from src.value_hunter.service import ValueHunterService
from src.value_hunter.store import ValueHunterStore


class SpyNotifier(NotificationSender):
    def __init__(self, config):
        super().__init__(config)
        self.calls = 0

    def configured_channels(self):
        return ["spy"]

    def send(self, result):
        self.calls += 1
        return ["spy"]


def config(tmp_path: Path, **changes) -> ValueHunterConfig:
    base = ValueHunterConfig(
        enabled=True, provider="demo", schedule="18:10", timezone="Asia/Shanghai",
        market_alert_score=70, candidate_alert_score=75, max_candidates=5,
        database_path=tmp_path / "value.sqlite3", watchlist_path=None,
        feishu_webhook_url="", smtp_host="", smtp_port=465, smtp_username="",
        smtp_password="", smtp_from="", email_to="", notify_on_demo=True,
    )
    return replace(base, **changes)


def test_service_persists_scan_and_sends_only_once(tmp_path):
    cfg = config(tmp_path)
    store = ValueHunterStore(cfg.database_path)
    notifier = SpyNotifier(cfg)
    service = ValueHunterService(cfg, DemoProvider(), store, notifier)

    first = service.run(notify=True)
    second = service.run(notify=True)

    assert first.notification_required is True
    assert len(first.candidates) == 2
    assert notifier.calls == 1
    assert store.latest()["run_id"] == second.run_id
    assert len(store.history()) == 2


def test_demo_notification_is_off_by_default(tmp_path):
    cfg = config(tmp_path, notify_on_demo=False)
    notifier = SpyNotifier(cfg)
    service = ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path), notifier)
    service.run(notify=True)
    assert notifier.calls == 0


def test_rendered_message_labels_research_not_buy(tmp_path):
    cfg = config(tmp_path)
    result = ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path)).run(notify=False)
    text = render_text(result)
    assert "进入研究名单" in text
    assert "不构成买入建议" in text
    assert "首要否决项" in text


def test_scheduler_computes_next_local_run(tmp_path):
    cfg = config(tmp_path)
    service = ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path))
    scheduler = ValueHunterScheduler(service)
    tz = timezone(timedelta(hours=8))
    before = datetime(2026, 7, 20, 18, 0, tzinfo=tz)
    after = datetime(2026, 7, 20, 19, 0, tzinfo=tz)
    assert scheduler.seconds_until_next_run(before) == 600
    assert scheduler.seconds_until_next_run(after) == 23 * 3600 + 10 * 60


def test_store_history_limit(tmp_path):
    cfg = config(tmp_path)
    service = ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path))
    for _ in range(3):
        service.run(notify=False)
    assert len(service.history(2)) == 2


def test_notification_failure_does_not_block_other_channel(tmp_path, monkeypatch):
    cfg = config(
        tmp_path,
        feishu_webhook_url="https://example.invalid/hook",
        smtp_host="smtp.example.invalid",
        email_to="research@example.invalid",
    )
    sender = NotificationSender(cfg)
    calls: list[str] = []

    def fail_feishu(_text):
        raise RuntimeError("webhook down")

    def deliver_email(_text):
        calls.append("email")

    monkeypatch.setattr(sender, "_send_feishu", fail_feishu)
    monkeypatch.setattr(sender, "_send_email", deliver_email)
    result = ValueHunterService(
        cfg, DemoProvider(), ValueHunterStore(cfg.database_path)
    ).run(notify=False)

    assert sender.send(result) == ["email"]
    assert calls == ["email"]
    assert "飞书投递失败" in sender.last_errors[0]


def test_status_exposes_missing_notification_configuration(tmp_path):
    cfg = config(tmp_path, feishu_webhook_url="", smtp_host="", email_to="")
    service = ValueHunterService(cfg, DemoProvider(), ValueHunterStore(cfg.database_path))
    status = service.status()
    assert status["notification_ready"] is False
    assert "VALUE_HUNTER_FEISHU_WEBHOOK" in status["missing_notification_settings"]
