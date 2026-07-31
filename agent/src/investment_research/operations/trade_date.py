"""Deterministic Shanghai trade-date resolution for manual shadow research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from .scheduling import TradingDaySchedule


class DateMode(StrEnum):
    AUTO = "auto"
    SELECTED = "selected"


class DateResolution(StrEnum):
    CURRENT_COMPLETED_TRADING_DAY = "current_completed_trading_day"
    PREVIOUS_COMPLETED_TRADING_DAY = "previous_completed_trading_day"
    SELECTED_TRADING_DAY = "selected_trading_day"
    SELECTED_NON_TRADING_DAY_ADJUSTED = "selected_non_trading_day_adjusted"
    HISTORICAL_DATA_UNAVAILABLE = "historical_data_unavailable"
    DATA_NOT_READY = "data_not_ready"


@dataclass(frozen=True, slots=True)
class ResolvedTradeDate:
    requested_date: date | None
    effective_trade_date: date
    date_mode: DateMode
    date_resolution: DateResolution
    information_cutoff: datetime
    reason: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "requested_date": (
                self.requested_date.isoformat() if self.requested_date else None
            ),
            "effective_trade_date": self.effective_trade_date.isoformat(),
            "date_mode": self.date_mode.value,
            "date_resolution": self.date_resolution.value,
            "information_cutoff": self.information_cutoff.isoformat(),
            "date_resolution_reason": self.reason,
        }


class TradeDateResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TradeDateResolver:
    """Resolve a request to the latest completed exchange-local trade date.

    The calendar is injected through the existing ``TradingDaySchedule`` so
    tests and future exchange-calendar providers can supply explicit closures.
    """

    def __init__(
        self,
        schedule: TradingDaySchedule | None = None,
        *,
        max_lookback_days: int = 370,
    ) -> None:
        if max_lookback_days < 1:
            raise ValueError("max_lookback_days must be positive")
        self.schedule = schedule or TradingDaySchedule()
        self.max_lookback_days = max_lookback_days

    def resolve(
        self,
        *,
        now: datetime,
        date_mode: DateMode | str = DateMode.AUTO,
        requested_date: date | None = None,
    ) -> ResolvedTradeDate:
        local_now = self.schedule.local_now(now)
        mode = DateMode(date_mode)
        if mode is DateMode.AUTO:
            if requested_date is not None:
                raise TradeDateResolutionError(
                    "invalid_date_selection",
                    "requested_date must be null when date_mode is auto",
                )
            return self._resolve_auto(local_now)
        if requested_date is None:
            raise TradeDateResolutionError(
                "invalid_date_selection",
                "requested_date is required when date_mode is selected",
            )
        if requested_date > local_now.date():
            raise TradeDateResolutionError(
                "invalid_date_selection",
                "requested_date must not be in the future",
            )
        if (
            requested_date == local_now.date()
            and self.schedule.is_trading_day(requested_date)
            and local_now.time().replace(tzinfo=None) < self.schedule.run_after
        ):
            raise TradeDateResolutionError(
                DateResolution.DATA_NOT_READY.value,
                "the selected trading day has not reached the post-close data cutoff",
            )
        if self.schedule.is_trading_day(requested_date):
            return ResolvedTradeDate(
                requested_date,
                requested_date,
                mode,
                DateResolution.SELECTED_TRADING_DAY,
                self._completed_cutoff(requested_date),
                "the selected date is a completed trading day",
            )
        effective = self._previous_trading_day(requested_date)
        return ResolvedTradeDate(
            requested_date,
            effective,
            mode,
            DateResolution.SELECTED_NON_TRADING_DAY_ADJUSTED,
            self._completed_cutoff(effective),
            "the selected date is not a trading day; resolved to the latest prior trading day",
        )

    def _resolve_auto(self, local_now: datetime) -> ResolvedTradeDate:
        today = local_now.date()
        if (
            self.schedule.is_trading_day(today)
            and local_now.time().replace(tzinfo=None) >= self.schedule.run_after
        ):
            return ResolvedTradeDate(
                None,
                today,
                DateMode.AUTO,
                DateResolution.CURRENT_COMPLETED_TRADING_DAY,
                local_now,
                "today is a completed Shanghai trading day",
            )
        effective = self._previous_trading_day(today)
        reason = (
            "today is still in session; resolved to the latest completed trading day"
            if self.schedule.is_trading_day(today)
            else "today is not a trading day; resolved to the latest completed trading day"
        )
        return ResolvedTradeDate(
            None,
            effective,
            DateMode.AUTO,
            DateResolution.PREVIOUS_COMPLETED_TRADING_DAY,
            self._completed_cutoff(effective),
            reason,
        )

    def _previous_trading_day(self, start: date) -> date:
        candidate = start
        for _ in range(self.max_lookback_days):
            candidate = candidate.fromordinal(candidate.toordinal() - 1)
            if self.schedule.is_trading_day(candidate):
                return candidate
        raise TradeDateResolutionError(
            DateResolution.DATA_NOT_READY.value,
            "no completed trading day is available within the configured lookback",
        )

    def _completed_cutoff(self, day: date) -> datetime:
        local = datetime.combine(
            day,
            self.schedule.run_after,
            tzinfo=ZoneInfo(self.schedule.timezone_name),
        )
        return local


__all__ = [
    "DateMode",
    "DateResolution",
    "ResolvedTradeDate",
    "TradeDateResolutionError",
    "TradeDateResolver",
]
