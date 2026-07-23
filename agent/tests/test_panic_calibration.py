"""Calibration tests use fixtures only: no network, persistence, or notifications."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.value_hunter.calibration import (
    ManualReviewLabel,
    ManualReviewRecord,
    ThresholdVersion,
    run_panic_calibration,
)
from src.value_hunter.panic_classifier import PanicLevel, PanicThresholds


SYMBOL = "600522.SH"


def _watchlist(tmp_path):
    path = tmp_path / "watchlist.yaml"
    path.write_text(
        'version: "test-1"\nwatchlist:\n  name: "fixture"\n  symbols:\n    - "600522.SH"\n',
        encoding="utf-8",
    )
    return path


def _panel(trade_date: date, decline_ratio: float = 0.6, close: float = 100.0):
    total = 10
    decline = round(total * decline_ratio)
    codes = ["600522"] + [f"00000{i}" for i in range(1, total)]
    changes = [-5.0] * decline + [2.0] * (total - decline)
    return {
        "spot_df": pd.DataFrame(
            {
                "代码": codes,
                "名称": ["fixture"] * total,
                "最新价": [close] + [10.0] * (total - 1),
                "涨跌幅": changes,
                "昨收": [close / 0.95] + [10.0] * (total - 1),
            }
        ),
        "limit_up_symbols": [],
        "limit_down_symbols": [],
        "data_date": trade_date,
        "now": datetime.combine(trade_date, datetime.min.time(), timezone.utc),
        "market_change_pct": -0.03,
        "sector_map": {SYMBOL: -0.04},
    }


def _outcome_prices(start: date, count: int = 60, start_price: float = 100.0):
    """Daily future-price map for calibration outcome windows."""
    return {
        start + timedelta(days=offset): {SYMBOL: start_price + offset}
        for offset in range(1, count + 1)
    }


def _versions():
    return [
        ThresholdVersion(
            "loose-v1",
            PanicThresholds(
                caution_decline_ratio=0.5,
                panic_decline_ratio=0.8,
                extreme_decline_ratio=0.95,
            ),
        ),
        ThresholdVersion(
            "strict-v2",
            PanicThresholds(
                caution_decline_ratio=0.9,
                panic_decline_ratio=0.95,
                extreme_decline_ratio=0.99,
            ),
        ),
    ]


def test_multiple_versions_are_preserved_and_compared(tmp_path):
    d = date(2026, 1, 5)
    result = run_panic_calibration(
        generation_panels={d: _panel(d)},
        outcome_prices=_outcome_prices(d),
        threshold_versions=_versions(),
        watchlist_path=_watchlist(tmp_path),
    )
    assert tuple(result.versions) == ("loose-v1", "strict-v2")
    assert result.versions["loose-v1"].replay.entries[0].result.panic.level == PanicLevel.CAUTION
    assert result.versions["strict-v2"].replay.entries[0].result.panic.level == PanicLevel.NORMAL
    assert len(result.differences) == 1
    assert result.differences[0].trade_date == d


def test_returns_use_exact_future_trading_windows(tmp_path):
    d = date(2026, 1, 5)
    result = run_panic_calibration(
        generation_panels={d: _panel(d)},
        outcome_prices=_outcome_prices(d),
        threshold_versions=[_versions()[0]],
        watchlist_path=_watchlist(tmp_path),
    )
    outcome = result.versions["loose-v1"].outcomes[0]
    by_horizon = {window.horizon: window for window in outcome.windows}
    assert by_horizon[5].target_date == d + timedelta(days=5)
    assert by_horizon[5].return_pct == pytest.approx(0.05)
    assert by_horizon[20].return_pct == pytest.approx(0.20)
    assert by_horizon[60].return_pct == pytest.approx(0.60)


def test_future_outcomes_cannot_change_candidate_generation(tmp_path):
    d = date(2026, 1, 5)
    args = {
        "generation_panels": {d: _panel(d)},
        "threshold_versions": [_versions()[0]],
        "watchlist_path": _watchlist(tmp_path),
    }
    rising = run_panic_calibration(outcome_prices=_outcome_prices(d, start_price=100.0), **args)
    falling_prices = {
        day: {SYMBOL: 50.0 - index}
        for index, day in enumerate(_outcome_prices(d), start=1)
    }
    falling = run_panic_calibration(outcome_prices=falling_prices, **args)

    rising_replay = rising.versions["loose-v1"].replay
    falling_replay = falling.versions["loose-v1"].replay
    assert rising_replay == falling_replay
    assert rising.versions["loose-v1"].outcomes != falling.versions["loose-v1"].outcomes


def test_unavailable_window_returns_none_and_data_gap(tmp_path):
    d = date(2026, 1, 5)
    result = run_panic_calibration(
        generation_panels={d: _panel(d)},
        outcome_prices=_outcome_prices(d, count=5),
        threshold_versions=[_versions()[0]],
        watchlist_path=_watchlist(tmp_path),
    )
    windows = {window.horizon: window for window in result.versions["loose-v1"].outcomes[0].windows}
    assert windows[5].return_pct == pytest.approx(0.05)
    assert windows[20].return_pct is None
    assert windows[20].data_gap is not None
    assert windows[60].return_pct is None
    assert windows[60].data_gap is not None


def test_summary_contains_frequency_distribution_and_coverage(tmp_path):
    d = date(2026, 1, 5)
    result = run_panic_calibration(
        generation_panels={d: _panel(d)},
        outcome_prices=_outcome_prices(d, count=20),
        threshold_versions=[_versions()[0]],
        watchlist_path=_watchlist(tmp_path),
    )
    summary = result.versions["loose-v1"].summary
    assert summary.panic_level_frequency["caution"] == 1
    assert summary.candidate_count == 1
    assert summary.return_distributions[5].available_count == 1
    assert summary.return_distributions[60].missing_count == 1
    assert summary.data_coverage == {5: 1.0, 20: 1.0, 60: 0.0}


def test_normal_day_has_no_calibration_candidates(tmp_path):
    d = date(2026, 1, 5)
    result = run_panic_calibration(
        generation_panels={d: _panel(d, decline_ratio=0.2)},
        outcome_prices=_outcome_prices(d),
        threshold_versions=[_versions()[0]],
        watchlist_path=_watchlist(tmp_path),
    )
    evaluation = result.versions["loose-v1"]
    assert evaluation.summary.panic_level_frequency["normal"] == 1
    assert evaluation.summary.candidate_count == 0
    assert evaluation.outcomes == ()


def test_repeated_execution_is_deterministic(tmp_path):
    d = date(2026, 1, 5)
    kwargs = {
        "generation_panels": {d: _panel(d)},
        "outcome_prices": _outcome_prices(d),
        "threshold_versions": _versions(),
        "watchlist_path": _watchlist(tmp_path),
    }
    assert run_panic_calibration(**kwargs) == run_panic_calibration(**kwargs)


def test_manual_review_labels_are_structured():
    record = ManualReviewRecord(
        threshold_version="loose-v1",
        trade_date=date(2026, 1, 5),
        symbol=SYMBOL,
        label=ManualReviewLabel.FALSE_POSITIVE,
        rationale="panic classification did not lead to durable mispricing",
        reviewer="fixture-reviewer",
    )
    assert record.label.value == "false_positive"


@pytest.mark.parametrize("horizons", [(), (0,), (5, 5)])
def test_invalid_horizons_rejected(tmp_path, horizons):
    d = date(2026, 1, 5)
    with pytest.raises(ValueError):
        run_panic_calibration(
            generation_panels={d: _panel(d)},
            outcome_prices=_outcome_prices(d),
            threshold_versions=[_versions()[0]],
            watchlist_path=_watchlist(tmp_path),
            horizons=horizons,
        )


def test_duplicate_threshold_versions_rejected(tmp_path):
    d = date(2026, 1, 5)
    with pytest.raises(ValueError, match="unique"):
        run_panic_calibration(
            generation_panels={d: _panel(d)},
            outcome_prices=_outcome_prices(d),
            threshold_versions=[_versions()[0], _versions()[0]],
            watchlist_path=_watchlist(tmp_path),
        )
