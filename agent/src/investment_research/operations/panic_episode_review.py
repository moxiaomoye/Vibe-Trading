from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..models.historical_market_panel import HistoricalMarketPanel
from ..operations.trading_calendar import TradingCalendar
from .evaluation_metrics import EvaluationMetrics, MetricsCalculator
from .outcome_loader import OutcomeLoader
from .review_labeling import ReviewLabel, label_counts, label_outcome


@dataclass(frozen=True, slots=True)
class EpisodeDateEntry:
    trade_date: date
    market_change_pct: float
    metrics: EvaluationMetrics
    labels: dict[int, ReviewLabel]


@dataclass(frozen=True, slots=True)
class EpisodeSummary:
    episode_start: date
    episode_end: date
    total_dates: int
    available_dates: int
    dates: tuple[EpisodeDateEntry, ...] = ()
    aggregate_hit_rate: float | None = None
    aggregate_avg_excess_return: float | None = None
    aggregate_avg_max_drawdown: float | None = None
    label_distribution: dict[str, int] = field(default_factory=dict)


class PanicEpisodeReviewWorkflow:
    def __init__(
        self,
        outcome_loader: OutcomeLoader,
        calendar: TradingCalendar | None = None,
    ) -> None:
        self.outcome_loader = outcome_loader
        self.calendar = calendar or TradingCalendar()

    def review_episode(
        self,
        episode_dates: tuple[date, ...],
    ) -> EpisodeSummary:
        entries: list[EpisodeDateEntry] = []
        total_labels: dict[ReviewLabel, int] = {}
        total_excess: list[float] = []
        total_drawdowns: list[float] = []
        hit_total = 0
        total_scored = 0

        for d in episode_dates:
            outcome = self.outcome_loader.load(d)

            panel = HistoricalMarketPanel(
                date=d, market_price=0.0, market_change_pct=0.0,
                ma_5=0.0, ma_10=0.0, ma_20=0.0,
                volume=0, turnover=0.0, amplitude=0.0,
            )
            cal = MetricsCalculator()
            metrics = cal.evaluate(panel, outcome)
            labels = label_outcome(outcome)
            counts = label_counts(labels)

            for label, count in counts.items():
                total_labels[label] = total_labels.get(label, 0) + count

            for h in metrics.horizons:
                if h.hit is not None:
                    total_scored += 1
                    if h.hit:
                        hit_total += 1
                if h.excess_return is not None:
                    total_excess.append(h.excess_return)
                if h.maximum_drawdown is not None:
                    total_drawdowns.append(h.maximum_drawdown)

            entries.append(
                EpisodeDateEntry(
                    trade_date=d,
                    market_change_pct=0.0,
                    metrics=metrics,
                    labels=labels,
                )
            )

        start = episode_dates[0] if episode_dates else date.today()
        end = episode_dates[-1] if episode_dates else date.today()
        aggregate_hit = hit_total / total_scored if total_scored > 0 else None
        avg_excess = sum(total_excess) / len(total_excess) if total_excess else None
        avg_dd = (
            sum(total_drawdowns) / len(total_drawdowns)
            if total_drawdowns
            else None
        )

        return EpisodeSummary(
            episode_start=start,
            episode_end=end,
            total_dates=len(episode_dates),
            available_dates=sum(
                1 for e in entries
                if any(h.hit is not None for h in e.metrics.horizons)
            ),
            dates=tuple(entries),
            aggregate_hit_rate=aggregate_hit,
            aggregate_avg_excess_return=avg_excess,
            aggregate_avg_max_drawdown=avg_dd,
            label_distribution={
                k.value: v for k, v in sorted(total_labels.items())
            },
        )
