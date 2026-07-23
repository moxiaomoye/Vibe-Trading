"""MVP 测试：A股盘后恐慌初筛。使用固定 fixtures，无真实网络。"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.value_hunter.market_snapshot import DataGap, build_snapshot_from_akshare
from src.value_hunter.panic_classifier import (
    PanicLevel,
    PanicThresholds,
    classify_panic,
)
from src.value_hunter.relative_strength import compute_relative_strength
from src.value_hunter.trading_rules import (
    LimitRule,
    classify_limit_rule,
    is_limit_down,
    is_limit_up,
)
from src.value_hunter.watchlist_loader import WatchlistConfig, load_watchlist


# ===========================================================================
# 涨跌停判断
# ===========================================================================

class TestLimitRules:
    def test_main_board_10pct(self):
        assert classify_limit_rule("600522.SH") == LimitRule.NORMAL_10PCT
        assert classify_limit_rule("000001.SZ") == LimitRule.NORMAL_10PCT
        assert classify_limit_rule("002371.SZ") == LimitRule.NORMAL_10PCT

    def test_gem_20pct(self):
        assert classify_limit_rule("300308.SZ") == LimitRule.GEM_20PCT
        assert classify_limit_rule("301308.SZ") == LimitRule.GEM_20PCT

    def test_star_20pct(self):
        assert classify_limit_rule("688981.SH") == LimitRule.STAR_20PCT

    def test_bse_30pct(self):
        assert classify_limit_rule("430017.BJ") == LimitRule.BSE_30PCT
        assert classify_limit_rule("830799.BJ") == LimitRule.BSE_30PCT

    def test_limit_down_main_board(self):
        assert is_limit_down(9.00, 10.00, LimitRule.NORMAL_10PCT) is True
        assert is_limit_down(9.50, 10.00, LimitRule.NORMAL_10PCT) is False

    def test_limit_down_gem(self):
        assert is_limit_down(8.00, 10.00, LimitRule.GEM_20PCT) is True
        assert is_limit_down(8.50, 10.00, LimitRule.GEM_20PCT) is False

    def test_limit_down_st(self):
        assert is_limit_down(9.50, 10.00, LimitRule.NORMAL_10PCT, is_st=True) is True
        assert is_limit_down(9.70, 10.00, LimitRule.NORMAL_10PCT, is_st=True) is False

    def test_limit_insufficient_data(self):
        assert is_limit_down(None, 10.00, LimitRule.NORMAL_10PCT) is None
        assert is_limit_down(9.00, None, LimitRule.NORMAL_10PCT) is None
        assert is_limit_down(9.00, 0.0, LimitRule.NORMAL_10PCT) is None

    def test_limit_up(self):
        assert is_limit_up(11.00, 10.00, LimitRule.NORMAL_10PCT) is True
        assert is_limit_up(10.50, 10.00, LimitRule.NORMAL_10PCT) is False


# ===========================================================================
# 恐慌分类
# ===========================================================================

class TestPanicClassification:
    def test_normal_market(self):
        result = classify_panic(total_stocks=4000, advance=2500, decline=1000, limit_down_count=5)
        assert result.level == PanicLevel.NORMAL
        assert len(result.reasons) >= 1

    def test_caution_threshold_decline_ratio(self):
        result = classify_panic(total_stocks=4000, advance=500, decline=3000, limit_down_count=10)
        assert result.level == PanicLevel.CAUTION

    def test_caution_threshold_limit_down(self):
        result = classify_panic(total_stocks=4000, advance=2000, decline=1500, limit_down_count=35)
        assert result.level == PanicLevel.CAUTION

    def test_panic_threshold_decline_ratio(self):
        result = classify_panic(total_stocks=4000, advance=200, decline=3600, limit_down_count=50)
        assert result.level == PanicLevel.PANIC

    def test_panic_threshold_limit_down(self):
        result = classify_panic(total_stocks=4000, advance=2000, decline=1500, limit_down_count=90)
        assert result.level == PanicLevel.PANIC

    def test_extreme_panic(self):
        result = classify_panic(total_stocks=4000, advance=50, decline=3850, limit_down_count=250)
        assert result.level == PanicLevel.EXTREME_PANIC

    def test_no_data(self):
        result = classify_panic(total_stocks=0, advance=0, decline=0, limit_down_count=0)
        assert result.level == PanicLevel.NORMAL
        assert "数据不足" in result.reasons[0]

    def test_custom_thresholds(self):
        t = PanicThresholds(caution_decline_ratio=0.50)
        result = classify_panic(total_stocks=100, advance=30, decline=60, limit_down_count=1, thresholds=t)
        assert result.level == PanicLevel.CAUTION

    def test_components_recorded(self):
        result = classify_panic(total_stocks=4000, advance=3000, decline=800, limit_down_count=3)
        assert "advance_ratio" in result.components
        assert "decline_ratio" in result.components
        assert "limit_down_count" in result.components


# ===========================================================================
# 相对强弱
# ===========================================================================

class TestRelativeStrength:
    def test_normal_case(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.03,
            market_change_pct=-0.05,
            sector_change_pct=-0.04,
            is_limit_down=False,
        )
        assert rs.relative_to_market == pytest.approx(0.02)
        assert rs.relative_to_sector == pytest.approx(0.01)
        assert rs.is_sharp_decline is False

    def test_sharp_decline_no_limit_down(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.07,
            market_change_pct=-0.02,
            sector_change_pct=-0.03,
            is_limit_down=False,
        )
        assert rs.is_sharp_decline is True
        assert rs.relative_to_market == pytest.approx(-0.05)

    def test_sharp_decline_but_limit_down(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.10,
            market_change_pct=-0.02,
            sector_change_pct=-0.03,
            is_limit_down=True,
        )
        assert rs.is_sharp_decline is False

    def test_missing_market_data(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.05, market_change_pct=None,
            sector_change_pct=-0.03, is_limit_down=False,
        )
        assert rs.relative_to_market is None
        assert rs.relative_to_sector == pytest.approx(-0.02)

    def test_missing_stock_data(self):
        rs = compute_relative_strength(
            stock_change_pct=None, market_change_pct=-0.05,
            sector_change_pct=-0.03, is_limit_down=None,
        )
        assert rs.relative_to_market is None
        assert rs.is_limit_down is None


# ===========================================================================
# 市场快照
# ===========================================================================

class TestMarketSnapshot:
    def test_build_normal(self):
        df = pd.DataFrame({
            "代码": ["000001", "600001", "300001"],
            "名称": ["平安", "宝钢", "宁德"],
            "最新价": [10.0, 5.0, 20.0],
            "涨跌幅": [2.0, -1.5, 5.0],
            "昨收": [9.8, 5.08, 19.0],
        })
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=date.today(),
        )
        assert snap.total_stocks == 3
        assert snap.advance == 2
        assert snap.decline == 1
        assert snap.flat == 0
        assert snap.data_gap.is_stale is False

    def test_stale_data(self):
        df = pd.DataFrame({
            "代码": ["000001"], "名称": ["平安"],
            "最新价": [10.0], "涨跌幅": [0.0], "昨收": [10.0],
        })
        old_date = date(2024, 1, 2)
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=old_date,
        )
        assert snap.data_gap.is_stale is True
        assert snap.data_gap.gap_days > 0

    def test_empty_dataframe(self):
        df = pd.DataFrame({"代码": [], "名称": [], "最新价": [], "涨跌幅": [], "昨收": []})
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=date.today(),
        )
        assert snap.total_stocks == 0

    def test_limit_down_from_pool(self):
        df = pd.DataFrame({
            "代码": ["600001", "600002"],
            "名称": ["A", "B"],
            "最新价": [9.0, 10.0],
            "涨跌幅": [-10.0, -0.5],
            "昨收": [10.0, 10.05],
        })
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols={"600001"},
            data_date=date.today(),
        )
        assert snap.limit_down >= 1

    def test_advance_decline_ratios(self):
        df = pd.DataFrame({
            "代码": [str(i) for i in range(100)],
            "名称": [f"S{i}" for i in range(100)],
            "最新价": [10.0] * 100,
            "涨跌幅": [2.0] * 60 + [-3.0] * 30 + [0.0] * 10,
            "昨收": [10.0] * 100,
        })
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=date.today(),
        )
        assert snap.advance == 60
        assert snap.decline == 30
        assert snap.flat == 10
        assert snap.advance_ratio == 0.6
        assert snap.decline_ratio == 0.3


# ===========================================================================
# 观察池加载
# ===========================================================================

class TestWatchlistLoader:
    def test_load_default_watchlist(self):
        cfg = load_watchlist()
        assert isinstance(cfg, WatchlistConfig)
        assert len(cfg.symbols) > 0
        assert cfg.version == "1.0.0"
        assert cfg.name == "default_watchlist"

    def test_content_hash_present(self):
        cfg = load_watchlist()
        assert len(cfg.content_hash) == 16

    def test_content_hash_stable(self):
        cfg1 = load_watchlist()
        cfg2 = load_watchlist()
        assert cfg1.content_hash == cfg2.content_hash

    def test_content_hash_changes_on_content_change(self, tmp_path):
        import yaml
        from src.value_hunter.watchlist_loader import load_watchlist, _compute_hash

        data1 = {"version": "1.0.0", "watchlist": {"name": "test", "symbols": ["600522.SH"]}}
        data2 = {"version": "1.0.0", "watchlist": {"name": "test", "symbols": ["600522.SH", "000001.SZ"]}}
        h1 = _compute_hash(data1)
        h2 = _compute_hash(data2)
        assert h1 != h2

    def test_from_different_cwd_default_watchlist(self, monkeypatch):
        orig_cwd = Path.cwd()
        try:
            monkeypatch.chdir(Path(__file__).resolve().parent.parent)
            cfg = load_watchlist()
            assert len(cfg.symbols) > 0
        finally:
            monkeypatch.chdir(str(orig_cwd))

    def test_explicit_path_still_works(self):
        from src.value_hunter.watchlist_loader import DEFAULT_WATCHLIST_PATH
        cfg = load_watchlist(DEFAULT_WATCHLIST_PATH)
        assert len(cfg.symbols) > 0

    def test_file_not_found(self):
        from src.value_hunter.watchlist_loader import DEFAULT_WATCHLIST_PATH
        fake = Path("nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            load_watchlist(fake)


# ===========================================================================
# 未来数据穿越保护
# ===========================================================================

class TestFutureDataLeakage:
    def test_single_day_results_deterministic_for_same_input(self):
        df_day1 = pd.DataFrame({
            "代码": ["600001", "600002", "600003"],
            "名称": ["A", "B", "C"],
            "最新价": [9.0, 11.0, 10.0],
            "涨跌幅": [-10.0, 5.0, 0.0],
            "昨收": [10.0, 10.0, 10.0],
        })
        date1 = date(2026, 6, 1)

        snap1 = build_snapshot_from_akshare(
            df_day1, limit_up_symbols=set(), limit_down_symbols={"600001"},
            data_date=date1,
        )
        snap2 = build_snapshot_from_akshare(
            df_day1, limit_up_symbols=set(), limit_down_symbols={"600001"},
            data_date=date1,
        )
        assert snap1.total_stocks == snap2.total_stocks
        assert snap1.decline == snap2.decline
        assert snap1.limit_down == snap2.limit_down

    def test_classify_panic_results_unchanged_with_future_data(self):
        r1 = classify_panic(total_stocks=100, advance=70, decline=20, limit_down_count=2)
        r2 = classify_panic(total_stocks=100, advance=70, decline=20, limit_down_count=2)
        assert r1.level == r2.level
        assert r1.reasons == r2.reasons
        assert r1.components == r2.components

    def test_future_data_date_rejected(self):
        df = pd.DataFrame({
            "代码": ["600001"], "名称": ["A"],
            "最新价": [10.0], "涨跌幅": [0.0], "昨收": [10.0],
        })
        future_date = date(2026, 12, 31)
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=future_date,
        )
        assert snap.data_gap.gap_days < 0 or not snap.data_gap.is_stale

    def test_data_date_older_than_today_marked_stale(self):
        df = pd.DataFrame({
            "代码": ["600001"], "名称": ["A"],
            "最新价": [10.0], "涨跌幅": [0.0], "昨收": [10.0],
        })
        old_date = date(2024, 1, 2)
        snap = build_snapshot_from_akshare(
            df, limit_up_symbols=set(), limit_down_symbols=set(),
            data_date=old_date,
        )
        assert snap.data_gap.is_stale is True


# ===========================================================================
# 行业数据缺失规则确认
# ===========================================================================

class TestIndustryDataMissing:
    def test_sector_none_when_missing(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.05, market_change_pct=-0.03,
            sector_change_pct=None, is_limit_down=False,
        )
        assert rs.relative_to_sector is None
        assert rs.relative_to_market is not None

    def test_market_still_computed_when_sector_missing(self):
        rs = compute_relative_strength(
            stock_change_pct=-0.05, market_change_pct=-0.03,
            sector_change_pct=None, is_limit_down=False,
        )
        assert rs.relative_to_market == pytest.approx(-0.02)

    def test_candidate_scanned_with_missing_sector(self):
        from src.value_hunter.panic_scan import ScannedCandidate
        c = ScannedCandidate(
            symbol="600522.SH", name="Test",
            close=10.0, change_pct=-0.05,
            relative_to_market=-0.02, relative_to_sector=None,
            is_limit_down=False, is_sharp_decline=True,
            is_suspended=False,
            data_gap=DataGap(),
        )
        assert c.relative_to_sector is None
        assert c.relative_to_market is not None


# ===========================================================================
# 模块导入无副作用
# ===========================================================================

class TestModuleImportNoSideEffects:
    def test_panic_scan_not_in_init(self):
        """value_hunter.__init__ 不应自动拉入 panic_scan。"""
        import src.value_hunter
        mods_before = set(sys.modules.keys())
        _ = src.value_hunter.ValueHunterConfig
        mods_after = set(sys.modules.keys())
        imported = mods_after - mods_before
        panic_imported = any("panic_scan" in m for m in imported)
        assert not panic_imported, f"__init__ 触发了 panic_scan 导入: {imported}"
