"""Thin Research MVP orchestration over the existing Value Hunter scan."""

from __future__ import annotations

from typing import Any

from src.value_hunter.models import CandidateResult, ScanResult
from src.value_hunter.service import ValueHunterService


def _market_state(score: float) -> str:
    if score >= 85:
        return "EXTREME_PANIC"
    if score >= 70:
        return "PANIC"
    if score >= 50:
        return "CAUTION"
    return "NORMAL"


def _candidate_payload(candidate: CandidateResult) -> dict[str, Any]:
    observation = candidate.observation
    gaps = list(candidate.missing_fields)
    if observation.current_price is None:
        gaps.append("current_price")
    if observation.relative_to_sector_pct is None:
        gaps.append("relative_to_sector_pct")
    return {
        "name": observation.name,
        "code": observation.symbol,
        "current_price": observation.current_price,
        "drawdown_pct": observation.drawdown_252_pct,
        "relative_to_market_pct": None,
        "sector": observation.sector,
        "sector_performance_pct": observation.relative_to_sector_pct,
        "selection_reasons": list(candidate.reasons),
        "risks": list(observation.risk_flags) + list(observation.risk_evidence),
        "data_gaps": list(dict.fromkeys(["relative_to_market_pct", *gaps])),
        "score": candidate.score.total,
        "research_status": candidate.status,
        "first_rejection": candidate.first_rejection,
        "quality": {
            "score": candidate.score.quality,
            "roe_5y_median_pct": observation.roe_5y_median_pct,
            "operating_cashflow_to_profit": observation.operating_cashflow_to_profit,
        },
        "financials": {
            "revenue_growth_pct": observation.revenue_growth_pct,
            "profit_growth_pct": observation.profit_growth_pct,
        },
        "valuation": {
            "pe_ttm": observation.pe_ttm,
            "pb": observation.pb,
            "pe_history_percentile": observation.pe_history_percentile,
            "pe_industry_percentile": observation.pe_industry_percentile,
        },
        "supporting_evidence": list(candidate.reasons),
        "counter_evidence": list(observation.risk_evidence),
    }


def build_research_run(service: ValueHunterService) -> dict[str, Any]:
    """Run the existing scanner once with notifications disabled and adapt it."""
    scan: ScanResult = service.run(notify=False)
    observation = scan.market.observation
    gaps = list(observation.warnings)
    summary_fields = {
        "advancers": observation.advancer_count,
        "decliners": observation.decliner_count,
        "limit_up": observation.limit_up_count,
        "limit_down": observation.limit_down_count,
        "breadth": observation.advancer_ratio,
        "panic_reasons": list(scan.market.reasons),
        "source": observation.source,
    }
    for field in ("advancers", "decliners", "limit_up", "limit_down", "breadth"):
        if summary_fields[field] is None:
            gaps.append(f"market_summary.{field}")
    candidates = [_candidate_payload(item) for item in scan.candidates[:5]]
    if not candidates:
        gaps.append("No candidate met the existing Value Hunter research threshold.")
    return {
        "trade_date": observation.as_of,
        "market_state": _market_state(scan.market.score),
        "market_summary": summary_fields,
        "candidates": candidates,
        "data_gaps": list(dict.fromkeys(gaps)),
    }
