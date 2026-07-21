"""Evidence-bound Market State assessment without a synthetic ranking score."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import MarketRegime
from .models import MarketState


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    snapshot_id: str
    evidence_set_id: str
    as_of: datetime
    broad_index_drawdown: float | None
    index_below_long_trend_ratio: float | None
    advancer_ratio: float | None
    limit_down_count: int | None
    median_daily_return: float | None
    turnover_stress_zscore: float | None
    data_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("market snapshot as_of must be timezone-aware")
        if not self.snapshot_id or not self.evidence_set_id:
            raise ValueError("market snapshot identity and evidence set are required")
        for value, name in (
            (self.index_below_long_trend_ratio, "index_below_long_trend_ratio"),
            (self.advancer_ratio, "advancer_ratio"),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.limit_down_count is not None and self.limit_down_count < 0:
            raise ValueError("limit_down_count cannot be negative")


class MarketStateAssessmentEngine:
    def assess(self, market_state_id: str, snapshot: MarketSnapshot, information_cutoff: datetime) -> MarketState:
        if information_cutoff.tzinfo is None or information_cutoff.utcoffset() is None:
            raise ValueError("information_cutoff must be timezone-aware")
        if snapshot.as_of > information_cutoff:
            raise ValueError("market assessment cannot use a future snapshot")
        observations = (
            snapshot.broad_index_drawdown,
            snapshot.index_below_long_trend_ratio,
            snapshot.advancer_ratio,
            snapshot.limit_down_count,
            snapshot.median_daily_return,
            snapshot.turnover_stress_zscore,
        )
        available = sum(value is not None for value in observations)
        confidence = available / len(observations)
        if available < 3:
            return MarketState(
                market_state_id, MarketRegime.UNKNOWN, snapshot.evidence_set_id, (),
                tuple(dict.fromkeys((*snapshot.data_gaps, "insufficient_market_coverage"))), confidence, snapshot.as_of,
            )

        severe, stress, drivers = 0, 0, []
        if snapshot.broad_index_drawdown is not None:
            if snapshot.broad_index_drawdown <= -0.25:
                severe += 1
                drivers.append(f"broad index drawdown {snapshot.broad_index_drawdown:.1%}")
            elif snapshot.broad_index_drawdown <= -0.12:
                stress += 1
                drivers.append(f"broad index correction {snapshot.broad_index_drawdown:.1%}")
        if snapshot.index_below_long_trend_ratio is not None:
            if snapshot.index_below_long_trend_ratio >= 0.8:
                severe += 1
                drivers.append("most tracked indices are below long-term trend")
            elif snapshot.index_below_long_trend_ratio >= 0.6:
                stress += 1
                drivers.append("a majority of tracked indices are below long-term trend")
        if snapshot.advancer_ratio is not None:
            if snapshot.advancer_ratio <= 0.15:
                severe += 1
                drivers.append(f"market breadth collapsed to {snapshot.advancer_ratio:.0%} advancers")
            elif snapshot.advancer_ratio <= 0.35:
                stress += 1
                drivers.append(f"market breadth weakened to {snapshot.advancer_ratio:.0%} advancers")
        if snapshot.limit_down_count is not None:
            if snapshot.limit_down_count >= 100:
                severe += 1
                drivers.append(f"{snapshot.limit_down_count} limit-down securities")
            elif snapshot.limit_down_count >= 20:
                stress += 1
                drivers.append(f"{snapshot.limit_down_count} limit-down securities")
        if snapshot.median_daily_return is not None:
            if snapshot.median_daily_return <= -0.05:
                severe += 1
                drivers.append(f"median daily return {snapshot.median_daily_return:.1%}")
            elif snapshot.median_daily_return <= -0.02:
                stress += 1
                drivers.append(f"median daily return {snapshot.median_daily_return:.1%}")
        if snapshot.turnover_stress_zscore is not None and snapshot.turnover_stress_zscore >= 2:
            stress += 1
            drivers.append("turnover is more than two standard deviations from its reference window")

        if severe >= 3:
            regime = MarketRegime.PANIC
        elif severe >= 2 or severe + stress >= 4:
            regime = MarketRegime.SYSTEMIC_STRESS
        elif severe + stress >= 2:
            regime = MarketRegime.CORRECTION
        else:
            regime = MarketRegime.NORMAL
            drivers.append("available indicators do not show correlated broad-market stress")
        return MarketState(
            market_state_id, regime, snapshot.evidence_set_id, tuple(drivers), snapshot.data_gaps,
            confidence, snapshot.as_of,
        )
