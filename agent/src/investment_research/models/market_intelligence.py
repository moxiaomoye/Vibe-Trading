"""Market Intelligence Layer (Phase 1).

A pure, deterministic market state engine that consumes the point-in-time
market snapshot carried by ``ResearchContext`` and produces a typed Market
Intelligence Contract. It never produces buy/sell advice: the contract is a
state judgement (``NORMAL`` / ``STRESS`` / ``PANIC`` / ``EXTREME_PANIC``) plus
per-dimension evidence, so a human researcher can inspect why a state was
reached.

Availability is part of the contract: dimensions the current provider schema
cannot supply (volatility, ERP) are reported as ``UNAVAILABLE`` instead of
silently contributing zero signal, and the state falls back to ``UNKNOWN``
when no available evidence exists. No future data is ever used (the engine
only reads the as-of snapshot) and results are reproducible: identical
snapshots produce identical verdicts.
"""

from __future__ import annotations

from enum import StrEnum
from statistics import median
from typing import Any

from pydantic import BaseModel, Field

from .data_quality import DataQualityStatus

MARKET_INTELLIGENCE_VERSION = "market-intel-v1"

TOTAL_DIMENSIONS = 6


class MarketState(StrEnum):
    """State judgement of the market intelligence contract."""

    NORMAL = "NORMAL"
    STRESS = "STRESS"
    PANIC = "PANIC"
    EXTREME_PANIC = "EXTREME_PANIC"
    UNKNOWN = "UNKNOWN"
    """No sufficient evidence at the point in time; data gaps are visible."""


class MarketDimension(StrEnum):
    """One evidence dimension of the market intelligence contract."""

    INDEX = "index"
    BREADTH = "breadth"
    LIMIT = "limit"
    TURNOVER = "turnover"
    VOLATILITY = "volatility"
    ERP = "erp"


class MarketDimensionVerdict(BaseModel):
    """Evidence verdict for one dimension at the research point in time."""

    dimension: MarketDimension
    status: DataQualityStatus
    observed: float | None = None
    threshold: float | None = None
    triggered: bool | None = None
    note: str | None = None


class MarketIntelligenceConfig(BaseModel):
    """Frozen, auditable engine thresholds (never env-mutated at runtime)."""

    version: str = MARKET_INTELLIGENCE_VERSION
    index_daily_return_pct: float = -2.0
    index_drawdown_pct: float = -20.0
    advancer_ratio: float = 0.30
    above_ma60_ratio: float = 0.35
    min_limit_down_count: int = 50
    turnover_zscore: float = 1.5
    weights: dict[MarketDimension, float] = Field(
        default_factory=lambda: {
            MarketDimension.INDEX: 35.0,
            MarketDimension.BREADTH: 25.0,
            MarketDimension.LIMIT: 20.0,
            MarketDimension.TURNOVER: 10.0,
            MarketDimension.VOLATILITY: 5.0,
            MarketDimension.ERP: 5.0,
        }
    )
    stress_band_low: int = 40
    panic_band_low: int = 60
    extreme_band_low: int = 80


class MarketIntelligence(BaseModel):
    """The Market Intelligence Contract attached to every research artifact."""

    version: str = MARKET_INTELLIGENCE_VERSION
    thresholds_version: str = MARKET_INTELLIGENCE_VERSION
    state: MarketState
    stress_score: int | None = None
    coverage: dict[str, int] = Field(default_factory=dict)
    dimensions: list[MarketDimensionVerdict] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


def _index_signals(market: Any) -> tuple[float | None, float | None, int, int, int]:
    returns = [float(item.daily_return_pct) for item in market.indices]
    drawdowns = [float(item.drawdown_252_pct) for item in market.indices]
    below_ma = sum(1 for item in market.indices if item.below_ma250)
    below_low = sum(1 for item in market.indices if item.below_120d_low)
    return (
        median(returns) if returns else None,
        median(drawdowns) if drawdowns else None,
        below_ma,
        below_low,
        len(market.indices),
    )


