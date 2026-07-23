from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from src.value_hunter.panic_scan import run_panic_scan
from src.value_hunter.post_close_provider import (
    AksharePostCloseProvider,
    PostCloseData,
    SinaSpotAdapter,
)


TODAY = date(2026, 7, 22)
NOW = datetime(2026, 7, 22, 18, 30, tzinfo=timezone.utc)


class FakeAkshare:
    def __init__(self, *, fail_spot_once: bool = False):
        self.fail_spot_once = fail_spot_once
        self.spot_calls = 0

    def stock_zh_a_spot_em(self):
        self.spot_calls += 1
        if self.fail_spot_once and self.spot_calls == 1:
            raise ConnectionError("temporary fixture failure")
        return pd.DataFrame(
            {
                "代码": ["600522", "300308"],
                "名称": ["fixture-a", "fixture-b"],
                "最新价": [10.0, 20.0],
                "涨跌幅": [-5.0, 2.0],
                "昨收": [10.5, 19.6],
            }
        )

    def stock_zh_index_daily_em(self, *, symbol):
        assert symbol == "sh000300"
        return pd.DataFrame(
            {
                "date": ["2026-07-21", "2026-07-22"],
                "close": [100.0, 98.0],
            }
        )

    def stock_zt_pool_em(self, *, date):
        assert date == "20260722"
        return pd.DataFrame({"代码": ["300308"]})

    def stock_zt_pool_dtgc_em(self, *, date):
        assert date == "20260722"
        return pd.DataFrame({"代码": ["600522"]})

    def stock_board_industry_name_em(self):
        return pd.DataFrame({"板块名称": ["半导体"], "涨跌幅": [-3.0]})


class FakeSinaAkshare:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.spot_calls = 0

    def stock_zh_a_spot(self):
        self.spot_calls += 1
        if self.fail:
            raise ConnectionError("Sina fixture unavailable")
        return pd.DataFrame(
            {
                "代码": ["sh600522", "sz300308"],
                "名称": ["fixture-a", "fixture-b"],
                "最新价": [10.0, 20.0],
                "涨跌幅": [-5.0, 2.0],
                "昨收": [10.5, 19.6],
                "成交量": [123400.0, 900.0],
            }
        )


def _provider(fake=None):
    return AksharePostCloseProvider(
        ak_module=fake or FakeAkshare(),
        today=lambda: TODAY,
        now=lambda: NOW,
    )


def _sina_adapter(fake=None):
    return SinaSpotAdapter(
        ak_module=fake or FakeSinaAkshare(),
        today=lambda: TODAY,
        now=lambda: NOW,
    )


def test_sina_spot_normalizes_codes_volume_and_point_in_time_metadata():
    fake = FakeSinaAkshare()
    result = _sina_adapter(fake).load(as_of=TODAY)

    assert fake.spot_calls == 1
    assert result.source == "akshare_sina"
    assert result.source_date == TODAY
    assert result.availability_date == TODAY
    assert result.retrieved_at == NOW
    assert result.spot_df["代码"].tolist() == ["600522", "300308"]
    assert result.spot_df["成交量"].tolist() == [1234.0, 9.0]
    assert {item.symbol for item in result.symbol_metadata} == {"600522", "300308"}
    assert result.errors == ()


def test_sina_spot_rejects_historical_request_before_network_call():
    fake = FakeSinaAkshare()
    result = _sina_adapter(fake).load(as_of=date(2026, 7, 21))

    assert fake.spot_calls == 0
    assert result.spot_df.empty
    assert result.source_date == date(2026, 7, 21)
    assert result.availability_date == TODAY
    assert result.data_gaps[0].field == "all_a_spot"


def test_sina_spot_attempts_paged_endpoint_only_once_on_failure():
    fake = FakeSinaAkshare(fail=True)
    result = _sina_adapter(fake).load(as_of=TODAY)

    assert fake.spot_calls == 1
    assert result.spot_df.empty
    assert result.errors[0].operation == "all_a_spot_sina"
    assert result.errors[0].attempts == 1
    assert result.errors[0].retryable is True


