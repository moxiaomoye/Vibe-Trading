"""Deterministic historical calibration and ex-post outcome evaluation.

Candidate generation and outcome labeling are deliberately separate phases:
``generation_panels`` are passed to history replay, while ``outcome_prices``
are only read after replay results have been frozen in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from statistics import mean, median
from typing import Any, Collection, Mapping, Sequence

from src.value_hunter.history_replay import HistoryReplayResult, run_history_replay
from src.value_hunter.market_snapshot import DataGap
from src.value_hunter.panic_classifier import PanicLevel, PanicThresholds


DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_CANDIDATE_LEVELS = frozenset(
    {PanicLevel.CAUTION, PanicLevel.PANIC, PanicLevel.EXTREME_PANIC}
)


class ManualReviewLabel(Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    TRUE_NEGATIVE = "true_negative"
    FALSE_NEGATIVE = "false_negative"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class ManualReviewRecord:
    threshold_version: str
    trade_date: date
    symbol: str
    label: ManualReviewLabel
    rationale: str
    reviewer: str | None = None


@dataclass(frozen=True)
class ThresholdVersion:
    version: str
    thresholds: PanicThresholds

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("threshold version must not be empty")


@dataclass(frozen=True)
class OutcomeWindow:
    horizon: int
    target_date: date | None
    return_pct: float | None
    data_gap: DataGap | None = None


@dataclass(frozen=True)
class CandidateOutcome:
    threshold_version: str
    trade_date: date
    symbol: str
    entry_close: float
    windows: tuple[OutcomeWindow, ...]


@dataclass(frozen=True)
class DistributionSummary:
    available_count: int
    missing_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None


@dataclass(frozen=True)
class CalibrationSummary:
    panic_level_frequency: Mapping[str, int]
    candidate_count: int
    return_distributions: Mapping[int, DistributionSummary]
    data_coverage: Mapping[int, float]


@dataclass(frozen=True)
class RuleVersionDifference:
    trade_date: date
    baseline_version: str
    comparison_version: str
    baseline_level: PanicLevel
    comparison_level: PanicLevel


@dataclass(frozen=True)
class VersionEvaluation:
    threshold_version: str
    replay: HistoryReplayResult
    outcomes: tuple[CandidateOutcome, ...]
    summary: CalibrationSummary


@dataclass(frozen=True)
class CalibrationResult:
    versions: Mapping[str, VersionEvaluation]
    differences: tuple[RuleVersionDifference, ...] = field(default_factory=tuple)
    horizons: tuple[int, ...] = DEFAULT_HORIZONS


def run_panic_calibration(
    *,
    generation_panels: Mapping[date, dict[str, Any]],
    outcome_prices: Mapping[date, Mapping[str, float]],
    threshold_versions: Sequence[ThresholdVersion],
    watchlist_path: Path | None = None,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    candidate_levels: Collection[PanicLevel] = DEFAULT_CANDIDATE_LEVELS,
) -> CalibrationResult:
    """Compare threshold versions and attach strictly ex-post return labels.

    ``outcome_prices`` is never passed to ``run_history_replay``. A horizon is
    measured on the sorted union of supplied trading dates. Missing target-day
    prices remain explicit gaps rather than being forward-filled.
    """
    versions = tuple(threshold_versions)
    if not versions:
        raise ValueError("at least one threshold version is required")
    version_names = [item.version for item in versions]
    if len(version_names) != len(set(version_names)):
        raise ValueError("threshold versions must be unique")

    normalized_horizons = tuple(int(value) for value in horizons)
    if not normalized_horizons or any(value <= 0 for value in normalized_horizons):
        raise ValueError("horizons must contain positive trading-day counts")
    if len(normalized_horizons) != len(set(normalized_horizons)):
        raise ValueError("horizons must be unique")

    trading_dates = tuple(sorted(set(generation_panels) | set(outcome_prices)))
    date_positions = {trade_date: index for index, trade_date in enumerate(trading_dates)}
    eligible_levels = frozenset(candidate_levels)
    evaluations: dict[str, VersionEvaluation] = {}

    for threshold_version in versions:
        replay = run_history_replay(
            daily_panels=dict(generation_panels),
            watchlist_path=watchlist_path,
            thresholds=threshold_version.thresholds,
        )
        outcomes = _evaluate_outcomes(
            replay=replay,
            threshold_version=threshold_version.version,
            outcome_prices=outcome_prices,
            trading_dates=trading_dates,
            date_positions=date_positions,
            horizons=normalized_horizons,
            candidate_levels=eligible_levels,
        )
        evaluations[threshold_version.version] = VersionEvaluation(
            threshold_version=threshold_version.version,
            replay=replay,
            outcomes=outcomes,
            summary=_summarize(replay, outcomes, normalized_horizons),
        )

    return CalibrationResult(
        versions=evaluations,
        differences=_compare_versions(evaluations, version_names),
        horizons=normalized_horizons,
    )


def _evaluate_outcomes(
    *,
    replay: HistoryReplayResult,
    threshold_version: str,
    outcome_prices: Mapping[date, Mapping[str, float]],
    trading_dates: tuple[date, ...],
    date_positions: Mapping[date, int],
    horizons: tuple[int, ...],
    candidate_levels: frozenset[PanicLevel],
) -> tuple[CandidateOutcome, ...]:
    outcomes: list[CandidateOutcome] = []
    for entry in replay.entries:
        if entry.result is None or entry.result.panic.level not in candidate_levels:
            continue
        for candidate in entry.result.watchlist:
            if candidate.close is None or candidate.close <= 0:
                continue
            windows = tuple(
                _evaluate_window(
                    trade_date=entry.trade_date,
                    symbol=candidate.symbol,
                    entry_close=candidate.close,
                    horizon=horizon,
                    outcome_prices=outcome_prices,
                    trading_dates=trading_dates,
                    date_positions=date_positions,
                )
                for horizon in horizons
            )
            outcomes.append(
                CandidateOutcome(
                    threshold_version=threshold_version,
                    trade_date=entry.trade_date,
                    symbol=candidate.symbol,
                    entry_close=candidate.close,
                    windows=windows,
                )
            )
    return tuple(outcomes)


def _evaluate_window(
    *,
    trade_date: date,
    symbol: str,
    entry_close: float,
    horizon: int,
    outcome_prices: Mapping[date, Mapping[str, float]],
    trading_dates: tuple[date, ...],
    date_positions: Mapping[date, int],
) -> OutcomeWindow:
    start_position = date_positions.get(trade_date)
    target_position = None if start_position is None else start_position + horizon
    if target_position is None or target_position >= len(trading_dates):
        return OutcomeWindow(
            horizon=horizon,
            target_date=None,
            return_pct=None,
            data_gap=DataGap(description=f"缺少 {horizon} 个交易日后的结果窗口"),
        )

    target_date = trading_dates[target_position]
    daily_prices = outcome_prices.get(target_date, {})
    target_close = _symbol_value(daily_prices, symbol)
    if target_close is None or target_close <= 0:
        return OutcomeWindow(
            horizon=horizon,
            target_date=target_date,
            return_pct=None,
            data_gap=DataGap(
                last_trade_date=target_date,
                description=f"{target_date} 缺少 {symbol} 收盘价",
            ),
        )

    return OutcomeWindow(
        horizon=horizon,
        target_date=target_date,
        return_pct=round(float(target_close) / entry_close - 1.0, 8),
    )


def _symbol_value(values: Mapping[str, float], symbol: str) -> float | None:
    value = values.get(symbol)
    if value is None:
        value = values.get(symbol.split(".")[0])
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _summarize(
    replay: HistoryReplayResult,
    outcomes: tuple[CandidateOutcome, ...],
    horizons: tuple[int, ...],
) -> CalibrationSummary:
    frequencies = {level.value: 0 for level in PanicLevel}
    for entry in replay.entries:
        if entry.result is not None:
            frequencies[entry.result.panic.level.value] += 1

    distributions: dict[int, DistributionSummary] = {}
    coverage: dict[int, float] = {}
    for horizon in horizons:
        windows = [
            window
            for outcome in outcomes
            for window in outcome.windows
            if window.horizon == horizon
        ]
        values = [window.return_pct for window in windows if window.return_pct is not None]
        missing = len(windows) - len(values)
        distributions[horizon] = DistributionSummary(
            available_count=len(values),
            missing_count=missing,
            minimum=min(values) if values else None,
            maximum=max(values) if values else None,
            mean=round(mean(values), 8) if values else None,
            median=round(median(values), 8) if values else None,
        )
        coverage[horizon] = round(len(values) / len(windows), 4) if windows else 0.0

    return CalibrationSummary(
        panic_level_frequency=frequencies,
        candidate_count=len(outcomes),
        return_distributions=distributions,
        data_coverage=coverage,
    )


def _compare_versions(
    evaluations: Mapping[str, VersionEvaluation],
    version_names: Sequence[str],
) -> tuple[RuleVersionDifference, ...]:
    baseline_name = version_names[0]
    baseline_levels = _levels_by_date(evaluations[baseline_name].replay)
    differences: list[RuleVersionDifference] = []
    for comparison_name in version_names[1:]:
        comparison_levels = _levels_by_date(evaluations[comparison_name].replay)
        for trade_date in sorted(set(baseline_levels) & set(comparison_levels)):
            baseline_level = baseline_levels[trade_date]
            comparison_level = comparison_levels[trade_date]
            if baseline_level != comparison_level:
                differences.append(
                    RuleVersionDifference(
                        trade_date=trade_date,
                        baseline_version=baseline_name,
                        comparison_version=comparison_name,
                        baseline_level=baseline_level,
                        comparison_level=comparison_level,
                    )
                )
    return tuple(differences)


def _levels_by_date(replay: HistoryReplayResult) -> dict[date, PanicLevel]:
    return {
        entry.trade_date: entry.result.panic.level
        for entry in replay.entries
        if entry.result is not None
    }
