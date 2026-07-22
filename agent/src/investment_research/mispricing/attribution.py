"""Date-safe adverse-event and price-move attribution for screened assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from ..contracts import AttributionCategory, AttributionRole, Permanence
from .models import PriceMoveAttribution, PriceMoveCause


class EventType(StrEnum):
    EARNINGS_WARNING = "earnings_warning"
    REGULATORY_PENALTY = "regulatory_penalty"
    MATERIAL_LITIGATION = "material_litigation"
    HOLDER_SELLING = "holder_selling"
    SHARE_PLEDGE = "share_pledge"
    MAJOR_ORDER_CHANGE = "major_order_change"
    COMPANY_ANNOUNCEMENT = "company_announcement"
    SECTOR_POLICY = "sector_policy"


class EventDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AttributionScope(StrEnum):
    MARKET_SYSTEMIC = "market_systemic"
    SECTOR = "sector"
    COMPANY_SPECIFIC = "company_specific"
    MIXED = "mixed"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class ResearchEvent:
    event_id: str
    event_type: EventType
    source: str
    event_at: datetime
    available_at: datetime
    relevance: float
    direction: EventDirection
    severity: float
    confidence: float
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    unknowns: tuple[str, ...]
    asset_id: str | None = None
    sector: str | None = None
    data_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.event_at, "event_at")
        _aware(self.available_at, "available_at")
        if self.available_at < self.event_at:
            raise ValueError("event availability cannot precede the event")
        if not self.event_id.strip() or not self.source.strip():
            raise ValueError("event identity and source are required")
        for name in ("relevance", "severity", "confidence"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.direction != EventDirection.NEUTRAL and not self.supporting_evidence_ids:
            raise ValueError("directional events require supporting evidence")
        if self.event_type == EventType.SECTOR_POLICY and not (self.sector or "").strip():
            raise ValueError("sector-policy events require a sector")


@dataclass(frozen=True, slots=True)
class PriceMoveContext:
    asset_id: str
    sector: str | None
    window_start: datetime
    window_end: datetime
    asset_return: float | None
    market_return: float | None
    sector_return: float | None
    asset_evidence_id: str | None
    market_evidence_id: str | None
    sector_evidence_id: str | None
    data_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _aware(self.window_start, "window_start")
        _aware(self.window_end, "window_end")
        if self.window_end < self.window_start:
            raise ValueError("price-move window end cannot precede start")
        if not self.asset_id.strip():
            raise ValueError("price-move asset is required")


@dataclass(frozen=True, slots=True)
class AttributionPolicy:
    version: str
    market_alignment_tolerance: float
    sector_alignment_tolerance: float
    price_alignment_confidence: float

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("attribution policy version is required")
        for name in (
            "market_alignment_tolerance",
            "sector_alignment_tolerance",
            "price_alignment_confidence",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class AttributionEvaluation:
    scope: AttributionScope
    attribution: PriceMoveAttribution
    policy_version: str
    eligible_event_ids: tuple[str, ...]
    excluded_future_event_ids: tuple[str, ...]
    supporting_evidence_ids: tuple[str, ...]
    counter_evidence_ids: tuple[str, ...]
    unknowns: tuple[str, ...]
    data_gaps: tuple[str, ...]


class DateSafeAttributionEngine:
    def evaluate(
        self,
        *,
        context: PriceMoveContext,
        events: tuple[ResearchEvent, ...],
        information_cutoff: datetime,
        policy: AttributionPolicy,
    ) -> AttributionEvaluation:
        _aware(information_cutoff, "information_cutoff")
        if context.window_end > information_cutoff:
            raise ValueError("attribution window cannot extend beyond information cutoff")
        excluded = tuple(
            event.event_id
            for event in events
            if event.available_at > information_cutoff or event.event_at > context.window_end
        )
        eligible = tuple(
            event
            for event in events
            if event.event_at >= context.window_start
            and event.event_at <= context.window_end
            and event.available_at <= information_cutoff
        )
        negative = tuple(event for event in eligible if event.direction == EventDirection.NEGATIVE)
        company_events = tuple(event for event in negative if event.asset_id == context.asset_id)
        sector_events = tuple(
            event
            for event in negative
            if event.event_type == EventType.SECTOR_POLICY and event.sector == context.sector
        )
        systemic_aligned = _aligned(
            context.asset_return,
            context.market_return,
            policy.market_alignment_tolerance,
        )
        sector_aligned = _aligned(
            context.asset_return,
            context.sector_return,
            policy.sector_alignment_tolerance,
        )

        cause_specs: list[tuple[AttributionCategory, str, tuple[str, ...], float, float]] = []
        if company_events:
            evidence_ids = _unique(
                item for event in company_events for item in event.supporting_evidence_ids
            )
            weight = sum(event.relevance * event.severity * event.confidence for event in company_events)
            cause_specs.append((
                AttributionCategory.EVENT,
                "date-eligible company-specific adverse event(s)",
                evidence_ids,
                weight,
                max(event.confidence for event in company_events),
            ))
        if sector_events:
            evidence_ids = _unique(
                item for event in sector_events for item in event.supporting_evidence_ids
            )
            weight = sum(event.relevance * event.severity * event.confidence for event in sector_events)
            cause_specs.append((
                AttributionCategory.POLICY,
                "date-eligible sector-policy event",
                evidence_ids,
                weight,
                max(event.confidence for event in sector_events),
            ))
        if systemic_aligned and context.market_evidence_id:
            cause_specs.append((
                AttributionCategory.LIQUIDITY,
                "asset decline aligned with broad-market decline",
                (context.market_evidence_id,),
                1.0,
                policy.price_alignment_confidence,
            ))
        if sector_aligned and context.sector_evidence_id:
            cause_specs.append((
                AttributionCategory.ACTIVE_FLOW,
                "asset decline aligned with sector decline",
                (context.sector_evidence_id,),
                1.0,
                policy.price_alignment_confidence,
            ))

        scope = _scope(company_events, sector_events, systemic_aligned, sector_aligned)
        data_gaps = list(context.data_gaps)
        data_gaps.extend(gap for event in eligible for gap in event.data_gaps)
        if excluded:
            data_gaps.append("post-cutoff events excluded")
        unknowns = list(item for event in eligible for item in event.unknowns)
        if not eligible:
            unknowns.append("absence of eligible event data is not evidence that no event occurred")
        if scope == AttributionScope.INSUFFICIENT_DATA:
            data_gaps.append("insufficient evidence to attribute the price move")
            causes = (
                PriceMoveCause(
                    category=AttributionCategory.UNKNOWN,
                    role=AttributionRole.TRIGGER,
                    permanence=Permanence.UNCERTAIN,
                    description="price-move cause remains unknown",
                    relative_importance=1.0,
                    confidence=0.0,
                    supporting_evidence_ids=(),
                    counter_evidence_ids=(),
                    alternative_explanations=tuple(_unique(unknowns)),
                    next_validation_event="obtain point-in-time market, sector, and issuer evidence",
                ),
            )
        else:
            causes = _build_causes(cause_specs)

        identity = (
            f"{context.asset_id}:{context.window_start.isoformat()}:{context.window_end.isoformat()}:"
            f"{policy.version}:{','.join(event.event_id for event in eligible)}:{scope.value}"
        )
        attribution = PriceMoveAttribution(
            attribution_id=str(uuid5(NAMESPACE_URL, f"price-attribution:{identity}")),
            asset_id=context.asset_id,
            evidence_set_id=str(uuid5(NAMESPACE_URL, f"price-attribution-evidence:{identity}")),
            window_start=context.window_start,
            window_end=context.window_end,
            causes=causes,
            created_at=information_cutoff,
        )
        supporting = _unique(item for cause in causes for item in cause.supporting_evidence_ids)
        counter = _unique(item for event in eligible for item in event.counter_evidence_ids)
        return AttributionEvaluation(
            scope=scope,
            attribution=attribution,
            policy_version=policy.version,
            eligible_event_ids=tuple(event.event_id for event in eligible),
            excluded_future_event_ids=excluded,
            supporting_evidence_ids=supporting,
            counter_evidence_ids=counter,
            unknowns=tuple(_unique(unknowns)),
            data_gaps=tuple(_unique(data_gaps)),
        )


def _aligned(asset_return: float | None, reference_return: float | None, tolerance: float) -> bool:
    return (
        asset_return is not None
        and reference_return is not None
        and asset_return < 0
        and reference_return < 0
        and abs(asset_return - reference_return) <= tolerance
    )


def _scope(
    company_events: tuple[ResearchEvent, ...],
    sector_events: tuple[ResearchEvent, ...],
    systemic_aligned: bool,
    sector_aligned: bool,
) -> AttributionScope:
    categories = set()
    if company_events:
        categories.add(AttributionScope.COMPANY_SPECIFIC)
    if sector_events or sector_aligned:
        categories.add(AttributionScope.SECTOR)
    if systemic_aligned:
        categories.add(AttributionScope.MARKET_SYSTEMIC)
    if len(categories) > 1:
        return AttributionScope.MIXED
    return next(iter(categories), AttributionScope.INSUFFICIENT_DATA)


def _build_causes(
    specs: list[tuple[AttributionCategory, str, tuple[str, ...], float, float]],
) -> tuple[PriceMoveCause, ...]:
    total_weight = sum(max(spec[3], 0.000001) for spec in specs)
    return tuple(
        PriceMoveCause(
            category=category,
            role=AttributionRole.TRIGGER if index == 0 else AttributionRole.AMPLIFIER,
            permanence=Permanence.UNCERTAIN,
            description=description,
            relative_importance=round(max(weight, 0.000001) / total_weight, 8),
            confidence=confidence,
            supporting_evidence_ids=evidence_ids,
            counter_evidence_ids=(),
            alternative_explanations=(),
            next_validation_event="review the next primary disclosure or market close",
        )
        for index, (category, description, evidence_ids, weight, confidence) in enumerate(specs)
    )


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
