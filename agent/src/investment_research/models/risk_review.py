"""Stock Risk Analyzer (Phase 4) - value-trap Risk Review contract.

A pure, deterministic risk review engine that consumes one candidate's
point-in-time observation and produces a typed ``RiskReview``. Its only job is
to surface value-trap risks (financial anomaly / cashflow / leverage /
shareholder / profitability deterioration) as evidence for a human researcher:
it never emits a buy/sell/rating directive and never blocks a human decision.

Inputs the current provider schema cannot supply (e.g. debt/leverage) are
reported as explicit data gaps instead of silent zeros, matching the contract
conventions of Phases 1-3.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, Field

RISK_REVIEW_VERSION = "risk-review-v1"

TOTAL_RISK_DIMENSIONS = 5


class RiskSeverity(StrEnum):
    """Severity of one risk finding. Overall level is the maximum finding."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskDimension(StrEnum):
    """One value-trap risk dimension."""

    FINANCIAL_ANOMALY = "financial_anomaly"
    """立案调查/财务造假/非标审计/退市/资不抵债等公告异常."""
    CASHFLOW = "cashflow"
    """经营现金流与净利润的背离（盈利含金量）."""
    LEVERAGE = "leverage"
    """负债/偿债压力（当前 Provider Schema 未提供，显式 Data Gap）."""
    SHAREHOLDER = "shareholder"
    """大股东/控股股东行为风险（如减持）."""
    PROFITABILITY = "profitability"
    """盈利恶化（净利润增长/ROE 转负）."""


class RiskFinding(BaseModel):
    """Evidence verdict for one risk dimension at the research point in time."""

    dimension: RiskDimension
    severity: RiskSeverity
    triggered: bool
    observed: float | None = None
    threshold: float | None = None
    evidence: list[str] = Field(default_factory=list)
    gap: bool = False
    """True when the dimension has no provider input and is an explicit Data Gap."""
    note: str | None = None


class RiskReviewConfig(BaseModel):
    """Frozen, auditable risk thresholds (never env-mutated at runtime)."""

    version: str = RISK_REVIEW_VERSION
    cashflow_medium_ratio: float = 0.8
    cashflow_high_ratio: float = 0.5
    profit_decline_medium_pct: float = -5.0
    profit_decline_high_pct: float = -20.0
    roe_negative_pct: float = 0.0
    anomaly_critical_flags: frozenset[str] = frozenset({
        "investigation", "fraud", "qualified_audit", "delisting", "negative_equity",
    })
    anomaly_medium_flags: frozenset[str] = frozenset({"inquiry"})
    shareholder_flags: frozenset[str] = frozenset({"shareholder_reduction"})
    profitability_decline_flags: frozenset[str] = frozenset({"profit_decline"})


class RiskReview(BaseModel):
    """The typed risk review attached to every researched candidate."""

    version: str = RISK_REVIEW_VERSION
    risk_level: RiskSeverity
    coverage: dict[str, int] = Field(default_factory=dict)
    dimensions: list[RiskFinding] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


def _flags(observation: Mapping[str, Any]) -> set[str]:
    return {str(flag) for flag in (observation.get("risk_flags") or [])}


