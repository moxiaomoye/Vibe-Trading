from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter

from src.investment_research.models.historical_market_panel import (
    HistoricalMarketPanel,
)
from src.investment_research.operations.evaluation_metrics import (
    EvaluationMetrics,
    MetricsCalculator,
    HorizonMetrics,
)
from src.investment_research.operations.outcome_loader import (
    FixtureOutcomeLoader,
    OutcomeLoader,
)
from src.investment_research.operations.review_labeling import (
    ReviewLabel,
    label_outcome,
)

router = APIRouter(prefix="/investment-research/historical-evaluation")


@router.get("/status")
def historical_evaluation_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "description": "Historical evaluation endpoint for M1.3 shadow report outcomes",
        "supported_horizons": [5, 20, 60],
    }


@router.get("/evaluate/{trade_date}")
def evaluate_trade_date(trade_date: str) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except (ValueError, TypeError):
        return {"error": {"code": "invalid_date", "message": "trade_date must be ISO format (YYYY-MM-DD)"}}

    loader: OutcomeLoader = FixtureOutcomeLoader({})
    outcome = loader.load(d)
    cal = MetricsCalculator()
    panel = HistoricalMarketPanel(
        date=d, market_price=0.0, market_change_pct=0.0,
        ma_5=0.0, ma_10=0.0, ma_20=0.0,
        volume=0, turnover=0.0, amplitude=0.0,
    )
    metrics = cal.evaluate(panel, outcome)
    labels = label_outcome(outcome)

    return _serialize_evaluation(d, metrics, labels)


def _serialize_evaluation(
    d: date,
    metrics: EvaluationMetrics,
    labels: dict[int, ReviewLabel],
) -> dict[str, Any]:
    return {
        "evaluation_date": d.isoformat(),
        "entry_price": metrics.entry_price,
        "metrics": {
            "hit_rate": metrics.hit_rate,
            "false_positive_rate": metrics.false_positive_rate,
            "false_negative_rate": metrics.false_negative_rate,
            "avg_excess_return": metrics.avg_excess_return,
            "avg_max_drawdown": metrics.avg_max_drawdown,
        },
        "horizons": [
            {
                "horizon": h.horizon,
                "asset_return": h.asset_return,
                "benchmark_return": h.benchmark_return,
                "excess_return": h.excess_return,
                "maximum_drawdown": h.maximum_drawdown,
                "hit": h.hit,
                "review_label": labels.get(h.horizon, "unclear"),
                "data_gap": h.data_gap,
            }
            for h in metrics.horizons
        ],
    }
