"""Example fixture input sets for bounded historical evaluation."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def sample_market_day(date_str: str) -> dict[str, Any]:
    """Return a single day's panel_data fixture for history replay."""
    d = date.fromisoformat(date_str)
    return {
        "schema_version": "1.0.0",
        "data_date": d,
        "source": "fixture_history",
        "availability_time": datetime(d.year, d.month, d.day, 15, 30, tzinfo=timezone.utc),
        "market_change_pct": -0.015,
    }


def two_day_sample() -> list[dict[str, Any]]:
    return [
        sample_market_day("2025-07-21"),
        sample_market_day("2025-07-22"),
    ]


def mixed_quality_sample() -> list[dict[str, Any]]:
    return [
        sample_market_day("2025-07-21"),
        sample_market_day("2025-07-22"),
        # Future data — should be rejected
        {
            "schema_version": "1.0.0",
            "data_date": date(2030, 1, 1),
            "source": "fixture_history_future",
            "availability_time": datetime(2030, 1, 1, 15, 30, tzinfo=timezone.utc),
        },
        # Missing source
        {
            "schema_version": "1.0.0",
            "data_date": date(2025, 7, 23),
            "source": "",
            "availability_time": datetime(2025, 7, 23, 15, 30, tzinfo=timezone.utc),
        },
    ]