def evaluate_risk_review(
    observation: Mapping[str, Any],
    config: RiskReviewConfig | None = None,
) -> RiskReview:
    """Review one candidate's value-trap risk (pure, no I/O).

    ``observation`` is the candidate observation block of the scan payload
    (candidate-level dict). Output is a typed Risk Review: severity findings
    per dimension, overall level = max finding severity, explicit gaps for
    dimensions the provider schema cannot supply. Never a rating directive.
    """
    config = config or RiskReviewConfig()
    flags = _flags(observation)
    findings: list[RiskFinding] = []
    summary: list[str] = []
    gaps: list[str] = []

    anomaly_hits = sorted(flags & set(config.anomaly_critical_flags))
    inquiry_hits = sorted(flags & set(config.anomaly_medium_flags))
    if anomaly_hits:
        findings.append(RiskFinding(
            dimension=RiskDimension.FINANCIAL_ANOMALY,
            severity=RiskSeverity.CRITICAL,
            triggered=True,
            evidence=anomaly_hits,
            note="公告级财务异常：立案/造假/非标审计/退市/资不抵债",
        ))
        summary.append(f"财务异常(CRITICAL)：{', '.join(anomaly_hits)}")
    elif inquiry_hits:
        findings.append(RiskFinding(
            dimension=RiskDimension.FINANCIAL_ANOMALY,
            severity=RiskSeverity.MEDIUM,
            triggered=True,
            evidence=inquiry_hits,
            note="交易所问询函",
        ))
        summary.append("财务异常(MEDIUM)：交易所问询函")
    else:
        findings.append(RiskFinding(
            dimension=RiskDimension.FINANCIAL_ANOMALY,
            severity=RiskSeverity.LOW,
            triggered=False,
            note="无公告级财务异常证据",
        ))

    shareholder_hits = sorted(flags & set(config.shareholder_flags))
    if shareholder_hits:
        findings.append(RiskFinding(
            dimension=RiskDimension.SHAREHOLDER,
            severity=RiskSeverity.MEDIUM,
            triggered=True,
            evidence=shareholder_hits,
            note="大股东减持计划",
        ))
        summary.append("股东行为(MEDIUM)：大股东减持")
    else:
        findings.append(RiskFinding(
            dimension=RiskDimension.SHAREHOLDER,
            severity=RiskSeverity.LOW,
            triggered=False,
            note="无大股东减持证据",
        ))

    decline_hits = sorted(flags & set(config.profitability_decline_flags))
    profit_growth = observation.get("profit_growth_pct")
    roe = observation.get("roe_5y_median_pct")
    profitability_triggered = False
    profitability_severity = RiskSeverity.LOW
    if decline_hits:
        profitability_triggered = True
        profitability_severity = RiskSeverity.HIGH
    if profit_growth is not None and profit_growth <= config.profit_decline_high_pct:
        profitability_triggered = True
        profitability_severity = RiskSeverity.HIGH
    elif profit_growth is not None and profit_growth <= config.profit_decline_medium_pct:
        profitability_triggered = True
        profitability_severity = RiskSeverity.MEDIUM
    if roe is not None and roe < config.roe_negative_pct:
        profitability_triggered = True
        profitability_severity = RiskSeverity.HIGH
    profitability_evidence = decline_hits + [
        f"净利润增长{profit_growth:.1f}%" if profit_growth is not None else None,
        f"五年ROE中位{roe:.1f}%" if roe is not None else None,
    ]
    profitability_evidence = [item for item in profitability_evidence if item]
    findings.append(RiskFinding(
        dimension=RiskDimension.PROFITABILITY,
        severity=profitability_severity,
        triggered=profitability_triggered,
        observed=profit_growth,
        threshold=config.profit_decline_high_pct,
        evidence=profitability_evidence,
        note="盈利恶化证据" if profitability_triggered else "盈利未见恶化证据",
    ))
    if profitability_triggered:
        summary.append(
            f"盈利恶化({profitability_severity.value})：{'; '.join(profitability_evidence) or '公告业绩预亏'}"
        )
    if profit_growth is None and not decline_hits:
        gaps.append("profit_growth_pct")
    if roe is None and not decline_hits:
        gaps.append("roe_5y_median_pct")

    cashflow = observation.get("operating_cashflow_to_profit")
    if cashflow is None:
        findings.append(RiskFinding(
            dimension=RiskDimension.CASHFLOW,
            severity=RiskSeverity.LOW,
            triggered=False,
            gap=True,
            note="经营现金流/净利润数据未提供（显式Data Gap）",
        ))
        gaps.append("operating_cashflow_to_profit")
    else:
        if cashflow < config.cashflow_high_ratio:
            cashflow_severity = RiskSeverity.HIGH
            cashflow_note = f"盈利含金量低：现金流/净利润{cashflow:.2f}"
        elif cashflow < config.cashflow_medium_ratio:
            cashflow_severity = RiskSeverity.MEDIUM
            cashflow_note = f"盈利含金量偏低：现金流/净利润{cashflow:.2f}"
        else:
            cashflow_severity = RiskSeverity.LOW
            cashflow_note = "经营现金流覆盖净利润"
        findings.append(RiskFinding(
            dimension=RiskDimension.CASHFLOW,
            severity=cashflow_severity,
            triggered=cashflow_severity is not RiskSeverity.LOW,
            observed=cashflow,
            threshold=config.cashflow_medium_ratio,
            note=cashflow_note,
        ))
        if cashflow_severity is not RiskSeverity.LOW:
            summary.append(f"现金流({cashflow_severity.value})：现金流/净利润{cashflow:.2f}")

    findings.append(RiskFinding(
        dimension=RiskDimension.LEVERAGE,
        severity=RiskSeverity.LOW,
        triggered=False,
        gap=True,
        note="负债/偿债数据源未接入（显式Data Gap）",
    ))
    gaps.append("leverage_data")

    severity_order = (RiskSeverity.LOW, RiskSeverity.MEDIUM, RiskSeverity.HIGH, RiskSeverity.CRITICAL)
    risk_level = max((finding.severity for finding in findings), key=severity_order.index)
    coverage = {
        "evaluated": sum(not finding.gap for finding in findings),
        "triggered": sum(finding.triggered for finding in findings),
        "total": TOTAL_RISK_DIMENSIONS,
    }
    if gaps:
        summary.append(f"数据缺口（显式保留）：{', '.join(sorted(set(gaps)))}")
    summary.append(f"风险审查等级：{risk_level.value}（最高维度严重度，非买入评级）")

    return RiskReview(
        version=config.version,
        risk_level=risk_level,
        coverage=coverage,
        dimensions=findings,
        data_gaps=sorted(set(gaps)),
        summary=summary,
    )
