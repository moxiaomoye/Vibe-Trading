from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from src.investment_research.candidates.models import ResearchCandidate
from src.investment_research.contracts import ActionLevel, MarketRegime
from src.investment_research.intelligence.alert_eligibility import AlertEligibilityPolicy
from src.investment_research.market.models import MarketState
from src.investment_research.repositories.sqlite_intelligence import SQLiteIntelligenceRepository
from tests.test_alert_eligibility import _assessment
from tests.test_mispricing_domain import NOW
from tests.test_mispricing_repository import _seed


def _intelligence(tmp_path):
    mispricing, _ = _seed(tmp_path)
    repository = SQLiteIntelligenceRepository(mispricing.path)
    market = MarketState("market-state-1", MarketRegime.PANIC, "set", ("systemic stress",), (), 0.8, NOW)
    candidate = ResearchCandidate("candidate-1", "opportunity", "asset", NOW)
    assessment = replace(
        _assessment(),
        evidence_set_id="set",
        thesis_version_id="thesis-v1",
        opportunity_version_id="opportunity-v1",
    )
    repository.save_market_state(market)
    repository.save_candidate(candidate)
    repository.append_assessment(assessment)
    return repository, market, candidate, assessment


def test_candidate_market_and_assessment_round_trip(tmp_path) -> None:
    repository, market, candidate, assessment = _intelligence(tmp_path)

    assert repository.get_market_state(market.market_state_id) == market
    assert repository.get_candidate(candidate.candidate_id) == candidate
    assert repository.current_assessment(candidate.candidate_id, NOW) == assessment


def test_assessments_are_append_only_and_point_in_time(tmp_path) -> None:
    repository, _, candidate, first = _intelligence(tmp_path)
    second = replace(
        first,
        assessment_id="assessment-2",
        version_number=2,
        action_level=ActionLevel.RESEARCH,
        confidence=0.7,
        effective_from=NOW + timedelta(days=1),
        next_review_at=NOW + timedelta(days=3),
        supersedes_assessment_id=first.assessment_id,
    )
    repository.append_assessment(second)

    assert repository.current_assessment(candidate.candidate_id, NOW) == first
    assert repository.current_assessment(candidate.candidate_id, NOW + timedelta(days=2)) == second
    with pytest.raises(ValueError, match="sequential"):
        repository.append_assessment(second)


def test_alert_persistence_requires_eligible_matching_decision(tmp_path) -> None:
    repository, _, _, assessment = _intelligence(tmp_path)
    policy = AlertEligibilityPolicy()
    decision = policy.evaluate(assessment, NOW)
    alert = policy.create_alert("alert-1", assessment, NOW)

    repository.save_alert(alert, decision)

    assert repository.get_alert("alert-1") == alert
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_alert(replace(alert, alert_id="duplicate"), decision)
    ineligible = policy.evaluate(replace(assessment, confidence=0.5), NOW)
    with pytest.raises(ValueError, match="eligible decision"):
        repository.save_alert(replace(alert, alert_id="invalid"), ineligible)


def test_candidate_asset_must_match_opportunity(tmp_path) -> None:
    mispricing, _ = _seed(tmp_path)
    repository = SQLiteIntelligenceRepository(mispricing.path)

    with pytest.raises(ValueError, match="must match"):
        repository.save_candidate(ResearchCandidate("candidate", "opportunity", "wrong-asset", NOW))


def test_intelligence_point_in_time_and_missing_reads(tmp_path) -> None:
    repository, _, candidate, _ = _intelligence(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.current_assessment(candidate.candidate_id, NOW.replace(tzinfo=None))
    with pytest.raises(KeyError):
        repository.current_assessment(candidate.candidate_id, NOW - timedelta(days=1))
    with pytest.raises(KeyError):
        repository.get_market_state("missing")
    with pytest.raises(KeyError):
        repository.get_candidate("missing")
    with pytest.raises(KeyError):
        repository.get_alert("missing")

