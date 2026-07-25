from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.historical_evaluation_routes import (
    _serialize_evaluation,
    router,
)
from src.investment_research.operations.evaluation_metrics import (
    EvaluationMetrics,
    HorizonMetrics,
    MetricsCalculator,
)
from src.investment_research.operations.outcome_loader import (
    HistoricalEvaluationOutcome,
    WindowOutcome,
)
from src.investment_research.operations.review_labeling import ReviewLabel


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestHistoricalEvaluationRoutes:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def test_status(self) -> None:
        resp = self.client.get("/investment-research/historical-evaluation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["supported_horizons"] == [5, 20, 60]

    def test_evaluate_invalid_date(self) -> None:
        resp = self.client.get("/investment-research/historical-evaluation/evaluate/bad-date")
        assert resp.status_code == 422 or resp.status_code == 200
        data = resp.json()
        if "error" in data:
            assert data["error"]["code"] == "invalid_date"

    def test_serialize_evaluation(self) -> None:
        d = date(2026, 7, 15)
        metrics = EvaluationMetrics(
            evaluation_date=d,
            entry_price=15.0,
            horizons=(
                HorizonMetrics(5, 0.02, 0.01, 0.01, -0.03, True, None),
                HorizonMetrics(20, -0.01, 0.01, -0.02, -0.05, False, None),
            ),
            hit_rate=0.5,
            false_positive_rate=0.5,
            false_negative_rate=0.0,
            avg_excess_return=-0.005,
            avg_max_drawdown=-0.04,
        )
        labels = {5: ReviewLabel.CORRECT_CALL, 20: ReviewLabel.FALSE_POSITIVE}
        result = _serialize_evaluation(d, metrics, labels)
        assert result["evaluation_date"] == "2026-07-15"
        assert result["metrics"]["hit_rate"] == 0.5
        assert len(result["horizons"]) == 2
        assert result["horizons"][0]["review_label"] == "correct_call"
        assert result["horizons"][1]["review_label"] == "false_positive"
