"""Deterministic market and candidate scoring rules."""

from __future__ import annotations

from statistics import median

from .models import (
    CandidateObservation,
    CandidateResult,
    MarketObservation,
    MarketResult,
    ScoreBreakdown,
)

_REQUIRED_RESEARCH_FIELDS = (
    "roe_5y_median_pct",
    "operating_cashflow_to_profit",
    "pe_history_percentile",
    "revenue_growth_pct",
    "profit_growth_pct",
    "drawdown_252_pct",
)


def _median_index_value(market: MarketObservation, name: str) -> float:
    values = [float(getattr(item, name)) for item in market.indices]
    return median(values) if values else 0.0


def score_market(market: MarketObservation) -> MarketResult:
    """Score observable market stress from 0 to 100."""
    reasons: list[str] = []

    below_ma = sum(item.below_ma250 for item in market.indices)
    below_low = sum(item.below_120d_low for item in market.indices)
    index_count = max(len(market.indices), 1)
    trend = min(18.0, 18.0 * below_ma / index_count) + min(12.0, 12.0 * below_low / index_count)
    if below_ma:
        reasons.append(f"{below_ma}/{index_count}个指数跌破250日均线")
    if below_low:
        reasons.append(f"{below_low}/{index_count}个指数跌破120日低点")

    drawdown = abs(min(0.0, _median_index_value(market, "drawdown_252_pct")))
    if drawdown >= 40:
        drawdown_score = 25.0
    elif drawdown >= 30:
        drawdown_score = 22.0
    elif drawdown >= 20:
        drawdown_score = 15.0
    elif drawdown >= 15:
        drawdown_score = 8.0
    else:
        drawdown_score = max(0.0, drawdown / 15.0 * 8.0)
    if drawdown >= 10:
        reasons.append(f"主要指数一年高点回撤中位数为{drawdown:.1f}%")

    breadth = 0.0
    if market.advancer_ratio is not None:
        breadth += 15.0 if market.advancer_ratio <= 0.2 else 8.0 if market.advancer_ratio <= 0.35 else 0.0
        if market.advancer_ratio <= 0.35:
            reasons.append(f"上涨家数占比仅{market.advancer_ratio:.0%}")
    if market.above_ma60_ratio is not None:
        breadth += 10.0 if market.above_ma60_ratio <= 0.2 else 5.0 if market.above_ma60_ratio <= 0.35 else 0.0
    breadth = min(25.0, breadth)

    panic = 0.0
    if market.limit_down_count is not None:
        panic += 12.0 if market.limit_down_count >= 100 else 8.0 if market.limit_down_count >= 50 else 4.0 if market.limit_down_count >= 20 else 0.0
        if market.limit_down_count >= 20:
            reasons.append(f"跌停数量达到{market.limit_down_count}家")
    daily_return = _median_index_value(market, "daily_return_pct")
    panic += 8.0 if daily_return <= -4 else 4.0 if daily_return <= -2 else 0.0
    if market.turnover_zscore is not None and market.turnover_zscore >= 1.5:
        panic = min(20.0, panic + 3.0)
        reasons.append("成交额显著高于近期均值")
    panic = min(20.0, panic)

    total = round(min(100.0, trend + drawdown_score + breadth + panic), 1)
    breadth_unavailable = (
        market.advancer_ratio is None
        and market.above_ma60_ratio is None
        and market.limit_down_count is None
    )
    if breadth_unavailable:
        level = "数据不足"
        reasons.append("市场宽度与跌停数据缺失，当前分数不可用于排除股灾")
    else:
        level = "股灾" if total >= 85 else "恐慌" if total >= 70 else "观察" if total >= 50 else "正常"
    return MarketResult(
        observation=market,
        score=total,
        level=level,
        components={
            "trend": round(trend, 1),
            "drawdown": round(drawdown_score, 1),
            "breadth": round(breadth, 1),
            "panic": round(panic, 1),
        },
        reasons=reasons or ["未触发显著市场压力条件"],
    )


def _quality(c: CandidateObservation) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    if c.industry_market_cap_rank is not None and c.industry_market_cap_rank <= 3:
        score += 6
        reasons.append(f"行业市值排名第{c.industry_market_cap_rank}")
    elif c.industry_market_cap_rank is not None and c.industry_market_cap_rank <= 5:
        score += 4
    if c.important_index_member:
        score = max(score, 5)
    elif c.market_cap_billion is not None:
        score += 3 if c.market_cap_billion >= 100 else 1 if c.market_cap_billion >= 30 else 0
    if c.roe_5y_median_pct is not None:
        score += 10 if c.roe_5y_median_pct >= 15 else 7 if c.roe_5y_median_pct >= 10 else 2 if c.roe_5y_median_pct > 0 else 0
        if c.roe_5y_median_pct >= 12:
            reasons.append(f"五年ROE中位数{c.roe_5y_median_pct:.1f}%")
    if c.operating_cashflow_to_profit is not None:
        score += 7 if c.operating_cashflow_to_profit >= 0.9 else 4 if c.operating_cashflow_to_profit >= 0.6 else 0
    growth_points = 0.0
    if c.revenue_growth_pct is not None:
        growth_points += 3.5 if c.revenue_growth_pct >= 10 else 1.5 if c.revenue_growth_pct >= 0 else 0
    if c.profit_growth_pct is not None:
        growth_points += 3.5 if c.profit_growth_pct >= 10 else 1.5 if c.profit_growth_pct >= 0 else 0
    score += growth_points
    if growth_points >= 7:
        reasons.append("收入与利润保持正增长")
    return min(30.0, score), reasons


