"""Unified research context model (Task 1).

``ResearchContext`` types the existing scan/research payloads (the same data
shape produced by ``ValueHunterService`` and consumed by ``research_mvp``)
into one pure Pydantic data object. It performs no I/O: it only validates and
re-expresses already-fetched data.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from typing import Any, Mapping

from pydantic import BaseModel, Field

from .artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactMetadata,
    compute_content_hash,
    compute_data_snapshot_id,
    make_research_id,
    make_research_run_id,
    provider_version_for,
)
from .data_quality import (
    DataQualityIssue,
    DataQualityReport,
    DataQualityStatus,
    classify_data_quality,
)
from .fear_memory import (
    FEAR_MEMORY_VERSION,
    FearMemory,
    query_fear_memory,
)
from .market_intelligence import (
    MARKET_INTELLIGENCE_VERSION,
    MarketIntelligence,
    MarketState,
    evaluate_market_intelligence,
)
from .market_regime import (
    MARKET_REGIME_VERSION,
    MacroSnapshotModel,
    MarketRegime,
    Regime,
    evaluate_market_regime,
)
from .rules_version import current_rules_version, rules_fingerprint

_MARKET_SUMMARY_FIELDS = (
    "advancer_count",
    "decliner_count",
    "limit_up_count",
    "limit_down_count",
    "advancer_ratio",
    "above_ma60_ratio",
    "turnover_zscore",
    "turnover_amount",
)

_WARNING_KEYWORDS = {
    "limit_down_count": ("跌停", "limit_down"),
    "limit_up_count": ("涨停", "limit_up"),
    "turnover_zscore": ("成交额", "turnover", "成交"),
    "turnover_amount": ("成交额", "turnover"),
}


class IndexSnapshotModel(BaseModel):
    symbol: str
    name: str
    close: float
    daily_return_pct: float
    drawdown_252_pct: float
    below_ma250: bool
    below_120d_low: bool


class MarketSnapshotModel(BaseModel):
    as_of: str
    indices: list[IndexSnapshotModel] = Field(default_factory=list)
    advancer_ratio: float | None = None
    above_ma60_ratio: float | None = None
    limit_down_count: int | None = None
    turnover_zscore: float | None = None
    advancer_count: int | None = None
    decliner_count: int | None = None
    limit_up_count: int | None = None
    turnover_amount: float | None = None
    source: str = "unknown"
    coverage: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    """Fields carrying explicitly-labelled estimates (e.g. watchlist-pool
    limit counts in historical mode). Estimates are never market stats."""


class ValuationSnapshotModel(BaseModel):
    """Point-in-time valuation/quality values for one candidate."""

    pe_ttm: float | None = None
    pb: float | None = None
    pe_history_percentile: float | None = None
    pe_industry_percentile: float | None = None
    roe_5y_median_pct: float | None = None
    drawdown_252_pct: float | None = None
    market_cap_billion: float | None = None
    etf_valuation: dict[str, Any] | None = None


class ResearchContext(BaseModel):
    """Pure-data research context for one point-in-time study."""

    research_run_id: str | None = None
    as_of_date: date
    requested_date: date
    market_snapshot: MarketSnapshotModel
    macro_snapshot: MacroSnapshotModel | None = None
    """Point-in-time macro inputs for Regime Detection (Phase 2). Data sources
    are not wired yet: absent means the regime block reports UNKNOWN with an
    explicit gap, never a silent guess."""
    valuation_snapshot: dict[str, ValuationSnapshotModel] = Field(default_factory=dict)
    data_quality: DataQualityReport = Field(default_factory=DataQualityReport)
    market_intelligence: MarketIntelligence | None = None
    market_regime: MarketRegime | None = None
    fear_memory: FearMemory | None = None
    """Historical Crisis Library visible at this research point in time
    (PIT-filtered; future episodes never leak into the past)."""
    artifact_metadata: ArtifactMetadata

    @classmethod
    def from_scan_payload(
        cls,
        scan_payload: Mapping[str, Any],
        *,
        requested_date: date | None = None,
        provider: str,
        profile: Mapping[str, Any] | None = None,
    ) -> "ResearchContext":
        """Build the typed context from an existing scan payload (no I/O).

        ``scan_payload`` is the shape produced by ``ScanResult.to_dict()``:
        ``market.observation`` holds the market snapshot and ``candidates``
        hold ``observation`` blocks with valuation/quality fields.
        """
        market = scan_payload.get("market", {})
        observation = market.get("observation", {})
        as_of = observation.get("as_of", "")
        as_of_date = date.fromisoformat(str(as_of)[:10])
        requested = requested_date or as_of_date

        warnings = list(observation.get("warnings", []) or [])
        market_snapshot = MarketSnapshotModel(
            as_of=as_of,
            indices=[
                IndexSnapshotModel(**index)
                for index in observation.get("indices", [])
                if isinstance(index, dict)
            ],
            advancer_ratio=observation.get("advancer_ratio"),
            above_ma60_ratio=observation.get("above_ma60_ratio"),
            limit_down_count=observation.get("limit_down_count"),
            turnover_zscore=observation.get("turnover_zscore"),
            advancer_count=observation.get("advancer_count"),
            decliner_count=observation.get("decliner_count"),
            limit_up_count=observation.get("limit_up_count"),
            turnover_amount=observation.get("turnover_amount"),
            source=str(observation.get("source", "unknown")),
            coverage=list(observation.get("coverage", []) or []),
            warnings=warnings,
            estimated_fields=list(observation.get("estimated_fields", []) or []),
        )

        valuation_snapshot: dict[str, ValuationSnapshotModel] = {}
        for candidate in scan_payload.get("candidates", []) or []:
            obs = candidate.get("observation", {})
            symbol = obs.get("symbol") or candidate.get("code")
            if not symbol:
                continue
            valuation_snapshot[str(symbol)] = ValuationSnapshotModel(
                pe_ttm=obs.get("pe_ttm"),
                pb=obs.get("pb"),
                pe_history_percentile=obs.get("pe_history_percentile"),
                pe_industry_percentile=obs.get("pe_industry_percentile"),
                roe_5y_median_pct=obs.get("roe_5y_median_pct"),
                drawdown_252_pct=obs.get("drawdown_252_pct"),
                market_cap_billion=obs.get("market_cap_billion"),
                etf_valuation=obs.get("etf_valuation"),
            )

        issues = _market_data_quality_issues(observation, as_of_date)
        for candidate in scan_payload.get("candidates", []) or []:
            obs = candidate.get("observation", {})
            issues.extend(_candidate_data_quality_issues(obs, as_of_date))

        market_intelligence = evaluate_market_intelligence(market_snapshot)
        fear_memory = query_fear_memory(as_of_date)

        macro_block = scan_payload.get("macro")
        macro_snapshot = None
        market_regime = None
        if isinstance(macro_block, dict) and isinstance(macro_block.get("observation"), dict):
            macro_snapshot = MacroSnapshotModel(**macro_block["observation"])
            market_regime = evaluate_market_regime(macro_snapshot)

        created = datetime.now(timezone.utc)
        research_run_id = make_research_run_id(scan_payload)
        artifact = ArtifactMetadata(
            research_id=make_research_id(as_of_date),
            research_run_id=research_run_id,
            created_at=created,
            as_of_date=as_of_date,
            requested_date=requested,
            rules_version=current_rules_version(),
            provider_version=provider_version_for(provider),
            artifact_version=ARTIFACT_SCHEMA_VERSION,
            rules_fingerprint=rules_fingerprint(profile),
            data_snapshot_id=compute_data_snapshot_id(scan_payload),
        )
        return cls(
            research_run_id=research_run_id,
            as_of_date=as_of_date,
            requested_date=requested,
            market_snapshot=market_snapshot,
            valuation_snapshot=valuation_snapshot,
            data_quality=DataQualityReport(issues=issues),
            market_intelligence=market_intelligence,
            market_regime=market_regime,
            macro_snapshot=macro_snapshot,
            fear_memory=fear_memory,
            artifact_metadata=artifact,
        )


def _market_data_quality_issues(
    observation: Mapping[str, Any], as_of: date
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    warnings = list(observation.get("warnings", []) or [])
    estimated = list(observation.get("estimated_fields", []) or [])
    for field in _MARKET_SUMMARY_FIELDS:
        value = observation.get(field)
        if field in estimated and value is not None:
            issues.append(
                classify_data_quality(
                    f"market.{field}",
                    value,
                    estimate_note="基于研究标的池的显式估计（非全市场统计）",
                    as_of=as_of,
                    source=str(observation.get("source", "")),
                )
            )
            continue
        if value is None:
            keywords = _WARNING_KEYWORDS.get(field, ())
            reason = next(
                (warning for warning in warnings if any(k in warning for k in keywords)),
                None,
            )
            issues.append(
                classify_data_quality(
                    f"market.{field}",
                    value,
                    unavailable_reason=reason or "not provided by the market provider",
                    as_of=as_of,
                    source=str(observation.get("source", "")),
                )
            )
    return issues


def _candidate_data_quality_issues(
    observation: Mapping[str, Any], as_of: date
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    symbol = observation.get("symbol", "?")
    missing = list(observation.get("missing_fields", []) or [])
    for field in missing:
        issues.append(
            classify_data_quality(
                f"candidate.{symbol}.{field}",
                None,
                missing_reason="declared missing by the candidate scan",
                as_of=as_of,
            )
        )
    for field in ("current_price", "relative_to_sector_pct", "daily_return_pct"):
        if field not in missing and observation.get(field) is None:
            issues.append(
                classify_data_quality(
                    f"candidate.{symbol}.{field}",
                    None,
                    missing_reason="not provided at the research point in time",
                    as_of=as_of,
                )
            )
    return issues


def attach_contract_metadata(
    scan_payload: Mapping[str, Any],
    report: dict[str, Any],
    *,
    requested_date: date | None = None,
    provider: str | None = None,
    profile: Mapping[str, Any] | None = None,
    context: ResearchContext | None = None,
) -> dict[str, Any]:
    """Attach ``artifact`` and ``data_quality`` blocks to a research report.

    ``context`` is the unified research context when the caller already holds
    one (the typed carrier for live/stored/rebuild paths); otherwise it is
    derived from the legacy ``scan_payload`` dict through the adapter
    (``ResearchContext.from_scan_payload``). Mutates and returns ``report``.
    The artifact ``content_hash`` covers the research content (report minus
    the artifact block itself) and never depends on ``created_at``, so the
    same input snapshot and rules reproduce the same hash.
    """
    if context is None:
        if provider is None:
            raise ValueError("provider is required when context is not provided")
        context = ResearchContext.from_scan_payload(
            scan_payload,
            requested_date=requested_date,
            provider=provider,
            profile=profile,
        )
    content = copy.deepcopy(dict(report))
    content.pop("artifact", None)
    artifact = context.artifact_metadata.model_copy(
        update={"content_hash": compute_content_hash(content)}
    )
    report["artifact"] = artifact.model_dump()
    report["data_quality"] = {
        "issues": [issue.model_dump() for issue in context.data_quality.issues],
        "counts": context.data_quality.counts(),
        "all_available": context.data_quality.all_available(),
    }
    report["research_run_id"] = context.research_run_id
    report["market_intelligence"] = _market_intelligence_block(context)
    report["market_regime"] = _market_regime_block(context)
    report["fear_memory"] = _fear_memory_block(context)
    return report


def _market_intelligence_block(context: ResearchContext) -> dict[str, Any]:
    """Deterministic ``market_intelligence`` block for the report payload."""
    intel = context.market_intelligence
    if intel is not None:
        return intel.model_dump()
    return {
        "version": MARKET_INTELLIGENCE_VERSION,
        "thresholds_version": MARKET_INTELLIGENCE_VERSION,
        "state": MarketState.UNKNOWN.value,
        "stress_score": None,
        "coverage": {"available": 0, "estimated": 0, "total": 6},
        "dimensions": [],
        "summary": ["market intelligence unavailable: context did not carry a market snapshot"],
    }


def _market_regime_block(context: ResearchContext) -> dict[str, Any]:
    """Deterministic ``market_regime`` block for the report payload.

    Macro data sources are not wired yet (Phase 2 contract-first): the block
    always exists, and without a macro snapshot it reports ``UNKNOWN`` with an
    explicit gap instead of silently vanishing.
    """
    regime = context.market_regime
    if regime is not None:
        return regime.model_dump()
    return {
        "version": MARKET_REGIME_VERSION,
        "thresholds_version": MARKET_REGIME_VERSION,
        "regime": Regime.UNKNOWN.value,
        "coverage": {"available": 0, "estimated": 0, "total": 5},
        "dimensions": [],
        "summary": ["market regime unavailable: macro data sources are not wired yet (explicit gap)"],
    }


def _fear_memory_block(context: ResearchContext) -> dict[str, Any]:
    """Deterministic ``fear_memory`` block for the report payload."""
    memory = context.fear_memory
    if memory is not None:
        return memory.model_dump(mode="json")
    return {
        "version": FEAR_MEMORY_VERSION,
        "as_of": context.as_of_date.isoformat(),
        "visible_episodes": [],
        "hidden_episodes_count": 0,
        "summary": ["fear memory unavailable: context did not carry a research date"],
    }
