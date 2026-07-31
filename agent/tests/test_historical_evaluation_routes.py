from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pandas as pd

import src.api.historical_evaluation_routes as routes
from src.api.historical_evaluation_routes import register_historical_evaluation_routes
from src.investment_research.operations.historical_price_provider import (
    HistoricalPriceProviderError,
    HistoricalPriceSeries,
    ProviderAttempt,
)


def _make_app(*, authenticated: bool = True) -> FastAPI:
    app = FastAPI()

    def _auth() -> None:
        if not authenticated:
            raise HTTPException(status_code=401, detail="Unauthorized")

    register_historical_evaluation_routes(app, _auth)
    return app


def _sample_payload() -> dict:
    first = date(2025, 7, 21)
    trading_dates: list[date] = []
    current = first
    while len(trading_dates) < 21:
        if current.weekday() < 5:
            trading_dates.append(current)
        current += timedelta(days=1)

    rows = []
    for index, trade_date in enumerate(trading_dates):
        asset = 10.0 + index * 0.1
        if index == 10:
            asset = 13.0
        elif index == 11:
            asset = 9.0
        rows.append(
            {
                "trade_date": trade_date.isoformat(),
                "asset_close": asset,
                "benchmark_close": 4000.0 + index * 5.0,
            }
        )
    return {
        "schema_version": "1.0",
        "input_mode": "sample",
        "data_source": "synthetic_hand_calculable_sample",
        "availability_time": datetime(2025, 8, 31, tzinfo=timezone.utc).isoformat(),
        "evaluation_date": first.isoformat(),
        "stock_code": "000001",
        "benchmark_code": "000300",
        "adjustment": "qfq",
        "prices": rows,
    }


def test_status_and_auth() -> None:
    assert TestClient(_make_app()).get(
        "/investment-research/historical-evaluation/status"
    ).status_code == 200
    assert TestClient(_make_app(authenticated=False)).get(
        "/investment-research/historical-evaluation/status"
    ).status_code == 401


class _AutomaticProvider:
    def capability_status(self) -> dict:
        return {
            "automatic_fetch": True,
            "providers": [{"provider": "test_provider", "usable": True}],
        }

    def fetch(self, stock_code, evaluation_date, *, horizon):
        index = pd.bdate_range(evaluation_date, periods=21)
        return HistoricalPriceSeries(
            stock_code=stock_code,
            benchmark_code="000300",
            evaluation_date=evaluation_date,
            adjustment="qfq",
            prices=pd.DataFrame(
                {
                    "asset_close": [10.0 + i * 0.1 for i in range(21)],
                    "benchmark_close": [4000.0 + i * 5 for i in range(21)],
                },
                index=index,
            ),
            component_sources={
                "stock": "test_provider",
                "benchmark": "test_provider",
            },
            attempts=(
                ProviderAttempt(
                    provider="test_provider",
                    component="stock",
                    status="success",
                ),
            ),
        )


def test_automatic_price_series_uses_same_t20_calculation(monkeypatch) -> None:
    monkeypatch.setattr(routes, "_provider_factory", _AutomaticProvider)

    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-auto",
        json={
            "stock_code": "000001",
            "evaluation_date": "2025-07-21",
            "horizon": 20,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "provider"
    assert body["adjustment"] == "qfq"
    assert body["verification_status"] == "provider_acquired_unverified"
    assert body["component_sources"]["stock"] == "test_provider"
    assert body["coverage"]["row_count"] == 21
    assert [item["horizon"] for item in body["horizons"]] == [20]
    assert abs(body["horizons"][0]["asset_return"] - 0.2) < 1e-12


def test_automatic_failure_returns_structured_provider_attempts(monkeypatch) -> None:
    class FailedProvider(_AutomaticProvider):
        def fetch(self, stock_code, evaluation_date, *, horizon):
            raise HistoricalPriceProviderError(
                "provider_unavailable",
                "automatic historical data unavailable for: stock",
                [
                    ProviderAttempt(
                        provider="tencent",
                        component="stock",
                        status="failed",
                        category="network",
                        message="connection timed out",
                    )
                ],
            )

    monkeypatch.setattr(routes, "_provider_factory", FailedProvider)
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-auto",
        json={
            "stock_code": "000001",
            "evaluation_date": "2025-07-21",
            "horizon": 20,
        },
    )

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "provider_unavailable"
    assert error["provider_attempts"][0]["category"] == "network"
    assert "tencent (stock) [network]" in error["reasons"][0]


