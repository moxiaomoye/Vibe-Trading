from __future__ import annotations

from src.value_hunter.models import CandidateObservation, IndexObservation, MarketObservation
from src.value_hunter.providers import DemoProvider
from src.value_hunter.scoring import score_candidate, score_market


def test_demo_market_is_high_stress_and_components_are_bounded():
    result = score_market(DemoProvider().load_market())
    assert result.level == "股灾"
    assert 85 <= result.score <= 100
    assert result.components == {"trend": 30.0, "drawdown": 22.0, "breadth": 25.0, "panic": 19.0}


def test_normal_market_does_not_false_alarm():
    market = MarketObservation(
        as_of="2024-01-01",
        indices=[IndexObservation("X", "正常指数", 100, 0.5, -2, False, False)],
        advancer_ratio=0.58,
        above_ma60_ratio=0.62,
        limit_down_count=2,
        turnover_zscore=0.1,
        source="fixture",
    )
    result = score_market(market)
    assert result.level == "正常"
    assert result.score < 20


def test_market_missing_breadth_is_not_labeled_normal():
    market = MarketObservation(
        as_of="2026-07-20",
        indices=[IndexObservation("X", "指数", 100, -0.5, -4, False, False)],
        advancer_ratio=None,
        above_ma60_ratio=None,
        limit_down_count=None,
        turnover_zscore=None,
        source="fixture",
    )
    result = score_market(market)
    assert result.level == "数据不足"
    assert "不可用于排除股灾" in result.reasons[-1]


def test_complete_value_dislocation_advances():
    candidate = DemoProvider().load_candidates()[0]
    result = score_candidate(candidate)
    assert result.bucket == "价值错杀"
    assert result.status == "A - 深入研究"
    assert result.score.total >= 80
    assert result.missing_fields == []


def test_severe_risk_flag_rejects_even_when_other_scores_are_strong():
    candidate = DemoProvider().load_candidates()[0]
    candidate.risk_flags = ["investigation"]
    result = score_candidate(candidate)
    assert result.status == "Reject"
    assert result.score.risk_cleanliness == 0


def test_missing_point_in_time_fields_never_advance():
    candidate = CandidateObservation(
        symbol="000001", name="缺数据", sector="软件", theme="AI",
        industry_market_cap_rank=1, important_index_member=True,
        pe_ttm=20, drawdown_252_pct=-40,
    )
    result = score_candidate(candidate)
    assert result.status == "C - 数据不足"
    assert "roe_5y_median_pct" in result.missing_fields


def test_sentiment_leader_is_not_mislabeled_as_value():
    result = score_candidate(DemoProvider().load_candidates()[2])
    assert result.bucket == "情绪龙头"
    assert result.status.startswith("C")
