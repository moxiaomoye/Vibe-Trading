"""Regime Detection (Phase 2) - Macro State Contract.

A pure, deterministic regime judgement engine built contract-first: it only
consumes the point-in-time macro snapshot and produces a typed ``MarketRegime``
contract. Macro data sources are not wired yet, so the contract exists today
to (a) freeze the schema and thresholds, and (b) guarantee that absent
evidence yields ``UNKNOWN`` with explicit gaps instead of silence.

Regime is a categorical judgement, not a stress continuum: the three crisis
regimes differ in nature (liquidity shock / earnings downgrade wave /
structural risk repricing), so classification is a documented priority order
rather than a score band. No future data is used and no trading directive is
ever emitted.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .data_quality import DataQualityStatus

MARKET_REGIME_VERSION = "market-regime-v1"

TOTAL_MACRO_DIMENSIONS = 5


class Regime(StrEnum):
    """Categorical market regime judgement of the macro contract."""

    LIQUIDITY_PANIC = "LIQUIDITY_PANIC"
    """Money-market stress (e.g. funding spread spike) is the dominant trigger."""
    EARNINGS_DOWNGRADE = "EARNINGS_DOWNGRADE"
    """Aggregate earnings revision wave is the dominant trigger."""
    STRUCTURAL_REPRICING = "STRUCTURAL_REPRICING"
    """Risk premium / rates repricing (ERP, credit spread, rate shock) dominates."""
    STABLE = "STABLE"
    """No macro dimension triggered on the available evidence."""
    UNKNOWN = "UNKNOWN"
    """Insufficient evidence at the point in time; data gaps are visible."""


class MacroDimension(StrEnum):
    """One evidence dimension of the macro regime contract."""

    RATE = "rate"
    LIQUIDITY = "liquidity"
    ERP = "erp"
    EARNINGS = "earnings"
    CREDIT = "credit"


class MacroSnapshotModel(BaseModel):
    """Point-in-time macro inputs. All dimensions optional: a missing input is
    a visible Data Gap, never a silent zero."""

    as_of: str
    source: str = "unknown"
    coverage: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_fields: list[str] = Field(default_factory=list)
    rate_change_bp: float | None = None
    """Recent policy/benchmark rate move in basis points (positive = tightening)."""
    liquidity_gap_bp: float | None = None
    """Money-market funding spread in basis points (e.g. R007 over OMO rate)."""
    equity_risk_premium_pct: float | None = None
    """Implied equity risk premium in percent."""
    earnings_revision_pct: float | None = None
    """Aggregate EPS forecast revision in percent (negative = downgrade wave)."""
    credit_spread_bp: float | None = None
    """Corporate credit spread in basis points."""


class RegimeVerdict(BaseModel):
    """Evidence verdict for one macro dimension at the research point in time."""

    dimension: MacroDimension
    status: DataQualityStatus
    observed: float | None = None
    threshold: float | None = None
    triggered: bool | None = None
    note: str | None = None


class MarketRegimeConfig(BaseModel):
    """Frozen, auditable regime thresholds (never env-mutated at runtime)."""

    version: str = MARKET_REGIME_VERSION
    rate_hike_bp: float = 50.0
    liquidity_gap_bp: float = 100.0
    erp_pct: float = 5.0
    earnings_revision_pct: float = -3.0
    credit_spread_bp: float = 200.0
    weights: dict[MacroDimension, float] = Field(
        default_factory=lambda: {
            MacroDimension.RATE: 30.0,
            MacroDimension.LIQUIDITY: 25.0,
            MacroDimension.ERP: 20.0,
            MacroDimension.EARNINGS: 15.0,
            MacroDimension.CREDIT: 10.0,
        }
    )


class MarketRegime(BaseModel):
    """The Regime Detection Contract attached to research artifacts."""

    version: str = MARKET_REGIME_VERSION
    thresholds_version: str = MARKET_REGIME_VERSION
    regime: Regime
    coverage: dict[str, int] = Field(default_factory=dict)
    dimensions: list[RegimeVerdict] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


def evaluate_market_regime(
    macro: MacroSnapshotModel,
    config: MarketRegimeConfig | None = None,
) -> MarketRegime:
    """Judge the market regime from the as-of macro snapshot (pure, no I/O).

    Dimensions whose inputs are absent are reported ``UNAVAILABLE``; estimated
    inputs are labelled and excluded from the available evidence weight, exactly
    like the Phase 1 market state engine. Regime priority (documented): liquidity
    shock > earnings downgrade wave > structural repricing.
    """
    config = config or MarketRegimeConfig()
    verdicts: list[RegimeVerdict] = []
    summary: list[str] = []
    estimated = set(macro.estimated_fields)

    _evaluated: list[tuple[MacroDimension, float | None, float, str, str]] = [
        (MacroDimension.RATE, macro.rate_change_bp, config.rate_hike_bp,
         "利率上行冲击（加息/收益率大幅上行）", "rate_change_bp"),
        (MacroDimension.LIQUIDITY, macro.liquidity_gap_bp, config.liquidity_gap_bp,
         "货币市场资金面压力（融资利差走阔）", "liquidity_gap_bp"),
        (MacroDimension.ERP, macro.equity_risk_premium_pct, config.erp_pct,
         "股权风险溢价（ERP）抬升", "equity_risk_premium_pct"),
        (MacroDimension.EARNINGS, macro.earnings_revision_pct, config.earnings_revision_pct,
         "盈利预测下调潮（EPS 修正为负）", "earnings_revision_pct"),
        (MacroDimension.CREDIT, macro.credit_spread_bp, config.credit_spread_bp,
         "信用利差走阔", "credit_spread_bp"),
    ]
    for dimension, observed, threshold, label, field in _evaluated:
        if observed is None:
            verdicts.append(RegimeVerdict(
                dimension=dimension,
                status=DataQualityStatus.UNAVAILABLE,
                note=f"{label}：数据未接入，为显式Data Gap",
            ))
            continue
        if field in estimated:
            status = DataQualityStatus.ESTIMATED
            note = "显式估计输入（非市场统计）"
        else:
            status = DataQualityStatus.AVAILABLE
            note = None
        if dimension is MacroDimension.EARNINGS:
            triggered = observed <= threshold
        else:
            triggered = observed >= threshold
        verdicts.append(RegimeVerdict(
            dimension=dimension,
            status=status,
            observed=observed,
            threshold=threshold,
            triggered=triggered,
            note=note,
        ))
        if triggered:
            summary.append(f"{label}：观测{observed:g}（阈值{threshold:g}）")

    available_weight = sum(
        config.weights[verdict.dimension]
        for verdict in verdicts
        if verdict.status is DataQualityStatus.AVAILABLE
    )
    triggered: set[MacroDimension] = {
        verdict.dimension for verdict in verdicts
        if verdict.status is DataQualityStatus.AVAILABLE and verdict.triggered
    }
    coverage = {
        "available": sum(
            verdict.status is DataQualityStatus.AVAILABLE for verdict in verdicts
        ),
        "estimated": sum(
            verdict.status is DataQualityStatus.ESTIMATED for verdict in verdicts
        ),
        "total": TOTAL_MACRO_DIMENSIONS,
    }

    if available_weight <= 0:
        regime = Regime.UNKNOWN
        summary.append("可用宏观证据不足，状态不可判定（数据缺口已显式列出）")
    elif MacroDimension.LIQUIDITY in triggered:
        regime = Regime.LIQUIDITY_PANIC
    elif MacroDimension.EARNINGS in triggered:
        regime = Regime.EARNINGS_DOWNGRADE
    elif triggered & {MacroDimension.RATE, MacroDimension.ERP, MacroDimension.CREDIT}:
        regime = Regime.STRUCTURAL_REPRICING
    else:
        regime = Regime.STABLE
    if regime is not Regime.UNKNOWN:
        summary.append(
            f"Regime判定：{regime.value}（可用证据维度{available_weight:.0f}/"
            f"{sum(config.weights.values()):.0f}，优先级 流动性>盈利>重定价）"
        )

    return MarketRegime(
        version=config.version,
        thresholds_version=config.version,
        regime=regime,
        coverage=coverage,
        dimensions=verdicts,
        summary=summary,
    )
