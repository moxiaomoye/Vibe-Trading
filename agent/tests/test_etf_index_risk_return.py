"""Phase 3 ETF Research Layer tests - index-proxy risk/panic statistics."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.value_hunter.models import CandidateObservation
from src.value_hunter.providers import (
    AkshareProvider,
    _index_risk_return_stats,
)


def _rows(prices: list[float], start: str = "2024-01-02") -> list[tuple[str, float]]:
    base = date.fromisoformat(start)
    return [
        (start, prices[0]),
    ] + [
        (f"{base.year}-{base.month:02d}-{min(28, base.day) + index:02d}", price)
        for index, price in enumerate(prices[1:], start=1)
    ]


class TestIndexRiskReturnStats:
    def test_insufficient_sample_returns_none(self) -> None:
        assert _index_risk_return_stats(_rows([100.0] * 59)) is None

    def test_flat_history_is_static(self) -> None:
        stats = _index_risk_return_stats(_rows([100.0] * 120))
        assert stats is not None
        assert stats["ann_volatility_pct"] == pytest.approx(0.0, abs=0.0001)
        assert stats["max_drawdown_pct"] == 0.0
        assert stats["panic_sessions_count"] == 0
        assert stats["panic_episodes"] == []
        assert stats["ann_return_pct"] == pytest.approx(0.0, abs=0.0001)

    def test_crash_produces_drawdown_and_panic_sessions(self) -> None:
        prices = [100.0] * 60 + [100.0 * (1 - 0.06) ** step for step in range(1, 11)]
        stats = _index_risk_return_stats(_rows(prices))
        assert stats is not None
        assert stats["max_drawdown_pct"] == pytest.approx(46.1, abs=1.0)
        assert stats["panic_sessions_count"] == 10
        assert len(stats["panic_episodes"]) == 1
        episode = stats["panic_episodes"][0]
        assert episode["drawdown_pct"] == pytest.approx(46.1, abs=1.0)
        assert episode["peak_date"] < episode["trough_date"]

    def test_recovery_starts_a_new_episode(self) -> None:
        prices = (
            [100.0] * 60
            + [100.0 * (1 - 0.06) ** step for step in range(1, 11)]
            + [60.0 * (1.02) ** step for step in range(1, 15)]
            + [150.0 * (1 - 0.05) ** step for step in range(1, 8)]
        )
        stats = _index_risk_return_stats(_rows(prices))
        assert stats is not None
        assert len(stats["panic_episodes"]) == 2
        assert stats["max_drawdown_pct"] == pytest.approx(
            stats["panic_episodes"][0]["drawdown_pct"], abs=0.001
        )

    def test_steady_growth_annualizes(self) -> None:
        daily = 0.0004
        prices = [100.0 * (1 + daily) ** index for index in range(252)]
        stats = _index_risk_return_stats(_rows(prices))
        assert stats is not None
        assert stats["ann_volatility_pct"] == pytest.approx(0.0, abs=0.001)
        expected = ((1 + daily) ** 252 - 1) * 100
        assert stats["ann_return_pct"] == pytest.approx(expected, rel=0.01)

    def test_episodes_are_non_overlapping(self) -> None:
        prices = [100.0] * 60
        for _ in range(3):
            prices.extend([prices[-1] * (1 - 0.08) for _ in range(10)])
            prices.extend([prices[-1] * (1 + 0.05) for _ in range(10)])
        stats = _index_risk_return_stats(_rows(prices))
        assert stats is not None
        episodes = stats["panic_episodes"]
        for index, episode in enumerate(episodes):
            for other in episodes[index + 1:]:
                assert not (episode["peak_date"] <= other["trough_date"]
                            and other["peak_date"] <= episode["trough_date"])

    def test_deterministic(self) -> None:
        rows = _rows([100.0, 98.0, 95.0, 92.0, 94.0, 91.0, 90.0, 93.0] * 20)
        assert _index_risk_return_stats(rows) == _index_risk_return_stats(rows)


class TestEnrichEtfIndexRiskReturn:
    def test_risk_stats_from_underlying_index_cut_at_valuation_as_of(self) -> None:
        january = [f"2026-01-{day:02d}" for day in range(1, 32)]
        february = [f"2026-02-{day:02d}" for day in range(1, 29)]
        march = [f"2026-03-{day:02d}" for day in range(1, 11)]
        dates = january + february + march
        closes = [100.0] * 60 + [100.0 * (1 - 0.06) ** step for step in range(1, 10)]
        frame = pd.DataFrame({"date": dates, "close": closes})

        class FakeAkshare:
            @staticmethod
            def stock_zh_index_daily_em(symbol):
                assert symbol in {"000688", "931743"}
                return frame if symbol == "000688" else frame.iloc[0:1]

        domestic = CandidateObservation(
            "588060", "科创50ETF", "科创板", "宽基",
            security_type="etf",
            etf_valuation={
                "underlying_index_code": "000688",
                "underlying_valuation_as_of": "2026-03-01",
            },
        )
        qdii = CandidateObservation(
            "159941", "纳指ETF", "海外", "纳指",
            security_type="etf",
            etf_valuation={"underlying_index_code": "NDX"},
        )

        AkshareProvider._enrich_etf_index_risk_return(FakeAkshare(), [domestic, qdii])

        valuation = domestic.etf_valuation
        assert valuation["underlying_ann_volatility_pct"] == pytest.approx(0.0, abs=0.0001)
        assert valuation["underlying_max_drawdown_pct"] == 0.0
        assert valuation["underlying_panic_sessions_count"] == 0
        assert valuation["underlying_risk_return_sessions"] == 60
        assert valuation["underlying_risk_return_as_of"] == "2026-03-01"
        assert valuation["underlying_risk_return_method"] != ""
        assert "index_proxy_risk_return" in domestic.source_fields
        assert qdii.etf_valuation.get("underlying_ann_return_pct") is None

    def test_short_history_is_explicit_gap(self) -> None:
        frame = pd.DataFrame({
            "date": ["2026-01-05"],
            "close": [100.0],
        })

        class FakeAkshare:
            @staticmethod
            def stock_zh_index_daily_em(symbol):
                return frame

        candidate = CandidateObservation(
            "159516", "半导体ETF", "半导体", "设备",
            security_type="etf",
            etf_valuation={
                "underlying_index_code": "931743",
                "underlying_valuation_as_of": "2026-01-05",
            },
        )

        AkshareProvider._enrich_etf_index_risk_return(FakeAkshare(), [candidate])

        valuation = candidate.etf_valuation
        assert valuation.get("underlying_ann_return_pct") is None
        assert "样本不足60个交易日" in valuation["underlying_risk_return_gap"]

    def test_failed_fetch_is_explicit_gap(self) -> None:
        class FakeAkshare:
            @staticmethod
            def stock_zh_index_daily_em(symbol):
                raise RuntimeError("network down")

        candidate = CandidateObservation(
            "588200", "芯片ETF", "科创板", "芯片",
            security_type="etf",
            etf_valuation={
                "underlying_index_code": "000685",
                "underlying_valuation_as_of": "2026-01-09",
            },
        )

        AkshareProvider._enrich_etf_index_risk_return(FakeAkshare(), [candidate])

        valuation = candidate.etf_valuation
        assert valuation.get("underlying_ann_return_pct") is None
        assert "读取失败" in valuation["underlying_risk_return_gap"]
        assert any("读取失败" in warning for warning in candidate.warnings)

    def test_no_domestic_index_is_noop(self) -> None:
        candidate = CandidateObservation(
            "159941", "纳指ETF", "海外", "纳指",
            security_type="etf",
            etf_valuation={"underlying_index_code": "NDX"},
        )
        AkshareProvider._enrich_etf_index_risk_return(None, [candidate])
        assert candidate.etf_valuation.get("underlying_ann_return_pct") is None
