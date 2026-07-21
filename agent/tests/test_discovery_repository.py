from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.discovery.models import DiscoveryDisposition, FundamentalIntegrity, ResearchLead, ResearchSnapshot
from src.investment_research.repositories.sqlite_discovery import SQLiteDiscoveryRepository


NOW = datetime(2026, 7, 21, 10, 0, tzinfo=timezone.utc)


def _snapshot() -> ResearchSnapshot:
    return ResearchSnapshot(
        "snapshot-1", "asset-1", "thesis-version-1", "evidence-set-1", NOW,
        -0.35, -0.15, 0.2, FundamentalIntegrity.INTACT,
        ("fundamental-1",), ("attribution-1",), ("counter-1",), (), (),
    )


def _lead() -> ResearchLead:
    return ResearchLead(
        "lead-1", "asset-1", "thesis-version-1", "evidence-set-1",
        DiscoveryDisposition.OPPORTUNITY_REVIEW, ("material dislocation",), (),
        "Is the impairment temporary?", NOW,
    )


def test_discovery_result_round_trip_and_append_only(tmp_path) -> None:
    repository = SQLiteDiscoveryRepository(tmp_path / "research.sqlite3")
    repository.save_result(_snapshot(), _lead())
    assert repository.get_result("lead-1") == (_snapshot(), _lead())
    with pytest.raises(Exception):
        repository.save_result(_snapshot(), _lead())


def test_discovery_result_consistency_is_enforced(tmp_path) -> None:
    repository = SQLiteDiscoveryRepository(tmp_path / "research.sqlite3")
    with pytest.raises(ValueError, match="inconsistent"):
        repository.save_result(_snapshot(), replace(_lead(), asset_id="other"))


def test_discovery_leads_are_queryable_point_in_time_and_by_disposition(tmp_path) -> None:
    repository = SQLiteDiscoveryRepository(tmp_path / "research.sqlite3")
    repository.save_result(_snapshot(), _lead())
    later_snapshot = replace(_snapshot(), snapshot_id="snapshot-2", as_of=NOW + timedelta(days=1))
    later_lead = replace(
        _lead(), lead_id="lead-2", disposition=DiscoveryDisposition.EVIDENCE_GAP,
        reasons=("fundamental evidence missing",), missing_evidence=("fundamentals",),
        as_of=NOW + timedelta(days=1),
    )
    repository.save_result(later_snapshot, later_lead)
    assert repository.list_leads(NOW) == (_lead(),)
    assert repository.list_leads(NOW + timedelta(days=2), DiscoveryDisposition.EVIDENCE_GAP) == (later_lead,)
    with pytest.raises(KeyError):
        repository.get_result("missing")
