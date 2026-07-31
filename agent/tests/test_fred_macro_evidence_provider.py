from __future__ import annotations

import json
from datetime import date, datetime, timezone

from src.config.accessor import reset_env_config
from src.investment_research.application.macro_evidence_ingestion import (
    MacroEvidenceIngestionService,
)
from src.investment_research.evidence.inbox import EvidenceInboxStatus
from src.investment_research.macro.fred_provider import (
    FredMacroEvidenceProvider,
    FredSeriesDefinition,
)
from src.investment_research.repositories.sqlite_evidence_inbox import (
    SQLiteEvidenceInboxRepository,
)


TODAY = date(2026, 7, 30)
NOW = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)
SERIES = (
    FredSeriesDefinition("DGS10", "US 10-Year Treasury Yield", "global-liquidity", "percent", "daily"),
)


def _payload(**_kwargs):
    return json.dumps(
        {
            "ok": True,
            "source": "fred",
            "data": {
                "series_id": "DGS10",
                "observations": [
                    {"date": "2026-07-28", "value": 4.12},
                    {"date": "2026-07-29", "value": 4.18},
                ],
            },
        }
    )


def test_fred_provider_requires_configuration_without_exposing_key(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    reset_env_config()
    provider = FredMacroEvidenceProvider(
        series=SERIES, execute=_payload, today=lambda: TODAY, now=lambda: NOW
    )

    result = provider.load(as_of=TODAY)

    assert result.status.value == "unconfigured"
    assert result.observations == ()
    assert result.to_dict()["historical_replay_eligible"] is False


def test_fred_provider_normalizes_traceable_current_observation(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fixture-key")
    reset_env_config()
    provider = FredMacroEvidenceProvider(
        series=SERIES, execute=_payload, today=lambda: TODAY, now=lambda: NOW
    )

    result = provider.load(as_of=TODAY)

    assert result.status.value == "configured"
    observation = result.observations[0]
    assert observation.series_id == "DGS10"
    assert str(observation.value) == "4.18"
    assert str(observation.previous_value) == "4.12"
    assert observation.source_url == "https://fred.stlouisfed.org/series/DGS10"
    assert "fixture-key" not in json.dumps(result.to_dict())


def test_fred_provider_rejects_current_revision_for_historical_replay(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "fixture-key")
    reset_env_config()
    provider = FredMacroEvidenceProvider(
        series=SERIES, execute=_payload, today=lambda: TODAY, now=lambda: NOW
    )

    result = provider.load(as_of=date(2026, 7, 1))

    assert result.status.value == "historical_unsupported"
    assert result.observations == ()
    assert "ALFRED" in result.data_gaps[0]


def test_macro_ingestion_reuses_pending_evidence_inbox_and_deduplicates(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FRED_API_KEY", "fixture-key")
    reset_env_config()
    repository = SQLiteEvidenceInboxRepository(tmp_path / "research.sqlite3")
    provider = FredMacroEvidenceProvider(
        series=SERIES, execute=_payload, today=lambda: TODAY, now=lambda: NOW
    )
    service = MacroEvidenceIngestionService(repository)

    first = service.ingest_fred(provider, as_of=TODAY, ingested_at=NOW)
    second = service.ingest_fred(provider, as_of=TODAY, ingested_at=NOW)

    assert first.ingested == 1
    assert second.deduplicated == 1
    rows = repository.list_items(EvidenceInboxStatus.PENDING, 10)
    assert len(rows) == 1
    assert rows[0].item.proposed_subject_type.value == "market"
    assert rows[0].item.proposed_direction.value == "neutral"
    assert "current_revision_not_approved_for_historical_replay" in (
        rows[0].item.quality_warnings
    )
