from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import investment_research_routes as routes
from src.config.accessor import reset_env_config
from src.investment_research.macro.fred_provider import FredSeriesDefinition
from src.investment_research.macro.models import (
    MacroEvidenceBatch,
    MacroObservationEvidence,
    MacroProviderStatus,
)


NOW = datetime(2026, 7, 30, 10, 0, tzinfo=timezone.utc)


class _Provider:
    provider_name = "fred"
    configured = True
    series = (
        FredSeriesDefinition(
            "VIXCLS",
            "CBOE Volatility Index",
            "global-risk",
        ),
    )

    def load(self, *, as_of: date) -> MacroEvidenceBatch:
        retrieved_at = datetime.now(timezone.utc)
        observation = MacroObservationEvidence(
            provider="fred",
            series_id="VIXCLS",
            title="CBOE Volatility Index",
            observation_date=as_of,
            value=Decimal("19.25"),
            retrieved_at=retrieved_at,
            source_url="https://fred.stlouisfed.org/series/VIXCLS",
            subject_id="global-risk",
        )
        return MacroEvidenceBatch(
            "fred",
            MacroProviderStatus.CONFIGURED,
            as_of,
            retrieved_at,
            (observation,),
        )


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv(
        "VIBE_INVESTMENT_RESEARCH_DB_PATH",
        str(tmp_path / "research.sqlite3"),
    )
    reset_env_config()
    routes.reset_investment_research_repository()
    monkeypatch.setattr(routes, "FredMacroEvidenceProvider", _Provider)
    app = FastAPI()

    async def allow() -> None:
        return None

    routes.register_investment_research_routes(app, allow)
    return TestClient(app)


def test_macro_status_exposes_capability_without_credentials(tmp_path, monkeypatch):
    response = _client(tmp_path, monkeypatch).get(
        "/investment-research/macro-evidence/status"
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["series"][0]["series_id"] == "VIXCLS"
    assert response.json()["credentials_exposed"] is False
    assert "api_key" not in response.text.lower()


def test_macro_collection_is_pending_deduplicated_and_has_no_side_effects(
    tmp_path,
    monkeypatch,
):
    client = _client(tmp_path, monkeypatch)

    first = client.post("/investment-research/macro-evidence/collect")
    second = client.post("/investment-research/macro-evidence/collect")
    inbox = client.get("/investment-research/evidence-inbox?status=pending")

    assert first.status_code == 200, first.text
    assert first.json()["ingested"] == 1
    assert first.json()["automatic_classification"] is False
    assert first.json()["candidate_or_valuation_effect"] == "none_until_human_review"
    assert first.json()["scheduler_started"] is False
    assert first.json()["notification_sent"] is False
    assert first.json()["trading_executed"] is False
    assert second.status_code == 200, second.text
    assert second.json()["ingested"] == 0
    assert second.json()["deduplicated"] == 1
    assert len(inbox.json()) == 1
    assert inbox.json()[0]["proposed_direction"] == "neutral"
