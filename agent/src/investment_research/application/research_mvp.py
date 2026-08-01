"""Thin Research MVP orchestration over the existing Value Hunter scan."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable

from src.value_hunter.models import CandidateResult, ScanResult
from src.value_hunter.config import resolve_panic_sensitivity
from src.value_hunter.service import ValueHunterService
from src.investment_research.operations.models import DeliveryChannel, OutboxMessage, OutboxStatus
from src.investment_research.repositories.sqlite_operations import SQLiteOperationsRepository
from uuid import NAMESPACE_URL, uuid5

MarketFetcher = Callable[..., dict[str, Any]]


def _market_state(
    score: float,
    trigger_count: int | None = None,
    required_confirmations: int | None = None,
) -> str:
    confirmed = (
        trigger_count is None
        or required_confirmations is None
        or trigger_count >= required_confirmations
    )
    if score >= 85 and confirmed:
        return "EXTREME_PANIC"
    if confirmed and trigger_count is not None and trigger_count > 0:
        return "PANIC"
    if score >= 50 or (trigger_count or 0) > 0:
        return "CAUTION"
    return "NORMAL"


def _panic_profile(scan: ScanResult, sensitivity: dict[str, Any]) -> dict[str, Any]:
    observation = scan.market.observation
    index_returns = [float(item.daily_return_pct) for item in observation.indices]
    daily_return = median(index_returns) if index_returns else None
    checks = {
        "index_daily_return": {
            "observed": round(daily_return, 3) if daily_return is not None else None,
            "threshold": sensitivity["index_daily_return_pct"],
            "triggered": daily_return <= sensitivity["index_daily_return_pct"] if daily_return is not None else None,
        },
        "advancer_ratio": {
            "observed": observation.advancer_ratio,
            "threshold": sensitivity["max_advancer_ratio"],
            "triggered": observation.advancer_ratio <= sensitivity["max_advancer_ratio"] if observation.advancer_ratio is not None else None,
        },
        "limit_down_count": {
            "observed": observation.limit_down_count,
            "threshold": sensitivity["min_limit_down_count"],
            "triggered": observation.limit_down_count >= sensitivity["min_limit_down_count"] if observation.limit_down_count is not None else None,
        },
    }
    trigger_count = sum(item["triggered"] is True for item in checks.values())
    return {**sensitivity, "trigger_count": trigger_count, "checks": checks}


def _candidate_payload(candidate: CandidateResult) -> dict[str, Any]:
    observation = candidate.observation
    gaps = list(candidate.missing_fields)
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
    observation_conditions = list(candidate.reasons) or [
        "补齐公司质量、财务、估值与价格错位证据后再进一步关注。"
    ]
    risk_conditions = list(observation.risk_evidence) or [candidate.first_rejection]
    validation_conditions = [
        "在下一次定期报告或公告后复核收入、利润和经营现金流趋势。",
        "复核相对大盘与行业表现是否改善，并确认改善不是未来数据回填。",
    ]
    market_reasons = [reason for reason in (
        f"单日涨跌幅{observation.daily_return_pct:.1f}%" if observation.daily_return_pct is not None else None,
        f"20日相对大盘{observation.relative_to_market_pct:+.1f}%" if observation.relative_to_market_pct is not None else None,
        f"距一年高点{observation.drawdown_252_pct:.1f}%" if observation.drawdown_252_pct is not None else None,
    ) if reason]
    company_reasons = [reason for reason in (
        f"五年ROE中位数{observation.roe_5y_median_pct:.1f}%" if observation.roe_5y_median_pct is not None else None,
        f"收入增长{observation.revenue_growth_pct:.1f}%" if observation.revenue_growth_pct is not None else None,
        f"利润增长{observation.profit_growth_pct:.1f}%" if observation.profit_growth_pct is not None else None,
    ) if reason]
    valuation_reasons = [reason for reason in (
        f"PE(TTM) {observation.pe_ttm:.1f}" if observation.pe_ttm is not None else None,
        f"PE历史分位{observation.pe_history_percentile:.0%}" if observation.pe_history_percentile is not None else None,
        f"PE行业分位{observation.pe_industry_percentile:.0%}" if observation.pe_industry_percentile is not None else None,
    ) if reason]
    return {
        "name": observation.name,
        "code": observation.symbol,
        "current_price": observation.current_price,
        "security_type": observation.security_type,
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
        "selection_reasons": list(candidate.reasons),
        "entry_reasons": {
            "market": market_reasons,
            "company": company_reasons,
            "valuation": valuation_reasons,
        },
        "risks": list(observation.risk_flags) + list(observation.risk_evidence),
        "catalysts": list(observation.catalyst_evidence),
        "invalidation": risk_conditions,
        "data_gaps": list(dict.fromkeys(gaps)),
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
        "forward_validation": {"t5": None, "t20": None, "t60": None},
        "research_plan": {
            "observation_conditions": observation_conditions,
            "risk_conditions": risk_conditions,
            "validation_conditions": validation_conditions,
        },
    }


def build_research_run(
    service: ValueHunterService,
    panic_sensitivity: int = 50,
) -> dict[str, Any]:
    """Run the existing scanner once with notifications disabled and adapt it."""
    method, resolved = resolve_panic_sensitivity(panic_sensitivity, service.config.method)
    scan: ScanResult = service.run(
        notify=False,
        include_incomplete=True,
        method_override=method,
    )
    panic_profile = _panic_profile(scan, resolved.to_dict())
    observation = scan.market.observation
    gaps = list(observation.warnings)
    summary_fields = {
        "advancers": observation.advancer_count,
        "decliners": observation.decliner_count,
        "limit_up": observation.limit_up_count,
        "limit_down": observation.limit_down_count,
        "breadth": observation.advancer_ratio,
        "turnover_amount": observation.turnover_amount,
        "panic_reasons": list(scan.market.reasons),
        "source": observation.source,
    }
    for field in (
        "advancers", "decliners", "limit_up", "limit_down", "breadth",
        "turnover_amount",
    ):
        if summary_fields[field] is None:
            gaps.append(f"market_summary.{field}")
    candidates = [_candidate_payload(item) for item in scan.candidates[:5]]
    for item in scan.candidates[:5]:
        gaps.extend(item.observation.warnings)
    if not candidates:
        gaps.append("No candidate met the existing Value Hunter research threshold.")
    return {
        "trade_date": observation.as_of,
        "market_state": _market_state(
            scan.market.score,
            panic_profile["trigger_count"],
            panic_profile["required_confirmations"],
        ),
        "panic_sensitivity": panic_profile,
        "market_summary": summary_fields,
        "candidates": candidates,
        "data_gaps": list(dict.fromkeys(gaps)),
    }


def _row_date(row: dict[str, Any]) -> date | None:
    for key in ("date", "datetime", "trade_date", "index", "Date"):
        try:
            return date.fromisoformat(str(row[key])[:10])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _row_close(row: dict[str, Any]) -> float | None:
    for key in ("close", "Close"):
        try:
            return float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _forward_returns(raw_rows: Any, trade_date: date) -> tuple[dict[str, float | None], list[str]]:
    metrics, gaps = _forward_metrics(raw_rows, trade_date)
    return {key: value["return_pct"] for key, value in metrics.items()}, gaps


def _forward_metrics(
    raw_rows: Any, trade_date: date
) -> tuple[dict[str, dict[str, float | None]], list[str]]:
    if isinstance(raw_rows, dict) and isinstance(raw_rows.get("data"), list):
        raw_rows = raw_rows["data"]
    rows = sorted(
        ((row_date, close) for row in raw_rows or [] if isinstance(row, dict)
         if (row_date := _row_date(row)) is not None and (close := _row_close(row)) is not None),
        key=lambda item: item[0],
    )
    start_index = next((index for index, (row_date, _) in enumerate(rows) if row_date == trade_date), None)
    gaps: list[str] = []
    if start_index is None:
        return {
            f"t{horizon}": {"return_pct": None, "max_drawdown_pct": None}
            for horizon in (5, 20, 60)
        }, ["base_trade_date_price"]
    base_close = rows[start_index][1]
    metrics: dict[str, dict[str, float | None]] = {}
    for horizon in (5, 20, 60):
        target_index = start_index + horizon
        key = f"t{horizon}"
        if target_index >= len(rows):
            metrics[key] = {"return_pct": None, "max_drawdown_pct": None}
            gaps.append(key)
        else:
            path = [close for _, close in rows[start_index:target_index + 1]]
            peak = path[0]
            max_drawdown = 0.0
            for close in path:
                peak = max(peak, close)
                max_drawdown = min(max_drawdown, (close / peak - 1.0) * 100.0)
            metrics[key] = {
                "return_pct": round((path[-1] / base_close - 1.0) * 100.0, 2),
                "max_drawdown_pct": round(max_drawdown, 2),
            }
    return metrics, gaps


def _classify_outcome(return_pct: float | None, excess_pct: float | None) -> str:
    if return_pct is None or excess_pct is None:
        return "不确定"
    if return_pct > 0 and excess_pct >= 3:
        return "正确"
    if return_pct <= -10 or excess_pct <= -3:
        return "错误"
    return "不确定"


def build_historical_evaluation(
    service: ValueHunterService,
    trade_date: date,
    market_fetcher: MarketFetcher,
) -> dict[str, Any]:
    """Evaluate a stored point-in-time scan without reconstructing it from future data."""
    snapshot = next(
        (item for item in service.history(200) if item.get("market", {}).get("observation", {}).get("as_of") == trade_date.isoformat()),
        None,
    )
    if snapshot is None:
        return {
            "trade_date": trade_date.isoformat(),
            "market_state": None,
            "candidates": [],
            "data_gaps": ["No point-in-time Value Hunter snapshot exists for the selected date."],
        }
    raw_candidates = snapshot.get("candidates", [])[:5]
    symbols = [item.get("observation", {}).get("symbol") for item in raw_candidates]
    symbols = [symbol for symbol in symbols if symbol]
    benchmark_symbol = "000300.SH"
    requested_symbols = list(dict.fromkeys([*symbols, benchmark_symbol]))
    price_data = market_fetcher(
        codes=requested_symbols,
        start_date=trade_date.isoformat(),
        end_date=(trade_date + timedelta(days=100)).isoformat(),
        source="auto",
        interval="1D",
        max_rows=0,
    ) if symbols else {}
    benchmark_metrics, benchmark_gaps = _forward_metrics(
        price_data.get(benchmark_symbol, []), trade_date
    )
    candidates: list[dict[str, Any]] = []
    gaps: list[str] = []
    for item in raw_candidates:
        observation = item.get("observation", {})
        symbol = observation.get("symbol", "")
        metrics, return_gaps = _forward_metrics(price_data.get(symbol, []), trade_date)
        horizon_payload: dict[str, Any] = {}
        for key in ("t5", "t20", "t60"):
            value = metrics[key]
            benchmark_return = benchmark_metrics[key]["return_pct"]
            excess = (
                round(value["return_pct"] - benchmark_return, 2)
                if value["return_pct"] is not None and benchmark_return is not None
                else None
            )
            horizon_payload[key] = value["return_pct"]
            horizon_payload[f"{key}_max_drawdown"] = value["max_drawdown_pct"]
            horizon_payload[f"{key}_excess"] = excess
            horizon_payload[f"{key}_outcome"] = _classify_outcome(
                value["return_pct"], excess
            )
        candidate_gaps = list(return_gaps)
        for gap in benchmark_gaps:
            candidate_gaps.append(f"benchmark.{gap}")
        candidates.append({
            "name": observation.get("name", symbol),
            "code": symbol,
            "research_status": item.get("status", "Research Candidate"),
            **horizon_payload,
            "data_gaps": candidate_gaps,
        })
        gaps.extend(f"{symbol}.{gap}" for gap in candidate_gaps)
    return {
        "trade_date": trade_date.isoformat(),
        "market_state": _market_state(float(snapshot.get("market", {}).get("score", 0.0))),
        "candidates": candidates,
        "data_gaps": list(dict.fromkeys(gaps)),
    }


def render_feishu_preview(report: dict[str, Any]) -> str:
    summary = report.get("market_summary", {})
    lines = [
        f"Vibe-Trading 盘后研究 | {report.get('trade_date', 'Data Gap')}",
        f"市场状态：{report.get('market_state', 'Data Gap')}",
        f"上涨/下跌：{summary.get('advancers')} / {summary.get('decliners')}",
        f"涨停/跌停：{summary.get('limit_up')} / {summary.get('limit_down')}",
        "",
        "Research Candidate：",
    ]
    for index, candidate in enumerate(report.get("candidates", [])[:5], 1):
        reasons = "；".join(candidate.get("selection_reasons", [])[:2]) or "Data Gap"
        lines.append(f"{index}. {candidate.get('name')} ({candidate.get('code')})：{reasons}")
    if not report.get("candidates"):
        lines.append("当前无候选；零候选是有效研究结果。")
    lines.extend(("", "仅供研究验证，不含交易指令、仓位建议或自动交易。"))
    return "\n".join(lines)


def prepare_feishu_delivery(
    report: dict[str, Any],
    repository: SQLiteOperationsRepository,
    *,
    send: bool = False,
    confirmed: bool = False,
) -> dict[str, Any]:
    preview = render_feishu_preview(report)
    eligible = (
        report.get("market_state") in {"PANIC", "EXTREME_PANIC"}
        and any(
            float(candidate.get("score", 0.0)) >= 75
            and str(candidate.get("research_status", "")).startswith(("A", "B"))
            for candidate in report.get("candidates", [])
        )
    )
    result: dict[str, Any] = {
        "preview": preview,
        "send": send,
        "confirmed": confirmed,
        "scheduler": False,
        "status": "preview",
        "eligible": eligible,
    }
    if not send:
        return result
    if not confirmed:
        raise ValueError("confirmed=true is required when send=true")
    if not eligible:
        raise ValueError(
            "Feishu outbox requires PANIC/EXTREME_PANIC and a high-quality candidate"
        )
    now = datetime.now(timezone.utc)
    trade_date = str(report.get("trade_date", "unknown"))
    key = f"research-mvp:{trade_date}:feishu"
    message = OutboxMessage(
        message_id=str(uuid5(NAMESPACE_URL, key)),
        idempotency_key=key,
        channel=DeliveryChannel.FEISHU,
        message_type="research_mvp",
        subject=f"Vibe-Trading 盘后研究 {trade_date}",
        body=preview,
        source_id=trade_date,
        status=OutboxStatus.PENDING,
        attempt_count=0,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    inserted = repository.enqueue(message)
    result["status"] = "queued" if inserted else "already_queued"
    result["message_id"] = message.message_id
    return result
