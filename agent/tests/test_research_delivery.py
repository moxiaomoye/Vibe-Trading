from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from src.investment_research.operations.delivery import (
    DailyNotificationPlanner,
    DryRunTransport,
    OpportunityReportNotificationPlanner,
    OutboxDispatcher,
    ServerChanTurboTransport,
)
from src.investment_research.operations.models import DeliveryChannel, OutboxStatus
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository


NOW = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)


class FixtureRenderer:
    def render(self, report) -> str:
        return f"Research report {report.report_id}: continue waiting."


@dataclass
class FixtureTransport:
    should_fail: bool = False
    sent: int = 0

    def send(self, message) -> None:
        self.sent += 1
        if self.should_fail:
            raise RuntimeError("fixture transport failed")


def _planner(tmp_path):
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    planner = DailyNotificationPlanner(repository)
    planner.renderer = FixtureRenderer()
    report = SimpleNamespace(report_id="report-1", trade_date=date(2026, 7, 21), mode="shadow")
    return repository, planner, report


def test_daily_notification_planning_is_deterministic_and_channel_specific(tmp_path) -> None:
    repository, planner, report = _planner(tmp_path)
    channels = (DeliveryChannel.FEISHU, DeliveryChannel.EMAIL)
    assert planner.enqueue(report, channels, NOW) == 2
    assert planner.enqueue(report, channels, NOW) == 0
    claimed = repository.claim_due(NOW)
    assert {message.channel for message in claimed} == set(channels)
    assert all(message.source_id == "report-1" for message in claimed)


def test_dispatcher_records_success_and_failure_without_losing_messages(tmp_path) -> None:
    repository, planner, report = _planner(tmp_path)
    planner.enqueue(report, (DeliveryChannel.FEISHU, DeliveryChannel.EMAIL), NOW)
    good = FixtureTransport()
    bad = FixtureTransport(should_fail=True)
    dispatcher = OutboxDispatcher(
        repository,
        {DeliveryChannel.FEISHU: good, DeliveryChannel.EMAIL: bad},
        retry_delay=timedelta(minutes=15),
    )
    assert dispatcher.dispatch_due(NOW) == (1, 1)
    assert good.sent == 1
    assert bad.sent == 1
    email_id = next(
        message.message_id
        for message in repository.claim_due(NOW + timedelta(minutes=15))
        if message.channel == DeliveryChannel.EMAIL
    )
    assert repository.get_message(email_id).status == OutboxStatus.SENDING


def test_missing_transport_is_a_retryable_delivery_failure(tmp_path) -> None:
    repository, planner, report = _planner(tmp_path)
    planner.enqueue(report, (DeliveryChannel.EMAIL,), NOW)
    dispatcher = OutboxDispatcher(repository, {}, retry_delay=timedelta(minutes=1))
    assert dispatcher.dispatch_due(NOW) == (0, 1)
    message = repository.claim_due(NOW + timedelta(minutes=1))[0]
    assert message.attempt_count == 2


def test_dry_run_transport_never_requires_external_configuration(tmp_path) -> None:
    repository, planner, report = _planner(tmp_path)
    planner.enqueue(report, (DeliveryChannel.FEISHU,), NOW)
    transport = DryRunTransport()
    assert OutboxDispatcher(repository, {DeliveryChannel.FEISHU: transport}).dispatch_due(NOW) == (1, 0)
    assert transport.delivered_count == 1


