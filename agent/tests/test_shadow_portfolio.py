from __future__ import annotations

from src.investment_research.operations.shadow_portfolio import ShadowPortfolioTracker


def _report(day: str, price: float, *, action_level: str = "prepare", panic: bool = True):
    return {
        "_fingerprint": f"report-{day}",
        "report_date": day,
        "market": {"panic": panic},
        "assets": [
            {
                "symbol": "600522.SH",
                "name": "中天科技",
                "effective_trade_date": day,
                "latest_close": price,
                "action_level": action_level,
                "supporting_evidence": ["市场恐慌且估值进入研究区"],
                "counter_evidence": ["基本面证据仍需复核"],
                "data_quality": "provider_acquired_unverified",
            }
        ],
    }


def test_shadow_intent_fills_only_on_later_trade_date_and_is_idempotent(tmp_path):
    tracker = ShadowPortfolioTracker(tmp_path / "shadow.json")

    signaled = tracker.process(_report("2026-07-29", 20.0))
    assert len(signaled["pending_intents"]) == 1
    assert signaled["open_positions"] == []
    assert signaled["cash"] == 70_000

    repeated = tracker.process(_report("2026-07-29", 20.0))
    assert len(repeated["pending_intents"]) == 1
    assert repeated["open_positions"] == []

    filled = tracker.process(_report("2026-07-30", 21.0, action_level="research"))
    assert filled["pending_intents"] == []
    assert len(filled["open_positions"]) == 1
    assert filled["open_positions"][0]["entry_trade_date"] == "2026-07-30"
    assert filled["open_positions"][0]["entry_price"] == 21.0
    assert filled["open_positions"][0]["notional"] == 3_500
    assert filled["trading_executed"] is False


def test_shadow_does_not_create_intent_without_panic_or_research_gate(tmp_path):
    tracker = ShadowPortfolioTracker(tmp_path / "shadow.json")

    calm = tracker.process(_report("2026-07-29", 20.0, panic=False))
    assert calm["pending_intents"] == []

    watch = tracker.process(
        {
            **_report("2026-07-30", 20.0, action_level="watch"),
            "_fingerprint": "watch",
        }
    )
    assert watch["pending_intents"] == []


def test_shadow_closes_at_t20_and_preserves_real_trade_boundary(tmp_path):
    tracker = ShadowPortfolioTracker(tmp_path / "shadow.json", horizon=2)
    tracker.process(_report("2026-07-29", 20.0))
    tracker.process(_report("2026-07-30", 21.0, action_level="research"))
    tracker.process(_report("2026-07-31", 22.0, action_level="research"))
    closed = tracker.process(_report("2026-08-03", 23.0, action_level="research"))

    assert closed["open_positions"] == []
    assert len(closed["closed_positions"]) == 1
    assert closed["closed_positions"][0]["status"] == "closed_t20"
    assert closed["closed_positions"][0]["return_pct"] == 9.52
    assert closed["cash"] > 70_000
    assert closed["trading_executed"] is False
