from __future__ import annotations

from src.value_hunter.models import CandidateObservation, IndexObservation, MarketObservation
from src.value_hunter.providers import AkshareProvider


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


def test_announcement_classifier_marks_severe_and_soft_risks():
    classify = AkshareProvider._classify_announcement
    assert classify("关于收到中国证监会立案告知书的公告") == "investigation"
    assert classify("关于公司股票被实施退市风险警示的公告") == "delisting"
    assert classify("持股5%以上股东减持计划预披露公告") == "shareholder_reduction"
    assert classify("日常经营合同公告") is None
