"""R1: Validator robustness — TypeError, Shanghai boundary, CONFLICTING_VERSION."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.historical.models import InputRowStatus
from src.investment_research.historical.validator import HistoricalInputValidator

SHANGHAI = ZoneInfo("Asia/Shanghai")


class TestNaiveAvailabilityTime:
    def test_naive_availability_time_does_not_crash(self):
        """Naive (no tzinfo) availability_time with tz-aware now must not raise TypeError."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        row = {
            "data_date": "2025-07-21",
            "source": "test",
            "availability_time": "2025-07-21T15:00:00",
        }
        result = v.validate([row], import_time=now)
        assert result.rows[0].row_status == InputRowStatus.MALFORMED
        assert any("timezone" in e for e in result.rows[0].errors)

    def test_naive_availability_time_safe_with_future_data(self):
        """Naive availability_time must not crash even when data_date is future."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        row = {
            "data_date": "2099-01-01",
            "source": "test",
            "availability_time": "2099-01-01T15:00:00",
        }
        result = v.validate([row], import_time=now)
        assert result.rows[0].row_status == InputRowStatus.FUTURE_DATA
        assert any("timezone" in e for e in result.rows[0].errors)

    def test_naive_availability_time_safe_with_duplicate(self):
        """Naive availability_time must not crash on duplicate date path."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        row1 = {"data_date": "2025-07-21", "source": "a", "availability_time": now}
        row2 = {"data_date": "2025-07-21", "source": "b", "availability_time": "2025-07-21T15:00:00"}
        result = v.validate([row1, row2], import_time=now)
        assert result.rows[1].row_status == InputRowStatus.DUPLICATE


class TestShanghaiTimezoneBoundary:
    def test_utc_sunday_shanghai_monday_data_accepted(self):
        """At UTC 17:00 Sunday (=Shanghai 01:00 Monday), data_date=Monday must be accepted.

        Old logic (UTC date): data_date(Mon 7/27) > now.date()(Sun 7/26) → TRUE → FUTURE (WRONG)
        Correct logic (Shanghai date): data_date(Mon 7/27) > exchange_date(Mon 7/27) → FALSE → ACCEPTED
        """
        now = datetime(2026, 7, 26, 17, 0, 0, tzinfo=timezone.utc)
        shanghai_date = now.astimezone(SHANGHAI).date()
        assert shanghai_date == date(2026, 7, 27)
        assert now.date() == date(2026, 7, 26)

        v = HistoricalInputValidator()
        row = {
            "data_date": shanghai_date,
            "source": "test",
            "availability_time": now,
        }
        result = v.validate([row], import_time=now)

        assert result.rows[0].row_status != InputRowStatus.FUTURE_DATA, (
            f"data_date={shanghai_date} at UTC {now} (Shanghai {now.astimezone(SHANGHAI)}): "
            f"should not be rejected as future"
        )


class TestConflictingVersion:
    def test_conflicting_rows_not_accepted(self):
        """Mixed schema versions must NOT produce ACCEPTED rows."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        rows = [
            {"data_date": date(2025, 7, 21), "source": "a",
             "availability_time": now, "schema_version": "1.0.0"},
            {"data_date": date(2025, 7, 22), "source": "b",
             "availability_time": now, "schema_version": "2.0.0"},
        ]
        result = v.validate(rows, import_time=now)

        accepted = [r for r in result.rows if r.row_status == InputRowStatus.ACCEPTED]
        assert len(accepted) == 0, f"Expected 0 ACCEPTED rows with conflicting versions, got {len(accepted)}"

    def test_conflicting_rows_marked_conflicting_version(self):
        """Rows with non-majority schema version must be CONFLICTING_VERSION."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        rows = [
            {"data_date": date(2025, 7, 21), "source": "a",
             "availability_time": now, "schema_version": "1.0.0"},
            {"data_date": date(2025, 7, 22), "source": "b",
             "availability_time": now, "schema_version": "2.0.0"},
        ]
        result = v.validate(rows, import_time=now)

        cv = [r for r in result.rows if r.row_status == InputRowStatus.CONFLICTING_VERSION]
        assert len(cv) == 2, f"Expected 2 CONFLICTING_VERSION rows, got {len(cv)}"

    def test_single_version_no_conflict(self):
        """All rows with same schema_version: all ACCEPTED, none CONFLICTING_VERSION."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        rows = [
            {"data_date": date(2025, 7, 21), "source": "a",
             "availability_time": now, "schema_version": "1.0.0"},
            {"data_date": date(2025, 7, 22), "source": "b",
             "availability_time": now, "schema_version": "1.0.0"},
        ]
        result = v.validate(rows, import_time=now)

        cv = [r for r in result.rows if r.row_status == InputRowStatus.CONFLICTING_VERSION]
        assert len(cv) == 0
        assert all(r.row_status == InputRowStatus.ACCEPTED for r in result.rows)
