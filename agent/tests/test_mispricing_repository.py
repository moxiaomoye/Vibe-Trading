from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from src.investment_research.assets.models import Asset
from src.investment_research.contracts import AssetType, OpportunityStatus
from src.investment_research.mispricing.models import MispricingOpportunity
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.repositories.sqlite_mispricing import SQLiteMispricingRepository
from src.investment_research.thesis.models import Thesis
from tests.test_mispricing_domain import NOW, _proposal


def _seed(tmp_path) -> tuple[SQLiteMispricingRepository, MispricingOpportunity]:
    path = tmp_path / "research.sqlite3"
    proposal = _proposal()
    research = SQLiteResearchRepository(path)
    research.save_thesis(Thesis("thesis", "AI Infrastructure", None, NOW))
    for evidence in proposal.evidence:
        research.save_evidence(evidence)
    research.save_evidence_set(proposal.evidence_set)
    research.append_thesis_version(proposal.thesis_version)

    repository = SQLiteMispricingRepository(path)
    repository.save_asset(Asset("asset", "TEST", "Test Asset", AssetType.ETF, "TEST", "USD", NOW))
    repository.save_exposure(proposal.exposure)
    repository.save_market_implied_view(proposal.market_implied_view)
    repository.save_attribution(proposal.attribution)
    repository.save_permanence_assessment(proposal.permanence)
    opportunity = MispricingOpportunity("opportunity", "thesis", "asset", "thesis:asset:valuation", NOW)
    repository.save_opportunity(opportunity)
    repository.append_opportunity_version(proposal.opportunity_version)
    return repository, opportunity


def test_mispricing_research_graph_round_trips(tmp_path) -> None:
    repository, opportunity = _seed(tmp_path)
    proposal = _proposal()

    assert repository.get_asset("asset").asset_type == AssetType.ETF
    assert repository.get_exposure("exposure") == proposal.exposure
    assert repository.get_market_implied_view("view") == proposal.market_implied_view
    assert repository.get_attribution("attribution") == proposal.attribution
    assert repository.get_permanence_assessment("permanence") == proposal.permanence
    assert repository.get_opportunity_by_dedupe_key(opportunity.dedupe_key) == opportunity
    assert repository.current_opportunity_version("opportunity", NOW) == proposal.opportunity_version


def test_opportunity_versions_are_append_only_and_point_in_time(tmp_path) -> None:
    repository, _ = _seed(tmp_path)
    first = _proposal().opportunity_version
    second = replace(
        first,
        opportunity_version_id="opportunity-v2",
        version_number=2,
        status=OpportunityStatus.WEAKENING,
        change_summary="Counter evidence increased.",
        effective_from=NOW + timedelta(days=1),
        next_review_at=NOW + timedelta(days=3),
        supersedes_version_id=first.opportunity_version_id,
    )
    repository.append_opportunity_version(second)

    assert repository.current_opportunity_version("opportunity", NOW).opportunity_version_id == "opportunity-v1"
    assert repository.current_opportunity_version("opportunity", NOW + timedelta(days=2)) == second
    with pytest.raises(ValueError, match="sequential"):
        repository.append_opportunity_version(second)


def test_opportunity_version_rejects_broken_parent_chain(tmp_path) -> None:
    repository, _ = _seed(tmp_path)
    first = _proposal().opportunity_version
    broken = replace(
        first,
        opportunity_version_id="opportunity-v2",
        version_number=2,
        status=OpportunityStatus.WEAKENING,
        effective_from=NOW + timedelta(days=1),
        next_review_at=NOW + timedelta(days=2),
        supersedes_version_id="wrong-parent",
    )

    with pytest.raises(ValueError, match="supersede"):
        repository.append_opportunity_version(broken)


def test_dedupe_key_prevents_daily_duplicate_opportunities(tmp_path) -> None:
    repository, opportunity = _seed(tmp_path)
    duplicate = replace(opportunity, opportunity_id="duplicate")

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_opportunity(duplicate)


def test_point_in_time_queries_require_existing_aware_cutoff(tmp_path) -> None:
    repository, _ = _seed(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.current_opportunity_version("opportunity", NOW.replace(tzinfo=None))
    with pytest.raises(KeyError):
        repository.current_opportunity_version("opportunity", NOW - timedelta(days=1))
    with pytest.raises(KeyError):
        repository.get_opportunity_by_dedupe_key("missing")

