"""Shared Research Candidate contract builder (RRV-RELIABILITY-CLOSURE-001).

Single serialization path for live scans, stored snapshot replay, and
HistoricalAkshareProvider rebuilds so no path maintains its own candidate
schema. A ``C - 数据不足`` candidate still carries a deterministic score,
score components, missing fields and a risk review; ETF issuer-only financial
fields are explicitly ``NOT_APPLICABLE`` instead of ``MISSING``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.value_hunter.models import CandidateResult

from .eligibility import EligibilityVerdict, EligibilityStatus
from .risk_review import evaluate_risk_review

CANDIDATE_CONTRACT_VERSION = "candidate-contract-v1"

_ISSUER_ONLY_FIELDS = {
    "roe_5y_median_pct",
    "operating_cashflow_to_profit",
    "pe_history_percentile",
    "revenue_growth_pct",
    "profit_growth_pct",
}

_PROVIDER_FAILURE_MARKERS = (
    "读取失败",
    "registry unavailable",
    "provider_failure",
    "DEGRADED",
)


def _risk_review_inputs(observation: Any) -> dict[str, Any]:
    return {
        "security_type": observation.security_type,
        "risk_flags": list(observation.risk_flags),
        "risk_evidence": list(observation.risk_evidence),
        "roe_5y_median_pct": observation.roe_5y_median_pct,
        "operating_cashflow_to_profit": observation.operating_cashflow_to_profit,
        "profit_growth_pct": observation.profit_growth_pct,
    }


def _market_reasons(observation: Any) -> list[str]:
    return [reason for reason in (
        f"单日涨跌幅{observation.daily_return_pct:.1f}%" if observation.daily_return_pct is not None else None,
        f"20日相对大盘{observation.relative_to_market_pct:+.1f}%" if observation.relative_to_market_pct is not None else None,
        f"距一年高点{observation.drawdown_252_pct:.1f}%" if observation.drawdown_252_pct is not None else None,
    ) if reason]


def _company_reasons(observation: Any) -> list[str]:
    return [reason for reason in (
        f"五年ROE中位数{observation.roe_5y_median_pct:.1f}%" if observation.roe_5y_median_pct is not None else None,
        f"收入增长{observation.revenue_growth_pct:.1f}%" if observation.revenue_growth_pct is not None else None,
        f"利润增长{observation.profit_growth_pct:.1f}%" if observation.profit_growth_pct is not None else None,
    ) if reason]


def _valuation_reasons(observation: Any) -> list[str]:
    return [reason for reason in (
        f"PE(TTM) {observation.pe_ttm:.1f}" if observation.pe_ttm is not None else None,
        f"PE历史分位{observation.pe_history_percentile:.0%}" if observation.pe_history_percentile is not None else None,
        f"PE行业分位{observation.pe_industry_percentile:.0%}" if observation.pe_industry_percentile is not None else None,
    ) if reason]


def _issuer_or_value(observation: Any, field: str, is_etf: bool) -> float | str | None:
    value = getattr(observation, field, None)
    if value is not None:
        return value
    return "NOT_APPLICABLE" if is_etf and field in _ISSUER_ONLY_FIELDS else None


def build_candidate_payload(
    candidate: CandidateResult,
    *,
    as_of: date,
    eligibility: EligibilityVerdict | None = None,
    horizon_payload: dict[str, Any] | None = None,
    horizon_gaps: list[str] | None = None,
) -> dict[str, Any]:
    """Serialize one candidate through the shared contract.

    ``horizon_payload`` carries the legacy T+5/20/60 keys (``t5``,
    ``t5_max_drawdown``, ``t5_excess``, ``t5_outcome``, ...) produced by the
    evaluation layer; when absent the forward validation block is left empty.
    """
    observation = candidate.observation
    is_etf = observation.security_type == "etf"
    gaps = list(candidate.missing_fields)
    if is_etf:
        gaps = [gap for gap in gaps if gap not in _ISSUER_ONLY_FIELDS]
    if observation.current_price is None:
        gaps.append("current_price")
    if observation.relative_to_sector_pct is None:
        gaps.append("relative_to_sector_pct")
    if not observation.catalyst_evidence:
        gaps.append("catalyst_evidence")
    for field in (
        "daily_return_pct",
        "return_20d_pct",
        "return_60d_pct",
        "volume_ratio_20d",
        "relative_to_market_pct",
        "market_data_as_of",
        "market_data_source",
    ):
        if getattr(observation, field) is None:
            gaps.append(field)
    etf_valuation = observation.etf_valuation or None
    if is_etf:
        for field in (
            "latest_nav",
            "nav_premium_pct",
            "reasonable_price_low",
            "reasonable_price_high",
            "bargain_price_low",
            "bargain_price_high",
            "underlying_valuation_premium_pct",
            "underlying_ann_volatility_pct",
            "underlying_max_drawdown_pct",
            "underlying_panic_sessions_count",
        ):
            if not etf_valuation or etf_valuation.get(field) is None:
                gaps.append(f"etf_valuation.{field}")
    provider_gaps = [
        warning for warning in observation.warnings
        if any(marker in warning for marker in _PROVIDER_FAILURE_MARKERS)
    ]
    gaps.extend(provider_gaps)
    if horizon_gaps:
        gaps.extend(horizon_gaps)

    observation_conditions = list(candidate.reasons) or [
        "补齐公司质量、财务、估值与价格错位证据后再进一步关注。"
    ]
    risk_conditions = list(observation.risk_evidence) or [candidate.first_rejection]
    validation_conditions = [
        "在下一次定期报告或公告后复核收入、利润和经营现金流趋势。",
        "复核相对大盘与行业表现是否改善，并确认改善不是未来数据回填。",
    ]

    score = candidate.score
    score_components = {
        "mispricing": round(score.mispricing, 1),
        "quality": round(score.quality, 1),
        "valuation": round(score.valuation, 1),
        "relative_strength": round(score.relative_strength, 1),
        "catalyst": round(score.catalyst, 1),
        "total": score.total,
    }
    eligibility_block: dict[str, Any] = {
        "eligibility_status": eligibility.eligibility_status.value if eligibility else None,
        "listing_date": eligibility.listing_date.isoformat() if eligibility and eligibility.listing_date else None,
        "eligibility_evidence_source": eligibility.eligibility_evidence_source if eligibility else None,
        "eligibility_reason": eligibility.eligibility_reason if eligibility else None,
        "eligibility_as_of": eligibility.eligibility_as_of.isoformat() if eligibility else as_of.isoformat(),
    }
    forward_validation: dict[str, Any] = {}
    legacy_horizon: dict[str, Any] = {}
    for key in ("t5", "t20", "t60"):
        if not horizon_payload:
            forward_validation[key] = None
            legacy_horizon[key] = None
            continue
        return_value = horizon_payload.get(key)
        entry: dict[str, Any] = {
            "return_pct": return_value,
            "max_drawdown_pct": horizon_payload.get(f"{key}_max_drawdown"),
            "excess_pct": horizon_payload.get(f"{key}_excess"),
            "outcome": horizon_payload.get(f"{key}_outcome"),
        }
        forward_validation[key] = entry
        legacy_horizon[key] = return_value
        legacy_horizon[f"{key}_max_drawdown"] = horizon_payload.get(f"{key}_max_drawdown")
        legacy_horizon[f"{key}_excess"] = horizon_payload.get(f"{key}_excess")
        legacy_horizon[f"{key}_outcome"] = horizon_payload.get(f"{key}_outcome")

    payload: dict[str, Any] = {
        "contract_version": CANDIDATE_CONTRACT_VERSION,
        "name": observation.name,
        "code": observation.symbol,
        "security_type": observation.security_type,
        "research_status": candidate.status,
        "score": score.total,
        "score_components": score_components,
        "selection_reasons": list(candidate.reasons),
        "first_rejection": candidate.first_rejection,
        "missing_fields": list(dict.fromkeys(candidate.missing_fields)),
        "data_gaps": list(dict.fromkeys(gaps)),
        "source_fields": list(observation.source_fields),
        "provider_warnings": list(observation.warnings),
        "supporting_evidence": list(candidate.reasons),
        "counter_evidence": list(observation.risk_evidence),
        "risk_review": evaluate_risk_review(_risk_review_inputs(observation)).model_dump(),
        "forward_validation": forward_validation,
        **eligibility_block,
        "current_price": observation.current_price,
        "daily_return_pct": observation.daily_return_pct,
        "return_20d_pct": observation.return_20d_pct,
        "return_60d_pct": observation.return_60d_pct,
        "volume_ratio_20d": observation.volume_ratio_20d,
        "drawdown_pct": observation.drawdown_252_pct,
        "relative_to_market_pct": observation.relative_to_market_pct,
        "market_data_as_of": observation.market_data_as_of,
        "market_data_source": observation.market_data_source,
        "sector": observation.sector,
        "sector_performance_pct": observation.relative_to_sector_pct,
        "entry_reasons": {
            "market": _market_reasons(observation),
            "company": _company_reasons(observation),
            "valuation": _valuation_reasons(observation),
        },
        "risks": list(observation.risk_flags) + list(observation.risk_evidence),
        "catalysts": list(observation.catalyst_evidence),
        "invalidation": risk_conditions,
        "quality": {
            "score": round(score.quality, 1),
            "roe_5y_median_pct": _issuer_or_value(observation, "roe_5y_median_pct", is_etf),
            "operating_cashflow_to_profit": _issuer_or_value(
                observation, "operating_cashflow_to_profit", is_etf
            ),
        },
        "financials": {
            "revenue_growth_pct": _issuer_or_value(observation, "revenue_growth_pct", is_etf),
            "profit_growth_pct": _issuer_or_value(observation, "profit_growth_pct", is_etf),
        },
        "valuation": {
            "pe_ttm": observation.pe_ttm,
            "pb": observation.pb,
            "pe_history_percentile": _issuer_or_value(
                observation, "pe_history_percentile", is_etf
            ),
            "pe_industry_percentile": _issuer_or_value(
                observation, "pe_industry_percentile", is_etf
            ),
        },
        "etf_valuation": etf_valuation,
        "research_plan": {
            "observation_conditions": observation_conditions,
            "risk_conditions": risk_conditions,
            "validation_conditions": validation_conditions,
        },
        **legacy_horizon,
    }
    if eligibility is not None and eligibility.eligibility_status is EligibilityStatus.CONFIRMED_NOT_LISTED:
        payload["selected_excluded_reason"] = eligibility.eligibility_reason
    return payload


def eligibility_blocks(
    verdicts: dict[str, EligibilityVerdict],
) -> dict[str, dict[str, Any]]:
    """Serialize eligibility verdicts for the universe audit."""
    return {symbol: verdict.model_dump(mode="json") for symbol, verdict in verdicts.items()}