def _valuation(c: CandidateObservation) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    if c.pe_ttm is not None and c.pe_ttm > 0:
        score += 3
    if c.pe_history_percentile is not None:
        score += 9 if c.pe_history_percentile <= 0.2 else 6 if c.pe_history_percentile <= 0.35 else 3 if c.pe_history_percentile <= 0.5 else 0
        if c.pe_history_percentile <= 0.35:
            reasons.append(f"PE处于自身历史{c.pe_history_percentile:.0%}分位")
    if c.pe_industry_percentile is not None:
        score += 6 if c.pe_industry_percentile <= 0.3 else 4 if c.pe_industry_percentile <= 0.5 else 0
    if c.profit_growth_pct is not None and c.pe_ttm is not None and c.pe_ttm > 0 and c.profit_growth_pct > 0:
        peg = c.pe_ttm / max(c.profit_growth_pct, 1)
        score += 2 if peg <= 1.0 else 1 if peg <= 1.5 else 0
    return min(20.0, score), reasons


def _mispricing(c: CandidateObservation) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    if c.drawdown_252_pct is not None:
        dd = abs(min(0.0, c.drawdown_252_pct))
        score += 12 if dd >= 40 else 9 if dd >= 30 else 5 if dd >= 20 else 0
        if dd >= 30:
            reasons.append(f"距一年高点回撤{dd:.1f}%")
    if c.daily_return_pct is not None:
        fall = abs(min(0.0, c.daily_return_pct))
        score += 4 if fall >= 7 else 3 if fall >= 4 else 1 if fall >= 2 else 0
    if c.return_20d_pct is not None:
        fall = abs(min(0.0, c.return_20d_pct))
        score += 5 if fall >= 20 else 3 if fall >= 10 else 1 if fall >= 5 else 0
    if c.return_60d_pct is not None:
        fall = abs(min(0.0, c.return_60d_pct))
        score += 4 if fall >= 30 else 2 if fall >= 15 else 0
    if c.relative_to_sector_pct is not None:
        under = abs(min(0.0, c.relative_to_sector_pct))
        score += 3 if under >= 15 else 2 if under >= 8 else 0
    if c.volume_ratio_20d is not None and c.volume_ratio_20d >= 1.5:
        score += 2
    return min(30.0, score), reasons


def _relative_strength(c: CandidateObservation) -> tuple[float, list[str]]:
    relative = c.relative_to_market_pct
    label = "大盘"
    if relative is None:
        relative = c.relative_to_sector_pct
        label = "行业"
    if relative is None:
        return 0.0, []
    score = 10.0 if relative >= 5 else 7.0 if relative >= 0 else 4.0 if relative >= -5 else 0.0
    reasons = [f"20日表现相对{label}{relative:+.1f}%"] if score >= 7 else []
    return score, reasons


def _catalyst(c: CandidateObservation) -> tuple[float, list[str]]:
    if len(c.catalyst_evidence) >= 2:
        return 10.0, [f"已记录{len(c.catalyst_evidence)}项可验证催化剂"]
    if c.catalyst_evidence:
        return 6.0, ["已记录1项可验证催化剂"]
    return 0.0, []


def score_candidate(c: CandidateObservation) -> CandidateResult:
    mispricing, m_reasons = _mispricing(c)
    quality, q_reasons = _quality(c)
    valuation, v_reasons = _valuation(c)
    relative_strength, rs_reasons = _relative_strength(c)
    catalyst, c_reasons = _catalyst(c)
    breakdown = ScoreBreakdown(
        mispricing, quality, valuation, relative_strength, catalyst
    )
    missing = [field for field in _REQUIRED_RESEARCH_FIELDS if getattr(c, field) is None]
    if c.relative_to_market_pct is None:
        missing.append("relative_to_market_pct")
    if not c.catalyst_evidence:
        missing.append("catalyst_evidence")
    bucket = "Panic Value Hunter"

    severe = any(flag in {"investigation", "qualified_audit", "fraud", "delisting", "negative_equity"} for flag in c.risk_flags)
    if severe:
        status = "Reject"
        evidence = c.risk_evidence[0] if c.risk_evidence else "需先核实公告和监管事项"
        first_rejection = f"存在重大风险标签：{evidence}"
    elif missing:
        status = "C - 数据不足"
        first_rejection = f"缺少{len(missing)}项关键时点数据"
    elif breakdown.total >= 80:
        status = "A - 深入研究"
        first_rejection = "需要验证盈利持续性及下期业绩预期"
    elif breakdown.total >= 65:
        status = "B - 观察名单"
        first_rejection = "综合评分尚未达到深入研究阈值"
    else:
        status = "C - 初筛标记"
        first_rejection = "质量、估值或基本面支持不足"

    return CandidateResult(
        observation=c,
        score=breakdown,
        bucket=bucket,
        status=status,
        reasons=(m_reasons + q_reasons + v_reasons + rs_reasons + c_reasons)[:6],
        first_rejection=first_rejection,
        missing_fields=missing,
    )
