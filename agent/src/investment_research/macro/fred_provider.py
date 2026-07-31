"""FRED adapter that reuses Vibe-Trading's existing macro tool."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from src.config.accessor import get_env_config
from src.tools.fred_macro_tool import FredMacroTool

from .models import MacroEvidenceBatch, MacroObservationEvidence, MacroProviderStatus


_SERIES_URL = "https://fred.stlouisfed.org/series/{series_id}"


@dataclass(frozen=True, slots=True)
class FredSeriesDefinition:
    series_id: str
    title: str
    subject_id: str
    units: str | None = None
    frequency: str | None = None


DEFAULT_FRED_SERIES = (
    FredSeriesDefinition("DGS2", "US 2-Year Treasury Yield", "global-liquidity", "percent", "daily"),
    FredSeriesDefinition("DGS10", "US 10-Year Treasury Yield", "global-liquidity", "percent", "daily"),
    FredSeriesDefinition("DTWEXBGS", "Trade Weighted US Dollar Index", "global-liquidity", "index", "daily"),
    FredSeriesDefinition("VIXCLS", "CBOE Volatility Index", "global-risk", "index", "daily"),
    FredSeriesDefinition("BAMLH0A0HYM2", "US High Yield Option-Adjusted Spread", "global-credit", "percent", "daily"),
    FredSeriesDefinition("DCOILWTICO", "WTI Crude Oil Price", "global-energy", "USD per barrel", "daily"),
)


class FredMacroEvidenceProvider:
    """Load current FRED observations as pending market evidence.

    The existing FRED tool returns current-revision data. Historical requests
    are rejected here until an ALFRED vintage-aware adapter is implemented.
    """

    provider_name = "fred"

    def __init__(
        self,
        *,
        series: tuple[FredSeriesDefinition, ...] = DEFAULT_FRED_SERIES,
        execute: Callable[..., str] | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.series = series
        self._execute = execute or FredMacroTool().execute
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))

    @property
    def configured(self) -> bool:
        return bool(get_env_config().data.fred_api_key.strip())

    def load(self, *, as_of: date) -> MacroEvidenceBatch:
        retrieved_at = self._now()
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("now() must return a timezone-aware datetime")
        if as_of != self._today():
            return MacroEvidenceBatch(
                self.provider_name,
                MacroProviderStatus.HISTORICAL_UNSUPPORTED,
                as_of,
                retrieved_at,
                data_gaps=(
                    "FRED current-revision observations are not allowed in historical replay; "
                    "ALFRED vintage dates are required",
                ),
            )
        if not self.configured:
            return MacroEvidenceBatch(
                self.provider_name,
                MacroProviderStatus.UNCONFIGURED,
                as_of,
                retrieved_at,
                data_gaps=("FRED_API_KEY is not configured",),
            )

        observations: list[MacroObservationEvidence] = []
        data_gaps: list[str] = []
        errors: list[str] = []
        start = as_of - timedelta(days=45)
        for definition in self.series:
            try:
                payload = json.loads(
                    self._execute(
                        series_id=definition.series_id,
                        start_date=start.isoformat(),
                        end_date=as_of.isoformat(),
                        limit=10,
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{definition.series_id}: {type(exc).__name__}")
                continue
            if not isinstance(payload, dict) or not payload.get("ok"):
                error = payload.get("error") if isinstance(payload, dict) else None
                errors.append(f"{definition.series_id}: {_error_kind(error)}")
                continue
            rows = ((payload.get("data") or {}).get("observations") or [])
            parsed = [_parse_row(row) for row in rows]
            valid = sorted(
                (row for row in parsed if row is not None and row[0] <= as_of),
                key=lambda row: row[0],
            )
            if not valid:
                data_gaps.append(f"{definition.series_id}: no dated numeric observation")
                continue
            latest = valid[-1]
            previous = valid[-2] if len(valid) > 1 else None
            observations.append(
                MacroObservationEvidence(
                    provider=self.provider_name,
                    series_id=definition.series_id,
                    title=definition.title,
                    observation_date=latest[0],
                    value=latest[1],
                    retrieved_at=retrieved_at,
                    source_url=_SERIES_URL.format(series_id=definition.series_id),
                    subject_id=definition.subject_id,
                    previous_observation_date=previous[0] if previous else None,
                    previous_value=previous[1] if previous else None,
                    realtime_start=latest[2],
                    realtime_end=latest[3],
                    units=definition.units,
                    frequency=definition.frequency,
                    quality_warnings=(
                        "observation_is_current_revision",
                    ),
                )
            )

        if observations and not errors and not data_gaps:
            status = MacroProviderStatus.CONFIGURED
        elif observations:
            status = MacroProviderStatus.PARTIAL
        else:
            status = MacroProviderStatus.UPSTREAM_UNAVAILABLE
        return MacroEvidenceBatch(
            self.provider_name,
            status,
            as_of,
            retrieved_at,
            tuple(observations),
            tuple(data_gaps),
            tuple(errors),
        )


def _parse_row(
    row: Any,
) -> tuple[date, Decimal, date | None, date | None] | None:
    if not isinstance(row, dict):
        return None
    try:
        observation_date = date.fromisoformat(str(row["date"])[:10])
        value = Decimal(str(row["value"]))
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return None
    realtime_start = _optional_date(row.get("realtime_start"))
    realtime_end = _optional_date(row.get("realtime_end"))
    return observation_date, value, realtime_start, realtime_end


def _optional_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _error_kind(value: Any) -> str:
    text = str(value or "").lower()
    if "api_key" in text or "permission" in text or "unauthorized" in text:
        return "authentication_or_permission"
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "timeout" in text:
        return "timeout"
    return "upstream_unavailable"
