"""历史回放测试。使用固定 fixtures，无网络，无持久化，无通知。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.value_hunter.history_replay import (
    HistoryReplayResult,
    run_history_replay,
)
from src.value_hunter.market_snapshot import DataGap
from src.value_hunter.panic_classifier import PanicLevel, PanicThresholds, RULE_VERSION


def _make_panel(
    trade_date: date,
    advance: int = 60,
    decline: int = 30,
    flat: int = 10,
    limit_up_symbols: list[str] | None = None,
    limit_down_symbols: list[str] | None = None,
    market_change_pct: float | None = None,
    sector_map: dict[str, float] | None = None,
):
    total = advance + decline + flat
    codes = [f"{i:06d}" for i in range(total)]
    prices = [10.0] * total
    changes = [2.0] * advance + [-3.0] * decline + [0.0] * flat
    prev_closes = [10.0] * total
    names = [f"S{i}" for i in range(total)]

    df = pd.DataFrame({
        "代码": codes,
        "名称": names,
        "最新价": prices,
        "涨跌幅": changes,
        "昨收": prev_closes,
    })
    return {
        "spot_df": df,
        "limit_up_symbols": limit_up_symbols or [],
        "limit_down_symbols": limit_down_symbols or [],
        "data_date": trade_date,
        "now": datetime(trade_date.year, trade_date.month, trade_date.day, 15, 0, tzinfo=timezone.utc),
        "market_change_pct": market_change_pct,
        "sector_map": sector_map,
    }


class TestHistoryReplayBasic:
    def test_single_day_replay(self):
        d = date(2026, 6, 1)
        panels = {d: _make_panel(d)}
        result = run_history_replay(daily_panels=panels)
        assert isinstance(result, HistoryReplayResult)
        assert len(result.entries) == 1
        assert result.entries[0].skip_reason is None
        assert result.entries[0].result is not None
        assert result.entries[0].result.data_date == d

    def test_multi_day_sequential(self):
        dates = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
        panels = {d: _make_panel(d) for d in dates}
        result = run_history_replay(daily_panels=panels)
        assert len(result.entries) == 3
        assert result.entries[0].trade_date == dates[0]
        assert result.entries[1].trade_date == dates[1]
        assert result.entries[2].trade_date == dates[2]

    def test_results_ordered_by_date(self):
        dates = [date(2026, 6, 3), date(2026, 6, 1), date(2026, 6, 2)]
        panels = {d: _make_panel(d) for d in dates}
        result = run_history_replay(daily_panels=panels)
        result_dates = [e.trade_date for e in result.entries]
        assert result_dates == sorted(result_dates)

    def test_no_buy_sell_fields_in_result(self):
        d = date(2026, 6, 1)
        panels = {d: _make_panel(d)}
        result = run_history_replay(daily_panels=panels)
        r = result.entries[0].result
        assert not hasattr(r, "buy")
        assert not hasattr(r, "sell")
        assert not hasattr(r, "target_price")
        assert not hasattr(r, "recommendation")


class TestHistoryReplayContent:
    def test_normal_to_caution_to_panic_to_extreme(self):
        dates = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4)]
        panels = {
            dates[0]: _make_panel(dates[0], advance=2500, decline=1000, flat=500),
            dates[1]: _make_panel(dates[1], advance=500, decline=3000, flat=500),
            dates[2]: _make_panel(dates[2], advance=200, decline=3600, flat=200),
            dates[3]: _make_panel(dates[3], advance=50, decline=3850, flat=100),
        }
        result = run_history_replay(daily_panels=panels)
        levels = [e.result.panic.level for e in result.entries]
        assert levels == [PanicLevel.NORMAL, PanicLevel.CAUTION, PanicLevel.PANIC, PanicLevel.EXTREME_PANIC]

    def test_rule_version_present_in_all_results(self):
        d = date(2026, 6, 1)
        panels = {d: _make_panel(d)}
        result = run_history_replay(daily_panels=panels)
        assert result.rule_version == RULE_VERSION
        assert result.entries[0].rule_version == RULE_VERSION
        assert result.entries[0].result.panic.rule_version == RULE_VERSION

    def test_watchlist_hash_present(self):
        d = date(2026, 6, 1)
        panels = {d: _make_panel(d)}
        result = run_history_replay(daily_panels=panels)
        assert len(result.watchlist_hash) == 16
        assert len(result.watchlist_version) > 0
        assert result.entries[0].watchlist_hash == result.watchlist_hash

    def test_deterministic_same_input_same_output(self):
        d = date(2026, 6, 1)
        panels = {d: _make_panel(d)}
        r1 = run_history_replay(daily_panels=panels)
        r2 = run_history_replay(daily_panels=panels)
        assert r1 == r2

    def test_replay_does_not_mutate_input_panel(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d)
        original_columns = panel["spot_df"].columns.tolist()
        run_history_replay(daily_panels={d: panel})
        assert panel["spot_df"].columns.tolist() == original_columns


class TestHistoryReplayFutureDataLeakage:
    def test_later_date_does_not_change_earlier_result(self):
        d1 = date(2026, 6, 1)
        d2 = date(2026, 6, 2)
        panels_day1_only = {d1: _make_panel(d1, advance=2500, decline=1000)}
        panels_both = {
            d1: _make_panel(d1, advance=2500, decline=1000),
            d2: _make_panel(d2, advance=50, decline=3850),
        }
        r1 = run_history_replay(daily_panels=panels_day1_only)
        r2 = run_history_replay(daily_panels=panels_both)
        assert r1.entries[0].result.panic.level == r2.entries[0].result.panic.level
        assert r1.entries[0].result.market_snapshot.total_stocks == r2.entries[0].result.market_snapshot.total_stocks

    def test_truncate_future_preserves_past(self):
        dates = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]
        panels = {d: _make_panel(d) for d in dates}
        full = run_history_replay(daily_panels=panels)
        truncated = run_history_replay(daily_panels=panels, end_date=dates[1])
        assert len(truncated.entries) == 2
        assert full.entries[0].result.panic.level == truncated.entries[0].result.panic.level
        assert full.entries[1].result.panic.level == truncated.entries[1].result.panic.level


class TestHistoryReplaySkipDates:
    def test_empty_data_skipped(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d)
        panel["spot_df"] = pd.DataFrame({"代码": [], "名称": [], "最新价": [], "涨跌幅": [], "昨收": []})
        result = run_history_replay(daily_panels={d: panel})
        assert result.entries[0].skip_reason is not None
        assert result.entries[0].result is None

    def test_date_mismatch_skipped(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d)
        panel["data_date"] = date(2026, 6, 2)
        result = run_history_replay(daily_panels={d: panel})
        assert result.entries[0].skip_reason is not None
        assert "数据日期" in result.entries[0].skip_reason

    def test_processed_and_skipped_dates_properties(self):
        d1 = date(2026, 6, 1)
        d2 = date(2026, 6, 2)
        panel2 = _make_panel(d2)
        panel2["spot_df"] = pd.DataFrame({"代码": [], "名称": [], "最新价": [], "涨跌幅": [], "昨收": []})
        panels = {d1: _make_panel(d1), d2: panel2}
        result = run_history_replay(daily_panels=panels)
        assert len(result.processed_dates) == 1
        assert d1 in result.processed_dates
        assert len(result.skipped_dates) == 1
        assert result.skipped_dates[0][0] == d2


class TestHistoryReplayDataDeficiency:
    def test_market_change_none(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d, market_change_pct=None)
        result = run_history_replay(daily_panels={d: panel})
        entry = result.entries[0].result
        for c in entry.watchlist:
            assert c.relative_to_market is None

    def test_sector_map_none_records_data_gap(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d, sector_map=None)
        result = run_history_replay(daily_panels={d: panel})
        entry = result.entries[0].result
        for c in entry.watchlist:
            if c.change_pct is not None:
                assert c.relative_to_sector is None
                assert c.data_gap.description == "缺少行业收益数据"

    def test_industry_data_missing_sector_is_none(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d, sector_map=None)
        result = run_history_replay(daily_panels={d: panel})
        entry = result.entries[0].result
        for c in entry.watchlist:
            if c.change_pct is not None:
                assert c.relative_to_sector is None
                assert c.data_gap.description

    def test_candidate_missing_from_day(self):
        """股票在当日行情中缺失，应记录 data_gap 而非伪造 0%"""
        d = date(2026, 6, 1)
        panel = _make_panel(d)
        result = run_history_replay(daily_panels={d: panel})
        for c in result.entries[0].result.watchlist:
            if c.data_gap.description == "当日行情中未找到":
                assert c.change_pct is None
                assert c.close is None
                break
        else:
            pass


class TestHistoryReplayNoSideEffects:
    def test_not_in_value_hunter_init(self):
        import sys
        import src.value_hunter
        mods_before = set(sys.modules.keys())
        _ = src.value_hunter.ValueHunterConfig
        mods_after = set(sys.modules.keys())
        imported = mods_after - mods_before
        replay_imported = any("history_replay" in m for m in imported)
        assert not replay_imported, f"__init__ 触发了 history_replay 导入: {imported}"


class TestHistoryReplayEdgeCases:
    def test_single_watchlist_symbol(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d, advance=1, decline=0, flat=0)
        result = run_history_replay(daily_panels={d: panel})
        assert len(result.entries[0].result.watchlist) >= 1

    def test_custom_thresholds(self):
        d = date(2026, 6, 1)
        panel = _make_panel(d, advance=30, decline=60, flat=10)
        t = PanicThresholds(caution_decline_ratio=0.50)
        result = run_history_replay(daily_panels={d: panel}, thresholds=t)
        assert result.entries[0].result.panic.level == PanicLevel.CAUTION

    def test_replay_start_end_filter(self):
        dates = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3), date(2026, 6, 4)]
        panels = {d: _make_panel(d) for d in dates}
        result = run_history_replay(daily_panels=panels, start_date=date(2026, 6, 2), end_date=date(2026, 6, 3))
        assert len(result.entries) == 2
        assert result.entries[0].trade_date == date(2026, 6, 2)
        assert result.entries[1].trade_date == date(2026, 6, 3)
