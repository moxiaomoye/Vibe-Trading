from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from src.investment_research.operations.delivery import DailyNotificationPlanner, DryRunTransport, OutboxDispatcher
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
