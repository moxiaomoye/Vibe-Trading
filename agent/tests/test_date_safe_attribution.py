from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.investment_research.mispricing.attribution import (
    AttributionPolicy,
    AttributionScope,
    DateSafeAttributionEngine,
    EventDirection,
    EventType,
    PriceMoveContext,
    ResearchEvent,
)


START = datetime(2026, 7, 20, tzinfo=timezone.utc)
END = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)
POLICY = AttributionPolicy("fixture-v1", 0.02, 0.02, 0.65)


def _context(**overrides):
    values = {
        "asset_id": "asset-a",
        "sector": "semiconductor",
        "window_start": START,
        "window_end": END,
        "asset_return": -0.10,
        "market_return": None,
        "sector_return": None,
        "asset_evidence_id": "price-a",
        "market_evidence_id": None,
        "sector_evidence_id": None,
    }
    values.update(overrides)
    return PriceMoveContext(**values)


def _event(
    event_id="event-a",
    *,
    event_type=EventType.EARNINGS_WARNING,
    available_at=END,
    asset_id="asset-a",
    sector=None,
    direction=EventDirection.NEGATIVE,
):
    return ResearchEvent(
        event_id=event_id,
        event_type=event_type,
        source="fixture-announcement",
        event_at=END - timedelta(hours=1),
        available_at=available_at,
        relevance=0.9,
        direction=direction,
        severity=0.8,
        confidence=0.85,
        supporting_evidence_ids=(f"evidence-{event_id}",),
        counter_evidence_ids=(f"counter-{event_id}",),
        unknowns=("duration of impact",),
        asset_id=asset_id,
        sector=sector,
    )


def _evaluate(context, events=()):
    return DateSafeAttributionEngine().evaluate(
        context=context,
        events=tuple(events),
        information_cutoff=CUTOFF,
        policy=POLICY,
    )


def test_company_specific_event_attribution():
    result = _evaluate(_context(), [_event()])
    assert result.scope == AttributionScope.COMPANY_SPECIFIC
    assert result.supporting_evidence_ids == ("evidence-event-a",)
    assert result.counter_evidence_ids == ("counter-event-a",)


_REMAINING_EVENT_TYPES = [
    pytest.param(EventType.REGULATORY_PENALTY, id="regulatory_penalty"),
    pytest.param(EventType.MATERIAL_LITIGATION, id="material_litigation"),
    pytest.param(EventType.HOLDER_SELLING, id="holder_selling"),
    pytest.param(EventType.SHARE_PLEDGE, id="share_pledge"),
    pytest.param(EventType.MAJOR_ORDER_CHANGE, id="major_order_change"),
    pytest.param(EventType.COMPANY_ANNOUNCEMENT, id="company_announcement"),
]


@pytest.mark.parametrize("event_type", _REMAINING_EVENT_TYPES)
def test_each_declared_event_type_produces_company_specific_attribution(event_type):
    result = _evaluate(_context(), [_event(event_type=event_type)])
    assert result.scope == AttributionScope.COMPANY_SPECIFIC


def test_sector_attribution_from_policy_and_aligned_return():
    context = _context(
        sector_return=-0.09,
        sector_evidence_id="sector-price",
    )
    event = _event(
        event_type=EventType.SECTOR_POLICY,
        asset_id=None,
        sector="semiconductor",
    )
    result = _evaluate(context, [event])
    assert result.scope == AttributionScope.SECTOR


def test_market_systemic_attribution():
    context = _context(market_return=-0.09, market_evidence_id="market-price")
    result = _evaluate(context)
    assert result.scope == AttributionScope.MARKET_SYSTEMIC
    assert result.supporting_evidence_ids == ("market-price",)


def test_mixed_attribution_when_company_and_market_evidence_coexist():
    context = _context(market_return=-0.09, market_evidence_id="market-price")
    result = _evaluate(context, [_event()])
    assert result.scope == AttributionScope.MIXED
    assert len(result.attribution.causes) == 2


def test_absence_of_news_is_not_evidence_of_absence():
    result = _evaluate(_context())
    assert result.scope == AttributionScope.INSUFFICIENT_DATA
    assert result.attribution.is_fully_unknown
    assert any("not evidence" in item for item in result.unknowns)


def test_future_event_cannot_influence_scan_date():
    future = _event(available_at=CUTOFF + timedelta(days=1))
    baseline = _evaluate(_context())
    with_future = _evaluate(_context(), [future])
    assert with_future.scope == baseline.scope
    assert with_future.attribution.causes == baseline.attribution.causes
    assert with_future.excluded_future_event_ids == (future.event_id,)


def test_repeated_evaluation_is_deterministic():
    context = _context(market_return=-0.09, market_evidence_id="market-price")
    first = _evaluate(context, [_event()])
    second = _evaluate(context, [_event()])
    assert first == second


def test_window_after_cutoff_is_rejected():
    context = _context(window_end=CUTOFF + timedelta(minutes=1))
    with pytest.raises(ValueError, match="cutoff"):
        _evaluate(context)
