from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from src.investment_research.application.daily_pipeline import DailyResearchInputs, DailyResearchPipeline
from src.investment_research.operations.models import DeliveryChannel, JobStatus
from src.investment_research.operations.scheduling import TradingDaySchedule
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_discovery import SQLiteDiscoveryRepository
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository
from src.investment_research.thesis.seeds import import_thesis_identities, load_blueprint_manifest


NOW = datetime(2026, 7, 20, 17, 0, tzinfo=timezone.utc)


def _pipeline(tmp_path) -> DailyResearchPipeline:
    path = tmp_path / "research.sqlite3"
    research = SQLiteResearchRepository(path)
    import_thesis_identities(research, load_blueprint_manifest(), NOW)
    return DailyResearchPipeline(
        research,
        SQLiteIntelligenceRepository(path),
        SQLiteDiscoveryRepository(path),
        SQLiteOperationsRepository(path),
        TradingDaySchedule(run_after=time(0, 30)),
    )


def test_pipeline_generates_truthful_empty_daily_report_and_outbox(tmp_path) -> None:
    pipeline = _pipeline(tmp_path)
    report = pipeline.run_if_due(
        "run-1", NOW, DailyResearchInputs(NOW), channels=(DeliveryChannel.FEISHU, DeliveryChannel.EMAIL)
    )
    assert report is not None
    assert report.candidates == ()
    assert report.discovery_leads == ()
    assert report.market_state is None
    assert report.trade_date == pipeline.schedule.local_now(NOW).date()
    assert report.trade_date != NOW.date()
    assert "No new high-quality" in report.conclusion
    trade_date = pipeline.schedule.local_now(NOW).date()
    assert pipeline.intelligence.get_daily_research_report(trade_date).report_id == report.report_id
    assert len(pipeline.operations.claim_due(NOW)) == 2
    assert pipeline.operations.get_run(pipeline.job_name, trade_date, "shadow").status == JobStatus.SUCCEEDED


def test_pipeline_is_idempotent_for_the_same_trade_date(tmp_path) -> None:
    pipeline = _pipeline(tmp_path)
    first = pipeline.run_if_due("run-1", NOW, DailyResearchInputs(NOW))
    second = pipeline.run_if_due("run-2", NOW, DailyResearchInputs(NOW))
    assert second == first
    trade_date = pipeline.schedule.local_now(NOW).date()
    assert pipeline.operations.get_run(pipeline.job_name, trade_date, "shadow").attempt_count == 1


def test_pipeline_does_not_run_before_schedule(tmp_path) -> None:
    pipeline = _pipeline(tmp_path)
    before = datetime(2026, 7, 20, 16, 29, tzinfo=timezone.utc)
    assert pipeline.run_if_due("run-1", before, DailyResearchInputs(before)) is None


def test_pipeline_failure_is_recorded_for_retry(tmp_path) -> None:
    pipeline = _pipeline(tmp_path)
    invalid_inputs = DailyResearchInputs(NOW, discovery_contexts=(None,))  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        pipeline.run_if_due("run-1", NOW, invalid_inputs)
    run = pipeline.operations.get_run(pipeline.job_name, pipeline.schedule.local_now(NOW).date(), "shadow")
    assert run.status == JobStatus.FAILED
    assert run.error
