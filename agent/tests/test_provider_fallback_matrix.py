"""W5 — Provider failure/fallback matrix tests.

All tests use fake/mocked providers to simulate failure modes without
real network access.  Covers the ValueHunterMarketAdapter and its
market observation provider contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from src.investment_research.integrations.value_hunter_market import (
    MarketObservationProvider,
    ValueHunterMarketAdapter,
)
from src.value_hunter.providers import DemoProvider

NOW = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)


@dataclass
class FakeMarketData:
    """Minimal market data shape matching DemoProvider output."""

    name: str
    as_of: str
    indices: tuple
    advance: int
    decline: int
    total_stocks: int
    limit_down: int
    median_daily_return: float
    advancer_ratio: float
    limit_down_count: int
    turnover_zscore: float | None
    drawdown_252_pct: float | None
    warnings: tuple[str, ...] = ()


class FakeSuccessfulProvider(MarketObservationProvider):
    name = "fake_success"

    def load_market(self) -> FakeMarketData:
        return FakeMarketData(
            name="fake_success",
            as_of="2026-07-21",
            indices=(),
            advance=2000,
            decline=2800,
            total_stocks=5000,
            limit_down=5,
            median_daily_return=-0.02,
            advancer_ratio=0.4,
            limit_down_count=5,
            turnover_zscore=-0.5,
            drawdown_252_pct=-0.15,
        )


class FakeEmptyProvider(MarketObservationProvider):
    name = "fake_empty"

    def load_market(self) -> FakeMarketData:
        return FakeMarketData(
            name="fake_empty",
            as_of="2026-07-21",
            indices=(),
            advance=0,
            decline=0,
            total_stocks=0,
            limit_down=0,
            median_daily_return=None,
            advancer_ratio=None,
            limit_down_count=None,
            turnover_zscore=None,
            drawdown_252_pct=None,
            warnings=("no_data",),
        )


class SlowFakeProvider(FakeSuccessfulProvider):
    name = "slow_fake"

    def load_market(self) -> FakeMarketData:
        import time
        time.sleep(10)
        return super().load_market()


class TestSuccessfulProvider:
    """Happy path: provider returns valid data."""

    def test_returns_bundle(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        bundle = adapter.load(NOW)
        assert bundle.snapshot is not None
        assert bundle.evidence_bundle is not None
        assert len(bundle.evidence) >= 1

    def test_evidence_content_hash(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        bundle = adapter.load(NOW)
        assert bundle.evidence[0].content_hash is not None
        assert len(bundle.evidence[0].content_hash) > 0

    def test_snapshot_fields_present(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        bundle = adapter.load(NOW)
        assert bundle.snapshot.advancer_ratio is not None
        assert bundle.snapshot.limit_down_count is not None


class TestEmptyProvider:
    """Provider returns empty/minimal data."""

    def test_empty_data_returns_bundle(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeEmptyProvider())
        bundle = adapter.load(NOW)
        assert bundle.snapshot is not None
        assert "no_data" in bundle.snapshot.data_gaps

    def test_evidence_quality_warnings(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeEmptyProvider())
        bundle = adapter.load(NOW)
        assert "no_data" in bundle.evidence[0].quality_warnings


class TestProviderIdempotency:
    """Repeated calls with the same provider must return identical results."""

    def test_demo_provider_idempotent(self) -> None:
        adapter = ValueHunterMarketAdapter(DemoProvider())
        r1 = adapter.load(NOW)
        r2 = adapter.load(NOW)
        assert r1 == r2

    def test_fake_provider_idempotent(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        r1 = adapter.load(NOW)
        r2 = adapter.load(NOW)
        assert r1 == r2


class TestProviderTimeout:
    """Slow provider must be terminated gracefully."""

    def test_slow_provider_times_out(self) -> None:
        adapter = ValueHunterMarketAdapter(SlowFakeProvider())
        with pytest.raises(TimeoutError, match="slow_fake"):
            adapter.load_with_timeout(NOW, timeout_seconds=0.05)

    def test_fast_provider_no_timeout(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        # Should complete well within 10s
        adapter.load_with_timeout(NOW, timeout_seconds=10.0)


class TestInvalidInput:
    """Adapter must reject invalid inputs gracefully."""

    def test_rejects_naive_datetime(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        with pytest.raises(ValueError, match="timezone-aware"):
            adapter.load(datetime(2026, 7, 21, 10, 30))

    def test_rejects_negative_timeout(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        with pytest.raises(ValueError, match="timeout must be positive"):
            adapter.load_with_timeout(NOW, timeout_seconds=-1)

    def test_rejects_zero_timeout(self) -> None:
        adapter = ValueHunterMarketAdapter(FakeSuccessfulProvider())
        with pytest.raises(ValueError, match="timeout must be positive"):
            adapter.load_with_timeout(NOW, timeout_seconds=0)
