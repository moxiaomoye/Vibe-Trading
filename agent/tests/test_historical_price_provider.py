from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from src.investment_research.operations.historical_price_provider import (
    HistoricalPriceProvider,
    HistoricalPriceProviderError,
)


def _frame(*, start: str = "2025-07-21", periods: int = 21, base: float = 10.0):
    index = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"close": [base + i for i in range(periods)]}, index=index)


@pytest.fixture(autouse=True)
def provider_configs(monkeypatch):
    def status(provider: str):
        return SimpleNamespace(provider=provider, configured=False)

    monkeypatch.setattr(
        "src.investment_research.operations.historical_price_provider.get_provider_config",
        status,
    )


def test_existing_tencent_loader_supplies_both_components(monkeypatch) -> None:
    def fetch(source, symbol, *_):
        assert source == "tencent"
        return _frame(base=4000.0 if symbol == "000300.SH" else 10.0)

    monkeypatch.setattr(HistoricalPriceProvider, "_fetch_loader_frame", staticmethod(fetch))

    result = HistoricalPriceProvider().fetch(
        "000001", date(2025, 7, 21), horizon=20
    )

    assert result.component_sources == {
        "stock": "tencent",
        "benchmark": "tencent",
    }
    assert result.coverage["row_count"] == 21
    assert result.coverage["last_trade_date"] == "2025-08-18"
    assert list(result.prices.columns) == ["asset_close", "benchmark_close"]


def test_stock_falls_back_to_akshare_without_replacing_benchmark(monkeypatch) -> None:
    def fetch(source, symbol, *_):
        if source == "tencent" and symbol != "000300.SH":
            raise OSError("temporary upstream connection failure")
        return _frame(base=4000.0 if symbol == "000300.SH" else 10.0)

    monkeypatch.setattr(HistoricalPriceProvider, "_fetch_loader_frame", staticmethod(fetch))

    result = HistoricalPriceProvider().fetch(
        "600000", date(2025, 7, 21), horizon=20
    )

    assert result.component_sources["stock"] == "akshare"
    assert result.component_sources["benchmark"] == "tencent"
    failed = [
        attempt
        for attempt in result.attempts
        if attempt.provider == "tencent"
        and attempt.component == "stock"
        and attempt.status == "failed"
    ]
    assert failed[0].category == "network"


def test_non_trading_date_resolves_to_previous_common_trading_day(
    monkeypatch,
) -> None:
    def fetch(source, symbol, *_):
        return _frame(
            start="2025-07-14",
            periods=30,
            base=4000.0 if symbol == "000300.SH" else 10.0,
        )

    monkeypatch.setattr(
        HistoricalPriceProvider,
        "_fetch_loader_frame",
        staticmethod(fetch),
    )

    result = HistoricalPriceProvider().fetch(
        "000001", date(2025, 7, 20), horizon=20
    )

    assert result.requested_evaluation_date == date(2025, 7, 20)
    assert result.evaluation_date == date(2025, 7, 18)
    assert result.date_resolution == "previous_common_trading_day"
    assert result.prices.index[0].date() == date(2025, 7, 18)


def test_missing_t20_coverage_is_structured(monkeypatch) -> None:
    monkeypatch.setattr(
        HistoricalPriceProvider,
        "_fetch_loader_frame",
        staticmethod(lambda *_: _frame(periods=10)),
    )

    with pytest.raises(HistoricalPriceProviderError) as caught:
        HistoricalPriceProvider().fetch(
            "000001", date(2025, 7, 21), horizon=20
        )

    assert caught.value.code == "date_not_covered"
    assert "T+20" in str(caught.value)


def test_no_provider_data_reports_every_attempt(monkeypatch) -> None:
    monkeypatch.setattr(
        HistoricalPriceProvider,
        "_fetch_loader_frame",
        staticmethod(lambda *_: None),
    )
    monkeypatch.setattr(
        HistoricalPriceProvider,
        "_fetch_akshare_benchmark",
        staticmethod(lambda *_: None),
    )

    with pytest.raises(HistoricalPriceProviderError) as caught:
        HistoricalPriceProvider().fetch(
            "000001", date(2025, 7, 21), horizon=20
        )

    assert caught.value.code == "provider_unavailable"
    attempted = {
        (attempt.provider, attempt.component, attempt.category)
        for attempt in caught.value.attempts
    }
    assert ("tencent", "stock", "no_data") in attempted
    assert ("akshare", "stock", "no_data") in attempted
    assert ("tencent", "benchmark", "no_data") in attempted
    assert ("akshare_index_em", "benchmark", "no_data") in attempted