def test_provider_normalizes_post_close_contract():
    result = _provider().load(as_of=TODAY)
    assert isinstance(result, PostCloseData)
    assert result.source_date == TODAY
    assert result.availability_date == TODAY
    assert result.retrieved_at == NOW
    assert result.benchmark_returns["000300.SH"] == -0.02
    assert result.limit_up_symbols == frozenset({"300308"})
    assert result.limit_down_symbols == frozenset({"600522"})
    assert result.sector_returns == {"半导体": -0.03}
    assert {item.symbol for item in result.symbol_metadata} == {"600522", "300308"}
    assert any(gap.field == "sector_memberships" for gap in result.data_gaps)


def test_provider_retries_once_then_succeeds():
    fake = FakeAkshare(fail_spot_once=True)
    result = _provider(fake).load(as_of=TODAY)
    assert fake.spot_calls == 2
    assert not result.spot_df.empty
    assert not any(error.operation == "all_a_spot" for error in result.errors)


def test_historical_spot_request_is_rejected_without_network_call():
    fake = FakeAkshare()
    result = _provider(fake).load(as_of=date(2026, 7, 21))
    assert fake.spot_calls == 0
    assert result.spot_df.empty
    assert result.data_gaps[0].field == "all_a_spot"
    assert result.availability_date == TODAY


def test_panel_conversion_preserves_dates_source_and_gaps():
    result = _provider().load(as_of=TODAY)
    panel = result.to_panel_data()
    assert panel["data_date"] == TODAY
    assert panel["availability_date"] == TODAY
    assert panel["source"] == "akshare"
    assert panel["market_change_pct"] == -0.02
    assert panel["sector_map"] == {}
    assert panel["data_gaps"] == list(result.data_gaps)


def test_live_scan_uses_injected_provider_without_not_implemented(tmp_path):
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text(
        'version: "test"\nwatchlist:\n  name: "fixture"\n  symbols:\n    - "600522.SH"\n',
        encoding="utf-8",
    )
    result = run_panic_scan(
        provider=_provider(),
        as_of=TODAY,
        watchlist_path=str(watchlist),
    )
    assert result.data_date == TODAY
    assert result.availability_date == TODAY
    assert result.source == "akshare"
    assert result.watchlist[0].symbol == "600522.SH"
    assert any(gap.field == "sector_memberships" for gap in result.data_gaps)


def test_provider_initialization_failure_is_structured(monkeypatch):
    provider = AksharePostCloseProvider(today=lambda: TODAY, now=lambda: NOW)

    def unavailable():
        raise RuntimeError("fixture provider unavailable")

    monkeypatch.setattr(provider, "_ak", unavailable)
    result = provider.load(as_of=TODAY)
    assert result.spot_df.empty
    assert result.errors[0].operation == "provider_initialization"
    assert result.errors[0].retryable is False
    assert result.data_gaps[0].field == "all_a_spot"


def test_empty_limit_up_pool_produces_gap():
    fake = FakeAkshare()
    fake.stock_zt_pool_em = lambda *, date: pd.DataFrame({"代码": []})
    result = _provider(fake).load(as_of=TODAY)
    assert result.limit_up_symbols == frozenset()
    assert any(
        gap.field == "limit_up_pool" and "empty" in gap.reason
        for gap in result.data_gaps
    )


def test_spot_without_code_column_skips_metadata():
    fake = FakeAkshare()
    fake.stock_zh_a_spot_em = lambda **_: pd.DataFrame({
        "symbol": ["600522", "300308"],
        "名称": ["fixture-a", "fixture-b"],
        "最新价": [10.0, 20.0],
        "涨跌幅": [-5.0, 2.0],
        "昨收": [10.5, 19.6],
    })
    result = _provider(fake).load(as_of=TODAY)
    assert result.symbol_metadata == ()
    assert any(gap.field == "symbol_metadata" for gap in result.data_gaps)


def test_permanently_failing_sector_endpoint_produces_error_and_gap():
    fake = FakeAkshare()
    fake.stock_board_industry_name_em = lambda **_: (_ for _ in ()).throw(
        ConnectionError("upstream sector fixture dead"),
    )
    result = _provider(fake).load(as_of=TODAY)
    assert result.sector_returns == {}
    assert any(
        err.operation == "sector_returns" and err.retryable is True
        for err in result.errors
    )
    assert any(
        gap.field == "sector_returns" and "unavailable" in gap.reason
        for gap in result.data_gaps
    )