def test_opportunity_report_preview_and_daily_deduplication(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    planner = OpportunityReportNotificationPlanner(repository)
    report = {
        "report_version": "2.0",
        "report_date": "2026-07-29",
        "conclusion": "今天继续等待估值和止跌条件同时满足。",
        "market": {
            "regime": "恐慌/系统性回撤",
            "shanghai_60d_point_change": -283.69,
            "limit_down_count": 9,
        },
        "assets": [
            {
                "symbol": "600522.SH",
                "name": "中天科技",
                "action_level": "research",
                "action_label": "恐慌观察",
                "latest_close": 29.34,
                "return_60d_pct": -10.71,
                "entry_framework": {
                    "summary": "当前属于重点观察。",
                    "next_review_condition": "等待收盘重新站上MA20",
                },
                "counter_evidence": ["当前价格高于静态乐观情景。"],
            }
        ],
        "data_gaps": ["news unavailable"],
    }
    preview = planner.preview(report)
    assert "每日投资研究简报" in preview["subject"]
    assert "中天科技" in preview["body"]
    assert "不是自动交易指令" in preview["body"]

    ids = planner.enqueue(report, (DeliveryChannel.FEISHU, DeliveryChannel.EMAIL), NOW)
    assert len(ids) == 2
    assert planner.enqueue(report, (DeliveryChannel.FEISHU, DeliveryChannel.EMAIL), NOW) == ids
    transports = {
        DeliveryChannel.FEISHU: DryRunTransport(),
        DeliveryChannel.EMAIL: DryRunTransport(),
    }
    dispatcher = OutboxDispatcher(repository, transports)
    assert dispatcher.dispatch_message_ids(ids, NOW) == (2, 0)
    assert dispatcher.dispatch_message_ids(ids, NOW) == (0, 0)


def test_targeted_dispatch_does_not_claim_unrelated_pending_message(tmp_path) -> None:
    repository, planner, report = _planner(tmp_path)
    planner.enqueue(report, (DeliveryChannel.FEISHU, DeliveryChannel.EMAIL), NOW)
    opportunity = OpportunityReportNotificationPlanner(repository)
    ids = opportunity.enqueue(
        {
            "report_version": "2.0",
            "report_date": "2026-07-29",
            "conclusion": "继续等待。",
            "market": {},
            "assets": [],
        },
        (DeliveryChannel.FEISHU,),
        NOW,
    )
    transport = DryRunTransport()
    dispatcher = OutboxDispatcher(
        repository, {DeliveryChannel.FEISHU: transport}
    )
    assert dispatcher.dispatch_message_ids(ids, NOW) == (1, 0)
    unrelated = repository.claim_due(NOW)
    assert len(unrelated) == 2
    assert {message.message_type for message in unrelated} == {"daily_research"}


def test_serverchan_transport_uses_title_and_body_without_exposing_key(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"code":0,"message":"success"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["data"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    message = SimpleNamespace(subject="重要标题", body="研究正文")
    ServerChanTurboTransport("SCT123456TEST").send(message)

    assert captured["url"].startswith("https://sctapi.ftqq.com/")
    assert b"title=" in captured["data"]
    assert b"desp=" in captured["data"]
    assert captured["timeout"] == 10.0


def _opportunity_report(
    *,
    report_date: str = "2026-07-29",
    symbol: str = "600522.SH",
    action_level: str = "research",
) -> dict:
    return {
        "report_version": "2.0",
        "report_date": report_date,
        "conclusion": "继续等待证据闭环。",
        "market": {
            "regime": "panic",
            "panic": True,
            "panic_triggers": [{"code": "market_drawdown", "label": "大盘显著回撤"}],
        },
        "assets": [
            {
                "symbol": symbol,
                "name": symbol,
                "action_level": action_level,
                "action_label": "研究候选",
                "panic_triggers": [
                    {"code": "asset_drawdown", "label": "三个月显著回撤"}
                ],
                "counter_evidence": ["基本面证据仍需复核。"],
            }
        ],
    }


def test_opportunity_reason_is_suppressed_for_24_hours(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    planner = OpportunityReportNotificationPlanner(repository)
    report = _opportunity_report()

    first_ids = planner.enqueue(report, (DeliveryChannel.SERVERCHAN,), NOW)
    assert len(repository.claim_message_ids(first_ids, NOW)) == 1

    repeated = dict(report, report_date="2026-07-30")
    second_ids = planner.enqueue(
        repeated,
        (DeliveryChannel.SERVERCHAN,),
        NOW + timedelta(hours=23),
    )
    assert repository.claim_message_ids(
        second_ids,
        NOW + timedelta(hours=23),
    ) == ()

    third_ids = planner.enqueue(
        dict(report, report_date="2026-07-31"),
        (DeliveryChannel.SERVERCHAN,),
        NOW + timedelta(hours=25),
    )
    assert len(
        repository.claim_message_ids(
            third_ids,
            NOW + timedelta(hours=25),
        )
    ) == 1


def test_serverchan_is_limited_to_four_planned_messages_in_24_hours(tmp_path) -> None:
    repository = SQLiteOperationsRepository(tmp_path / "research.sqlite3")
    planner = OpportunityReportNotificationPlanner(repository)

    planned_ids: list[str] = []
    for index in range(5):
        ids = planner.enqueue(
            _opportunity_report(
                report_date=f"2026-07-{20 + index:02d}",
                symbol=f"60052{index}.SH",
            ),
            (DeliveryChannel.SERVERCHAN,),
            NOW + timedelta(minutes=index),
        )
        planned_ids.extend(ids)

    claimed = repository.claim_message_ids(
        tuple(planned_ids),
        NOW + timedelta(minutes=5),
    )
    assert len(claimed) == 4
    assert repository.count_channel_messages_since(
        DeliveryChannel.SERVERCHAN,
        NOW - timedelta(seconds=1),
    ) == 4
