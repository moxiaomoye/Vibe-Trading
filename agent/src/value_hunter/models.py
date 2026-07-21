"""Domain models for Value Hunter.

The module deliberately separates observable inputs from derived scores.  This
makes historical, point-in-time fixtures testable and prevents an LLM from
silently changing screening rules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class IndexObservation:
    symbol: str
    name: str
    close: float
    daily_return_pct: float
    drawdown_252_pct: float
    below_ma250: bool
    below_120d_low: bool


@dataclass(slots=True)
class MarketObservation:
    as_of: str
    indices: list[IndexObservation]
    advancer_ratio: float | None
    above_ma60_ratio: float | None
    limit_down_count: int | None
    turnover_zscore: float | None
    source: str
    coverage: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateObservation:
    symbol: str
    name: str
    sector: str
    theme: str
    market_cap_billion: float | None = None
    industry_market_cap_rank: int | None = None
    important_index_member: bool = False
    roe_5y_median_pct: float | None = None
    operating_cashflow_to_profit: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    pe_history_percentile: float | None = None
    pe_industry_percentile: float | None = None
    revenue_growth_pct: float | None = None
    profit_growth_pct: float | None = None
    drawdown_252_pct: float | None = None
    relative_to_sector_pct: float | None = None
    turnover_percentile: float | None = None
    risk_flags: list[str] = field(default_factory=list)
    risk_evidence: list[str] = field(default_factory=list)
    source_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoreBreakdown:
    quality: float
    valuation: float
    fundamentals: float
    dislocation: float
    risk_cleanliness: float

    @property
    def total(self) -> float:
        return round(
            self.quality
            + self.valuation
            + self.fundamentals
            + self.dislocation
            + self.risk_cleanliness,
            1,
        )


@dataclass(slots=True)
class CandidateResult:
    observation: CandidateObservation
    score: ScoreBreakdown
    bucket: str
    status: str
    reasons: list[str]
    first_rejection: str
    missing_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["score"]["total"] = self.score.total
        return result


@dataclass(slots=True)
class MarketResult:
    observation: MarketObservation
    score: float
    level: str
    components: dict[str, float]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation": asdict(self.observation),
            "score": self.score,
            "level": self.level,
            "components": self.components,
            "reasons": self.reasons,
        }


@dataclass(slots=True)
class ScanResult:
    run_id: str
    started_at: str
    completed_at: str
    mode: str
    market: MarketResult
    candidates: list[CandidateResult]
    notification_required: bool
    notification_reason: str
    errors: list[str] = field(default_factory=list)

    @classmethod
    def started(cls, run_id: str, mode: str, market: MarketResult) -> "ScanResult":
        now = datetime.now(timezone.utc).isoformat()
        return cls(run_id, now, now, mode, market, [], False, "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "mode": self.mode,
            "market": self.market.to_dict(),
            "candidates": [item.to_dict() for item in self.candidates],
            "notification_required": self.notification_required,
            "notification_reason": self.notification_reason,
            "errors": self.errors,
        }