def evaluate_market_intelligence(
    market: Any,
    config: MarketIntelligenceConfig | None = None,
) -> MarketIntelligence:
    """Judge market state from the as-of market snapshot (pure, no I/O).

    ``market`` is a ``MarketSnapshotModel`` (the typed snapshot inside
    ``ResearchContext``). Dimensions whose inputs are absent are reported as
    ``UNAVAILABLE`` with a visible note; the stress score is renormalized over
    the available evidence weight only.
    """
    config = config or MarketIntelligenceConfig()
    dimensions: list[MarketDimensionVerdict] = []
    summary: list[str] = []

    median_return, median_drawdown, below_ma, below_low, index_count = _index_signals(market)
    if index_count == 0:
        index_triggered = False
        index_status = DataQualityStatus.UNAVAILABLE
        index_note = "无指数行情（快照为空）"
    else:
        index_triggered = (
            (median_return is not None and median_return <= config.index_daily_return_pct)
            or (median_drawdown is not None and median_drawdown <= config.index_drawdown_pct)
            or below_ma == index_count
            or below_low == index_count
        )
        index_status = DataQualityStatus.AVAILABLE
        index_note = None
    dimensions.append(MarketDimensionVerdict(
        dimension=MarketDimension.INDEX,
        status=index_status,
        observed=median_return,
        threshold=config.index_daily_return_pct,
        triggered=index_triggered,
        note=index_note,
    ))
    if index_triggered:
        summary.append(
            f"指数：中位日跌幅{median_return:.1f}%（阈值{config.index_daily_return_pct:.1f}%），"
            f"回撤中位{median_drawdown:.1f}%（阈值{config.index_drawdown_pct:.1f}%）"
        )

    advancer = market.advancer_ratio
    ma60 = market.above_ma60_ratio
    if advancer is None and ma60 is None:
        breadth_triggered = None
        breadth_status = DataQualityStatus.UNAVAILABLE
        breadth_note = "宽度数据未提供"
    else:
        breadth_triggered = (
            (advancer is not None and advancer <= config.advancer_ratio)
            or (advancer is None and ma60 is not None and ma60 <= config.above_ma60_ratio)
        )
        breadth_status = DataQualityStatus.AVAILABLE
        breadth_note = None
    dimensions.append(MarketDimensionVerdict(
        dimension=MarketDimension.BREADTH,
        status=breadth_status,
        observed=advancer,
        threshold=config.advancer_ratio,
        triggered=breadth_triggered,
        note=breadth_note,
    ))
    if breadth_triggered:
        if advancer is not None:
            summary.append(f"宽度：上涨占比{advancer:.0%}（阈值{config.advancer_ratio:.0%}）")
        else:
            summary.append(
                f"宽度：60日线以上占比{ma60:.0%}（阈值{config.above_ma60_ratio:.0%}）"
            )

    limit_down = market.limit_down_count
    if limit_down is None:
        limit_triggered = None
        limit_status = DataQualityStatus.UNAVAILABLE
        limit_note = "跌停数量未提供（历史回溯为Data Gap）"
    else:
        limit_triggered = limit_down >= config.min_limit_down_count
        limit_status = DataQualityStatus.AVAILABLE
        limit_note = None
    dimensions.append(MarketDimensionVerdict(
        dimension=MarketDimension.LIMIT,
        status=limit_status,
        observed=float(limit_down) if limit_down is not None else None,
        threshold=float(config.min_limit_down_count),
        triggered=limit_triggered,
        note=limit_note,
    ))
    if limit_triggered:
        summary.append(f"涨跌停：跌停{limit_down}家（阈值{config.min_limit_down_count}家）")

    turnover_z = market.turnover_zscore
    if turnover_z is None:
        turnover_triggered = None
        turnover_status = DataQualityStatus.UNAVAILABLE
        turnover_note = (
            "成交额分位（zscore）未接入历史数据；成交额无基线不可判定异常"
        )
    else:
        turnover_triggered = turnover_z >= config.turnover_zscore
        turnover_status = DataQualityStatus.AVAILABLE
        turnover_note = None
    dimensions.append(MarketDimensionVerdict(
        dimension=MarketDimension.TURNOVER,
        status=turnover_status,
        observed=turnover_z,
        threshold=config.turnover_zscore,
        triggered=turnover_triggered,
        note=turnover_note,
    ))
    if turnover_triggered:
        summary.append(f"成交异常：成交额分位{turnover_z:.1f}（阈值{config.turnover_zscore:.1f}）")

    for dimension, note in (
        (MarketDimension.VOLATILITY, "波动率维度预留：当前 Provider Schema 未提供该输入"),
        (MarketDimension.ERP, "ERP 维度预留：当前 Provider Schema 未提供该输入"),
    ):
        dimensions.append(MarketDimensionVerdict(
            dimension=dimension,
            status=DataQualityStatus.UNAVAILABLE,
            triggered=None,
            note=note,
        ))

    available_weight = sum(
        config.weights[verdict.dimension]
        for verdict in dimensions
        if verdict.status is DataQualityStatus.AVAILABLE
    )
    triggered_weight = sum(
        config.weights[verdict.dimension]
        for verdict in dimensions
        if verdict.status is DataQualityStatus.AVAILABLE and verdict.triggered
    )
    coverage = {
        "available": sum(
            verdict.status is DataQualityStatus.AVAILABLE for verdict in dimensions
        ),
        "total": TOTAL_DIMENSIONS,
    }
    if available_weight <= 0:
        state = MarketState.UNKNOWN
        stress_score = None
        summary.append("可用证据不足，状态不可判定（数据缺口已显式列出）")
    else:
        stress_score = int(round(triggered_weight / available_weight * 100.0))
        if stress_score >= config.extreme_band_low:
            state = MarketState.EXTREME_PANIC
        elif stress_score >= config.panic_band_low:
            state = MarketState.PANIC
        elif stress_score >= config.stress_band_low:
            state = MarketState.STRESS
        else:
            state = MarketState.NORMAL
        summary.append(
            f"状态判定：{state.value}（压力得分{stress_score}，可用证据权重"
            f"{available_weight:.0f}/{sum(config.weights.values()):.0f}）"
        )

    return MarketIntelligence(
        version=config.version,
        thresholds_version=config.version,
        state=state,
        stress_score=stress_score,
        coverage=coverage,
        dimensions=dimensions,
        summary=summary,
    )