def test_automatic_rejects_date_that_cannot_have_reached_t20(monkeypatch) -> None:
    class ProviderMustNotRun(_AutomaticProvider):
        def fetch(self, stock_code, evaluation_date, *, horizon):
            raise AssertionError("provider must not run for an immature date")

    monkeypatch.setattr(routes, "_provider_factory", ProviderMustNotRun)
    evaluation_date = datetime.now(routes.SHANGHAI).date() - timedelta(days=10)
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-auto",
        json={
            "stock_code": "000001",
            "evaluation_date": evaluation_date.isoformat(),
            "horizon": 20,
        },
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "date_not_matured"
    assert "has not reached T+20" in error["message"]


def test_automatic_reports_requested_and_effective_trading_dates(
    monkeypatch,
) -> None:
    class WeekendResolvingProvider(_AutomaticProvider):
        def fetch(self, stock_code, evaluation_date, *, horizon):
            series = super().fetch(
                stock_code,
                date(2025, 7, 18),
                horizon=horizon,
            )
            return HistoricalPriceSeries(
                stock_code=series.stock_code,
                benchmark_code=series.benchmark_code,
                evaluation_date=date(2025, 7, 18),
                adjustment=series.adjustment,
                prices=series.prices,
                component_sources=series.component_sources,
                attempts=series.attempts,
                requested_evaluation_date=date(2025, 7, 20),
                date_resolution="previous_common_trading_day",
            )

    monkeypatch.setattr(
        routes,
        "_provider_factory",
        WeekendResolvingProvider,
    )
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-auto",
        json={
            "stock_code": "000001",
            "evaluation_date": "2025-07-20",
            "horizon": 20,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_evaluation_date"] == "2025-07-20"
    assert body["effective_evaluation_date"] == "2025-07-18"
    assert body["evaluation_date"] == "2025-07-18"
    assert body["date_resolution"] == "previous_common_trading_day"
    assert "previous common trading day" in body["warnings"][0]


def test_manual_price_series_returns_hand_calculable_t20() -> None:
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-manual",
        json=_sample_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["input_mode"] == "sample"
    assert body["capability"] == "sample_contract"
    assert body["coverage"]["row_count"] == 21
    t20 = next(row for row in body["horizons"] if row["horizon"] == 20)
    assert t20["target_trading_date"] == "2025-08-18"
    assert t20["target_price"] == 12.0
    assert abs(t20["asset_return"] - 0.2) < 1e-12
    expected_benchmark = 4100.0 / 4000.0 - 1.0
    assert abs(t20["benchmark_return"] - expected_benchmark) < 1e-12
    assert abs(t20["excess_return"] - (0.2 - expected_benchmark)) < 1e-12
    assert t20["maximum_drawdown"] is not None
    assert t20["calculation_status"] == "complete"


def test_manual_price_series_rejects_duplicate_or_future_rows() -> None:
    payload = _sample_payload()
    payload["prices"][1]["trade_date"] = payload["prices"][0]["trade_date"]
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-manual",
        json=payload,
    )
    assert response.status_code == 422


def test_manual_price_series_does_not_treat_missing_t20_as_zero() -> None:
    payload = _sample_payload()
    payload["prices"] = payload["prices"][:10]
    response = TestClient(_make_app()).post(
        "/investment-research/historical-evaluation/evaluate-manual",
        json=payload,
    )
    assert response.status_code == 200
    t20 = next(row for row in response.json()["horizons"] if row["horizon"] == 20)
    assert t20["asset_return"] is None
    assert t20["data_gap"] == "horizon_out_of_calendar_range"
    assert t20["calculation_status"] == "data_gap"
