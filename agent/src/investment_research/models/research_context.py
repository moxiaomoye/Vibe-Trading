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
from .market_intelligence import (
    MARKET_INTELLIGENCE_VERSION,
    MarketIntelligence,
    MarketState,
    evaluate_market_intelligence,
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
    valuation_snapshot: dict[str, ValuationSnapshotModel] = Field(default_factory=dict)
    data_quality: DataQualityReport = Field(default_factory=DataQualityReport)
    market_intelligence: MarketIntelligence | None = None
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
            artifact_metadata=artifact,
        )


def _market_data_quality_issues(
    observation: Mapping[str, Any], as_of: date
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    warnings = list(observation.get("warnings", []) or [])
    for field in _MARKET_SUMMARY_FIELDS:
        value = observation.get(field)
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
        "coverage": {"available": 0, "total": 6},
        "dimensions": [],
        "summary": ["market intelligence unavailable: context did not carry a market snapshot"],
    }
