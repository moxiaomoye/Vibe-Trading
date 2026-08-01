from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.value_hunter.models import CandidateObservation, IndexObservation, MarketObservation
from src.value_hunter.providers import AkshareProvider, _latest_complete_weekday
from src.value_hunter.providers import normalize_ashare_symbol, security_type_for_symbol


def test_akshare_daily_cache_round_trip(tmp_path):
    provider = AkshareProvider(cache_dir=tmp_path)
    market = MarketObservation(
        as_of="2026-07-20",
        indices=[IndexObservation("sh000300", "沪深300", 4000, -1.2, -12.0, True, False)],
        advancer_ratio=0.25,
        above_ma60_ratio=None,
        limit_down_count=20,
        turnover_zscore=None,
        source="test",
        coverage=["indices", "spot_breadth"],
    )
    candidates = [
        CandidateObservation(
            symbol="688981",
            name="中芯国际",
            sector="半导体制造",
            theme="国产芯片",
            pe_ttm=35.0,
            source_fields=["test"],
        )
    ]

    provider._write_cache("market", market)
    provider._write_cache("candidates", candidates)

    loaded_market = provider._read_market_cache()
    loaded_candidates = provider._read_candidate_cache()
    assert loaded_market is not None
    assert loaded_market.indices[0].name == "沪深300"
    assert "使用当日缓存行情" in loaded_market.warnings
    assert loaded_candidates is not None
    assert loaded_candidates[0].pe_ttm == 35.0


def test_candidate_cache_uses_latest_available_file_and_marks_staleness(tmp_path) -> None:
    cache = tmp_path / "akshare-candidates-2026-07-22.json"
    cache.write_text(
        '[{"symbol":"688981","name":"SMIC","sector":"Semiconductor","theme":"Foundry"}]',
        encoding="utf-8",
    )
    provider = AkshareProvider(cache_dir=tmp_path)

    candidates = provider._read_candidate_cache()

    assert candidates is not None
    assert candidates[0].symbol == "688981"
    assert "2026-07-22" in candidates[0].warnings[0]


def test_candidate_cache_is_ignored_when_watchlist_symbols_change(tmp_path) -> None:
    cache = tmp_path / "akshare-candidates-2026-07-22.json"
    cache.write_text(
        '[{"symbol":"688981","name":"SMIC","sector":"Semiconductor","theme":"Foundry"}]',
        encoding="utf-8",
    )
    watchlist = tmp_path / "watchlist.csv"
    watchlist.write_text(
        "symbol,name,sector,theme\n600522,ZTT,Telecom,Cable\n",
        encoding="utf-8",
    )
    provider = AkshareProvider(watchlist_path=watchlist, cache_dir=tmp_path)

    assert provider._read_candidate_cache() is None


def test_market_history_enrichment_uses_normalized_stock_and_etf_symbols() -> None:
    def fetcher(**kwargs):
        assert kwargs["source"] == "auto"
        assert set(kwargs["codes"]) == {"600522.SH", "159516.SZ", "000300.SH"}
        result = {}
        for symbol, step in (("600522.SH", 1.0), ("159516.SZ", 0.5), ("000300.SH", 0.25)):
            result[symbol] = [
                {
                    "trade_date": f"2026-04-{1 + index:02d}" if index < 30 else f"2026-05-{index - 29:02d}",
                    "close": 100.0 + index * step,
                    "volume": 1000.0 + index * 10,
                }
                for index in range(61)
            ]
        return result

    candidates = [
        CandidateObservation("600522", "ZTT", "Telecom", "Cable"),
        CandidateObservation("159516", "Semiconductor ETF", "Semiconductor", "Equipment"),
    ]
    provider = AkshareProvider(market_fetcher=fetcher)

    provider._enrich_market_history(candidates)

    assert candidates[0].security_type == "stock"
    assert candidates[1].security_type == "etf"
    assert candidates[0].current_price == 160.0
    assert candidates[0].return_20d_pct is not None
    assert candidates[0].return_60d_pct == 60.0
    assert candidates[0].volume_ratio_20d is not None
    assert candidates[0].relative_to_market_pct is not None
    assert candidates[0].market_data_as_of is not None
    assert "market_data_registry_ohlcv" in candidates[0].source_fields


def test_symbol_normalization_and_security_type() -> None:
    assert normalize_ashare_symbol("600522") == "600522.SH"
    assert normalize_ashare_symbol("002261") == "002261.SZ"
    assert normalize_ashare_symbol("588060") == "588060.SH"
    assert security_type_for_symbol("588060") == "etf"
    assert security_type_for_symbol("600522") == "stock"


def test_latest_complete_weekday_skips_weekend_and_pre_close_session() -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    assert _latest_complete_weekday(datetime(2026, 8, 1, 16, 0, tzinfo=timezone)).isoformat() == "2026-07-31"
    assert _latest_complete_weekday(datetime(2026, 7, 31, 14, 0, tzinfo=timezone)).isoformat() == "2026-07-30"


def test_announcement_classifier_marks_severe_and_soft_risks():
    classify = AkshareProvider._classify_announcement
    assert classify("关于收到中国证监会立案告知书的公告") == "investigation"
    assert classify("关于公司股票被实施退市风险警示的公告") == "delisting"
    assert classify("持股5%以上股东减持计划预披露公告") == "shareholder_reduction"
    assert classify("日常经营合同公告") is None
