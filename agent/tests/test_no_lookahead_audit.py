"""V3: No-lookahead audit of M1.3 historical evaluation code."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.investment_research.historical.models import InputRowStatus
from src.investment_research.historical.validator import HistoricalInputValidator
from src.investment_research.operations.manual_import import parse_manual_import_dict
from src.investment_research.operations.report_storage import ReportStorage


SHANGHAI = ZoneInfo("Asia/Shanghai")


class TestValidatorNoLookahead:
    def test_shanghai_timezone_boundary_uses_shanghai_date(self):
        """Validator must use Shanghai date, not UTC date, for future-data check.

        At UTC 15:00 on a Monday (Shanghai 23:00 Monday), a data_date of
        Monday should NOT be rejected as future — the trading day is over.
        """
        now = datetime(2026, 7, 27, 15, 0, 0, tzinfo=timezone.utc)
        shanghai_date = now.astimezone(SHANGHAI).date()  # Monday 2026-07-27

        v = HistoricalInputValidator()
        row = {
            "data_date": shanghai_date,
            "source": "test",
            "availability_time": now,
        }
        result = v.validate([row], import_time=now)

        assert result.rows[0].row_status != InputRowStatus.FUTURE_DATA, (
            f"data_date={shanghai_date} should not be future at {now} "
            f"(Shanghai {now.astimezone(SHANGHAI)})"
        )

    def test_utc_midnight_shanghai_tomorrow_not_rejected(self):
        """At UTC 17:00 Sunday (Shanghai 01:00 Monday), Sunday data should pass.

        If validator uses UTC date (Sunday), it would compare data_date=Sunday
        against now.date()=Sunday, correctly passing. This test validates
        the boundary works.
        """
        now = datetime(2026, 7, 26, 17, 0, 0, tzinfo=timezone.utc)
        shanghai_now = now.astimezone(SHANGHAI)
        assert shanghai_now.date() == date(2026, 7, 27)  # Monday

        v = HistoricalInputValidator()
        row = {
            "data_date": date(2026, 7, 26),  # Sunday data
            "source": "test",
            "availability_time": now,
        }
        result = v.validate([row], import_time=now)

        assert result.rows[0].row_status == InputRowStatus.ACCEPTED

    def test_conflicting_versions_reported(self):
        """conflicting_versions=1 when schema versions differ across rows."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        rows = [
            {"data_date": date(2025, 7, 21), "source": "a",
             "availability_time": now, "schema_version": "1.0.0"},
            {"data_date": date(2025, 7, 22), "source": "b",
             "availability_time": now, "schema_version": "2.0.0"},
        ]
        result = v.validate(rows, import_time=now)
        report = v.report(result)

        assert report.conflicting_versions == 1
        assert any("conflicting schema" in e for e in result.import_errors)

    def test_single_version_no_conflict(self):
        """conflicting_versions=0 when all rows use the same schema version."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        rows = [
            {"data_date": date(2025, 7, 21), "source": "a",
             "availability_time": now, "schema_version": "1.0.0"},
            {"data_date": date(2025, 7, 22), "source": "b",
             "availability_time": now, "schema_version": "1.0.0"},
        ]
        result = v.validate(rows, import_time=now)
        report = v.report(result)

        assert report.conflicting_versions == 0

    def test_cross_import_duplicate_allowed(self):
        """Validator is stateless — same data_date can be imported across calls."""
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        row = {"data_date": date(2025, 7, 21), "source": "test",
               "availability_time": now}

        r1 = v.validate([row], import_time=now)
        r2 = v.validate([row], import_time=now)

        assert r1.rows[0].row_status == InputRowStatus.ACCEPTED
        assert r2.rows[0].row_status == InputRowStatus.ACCEPTED


class TestManualImportNoLookahead:
    def test_cutoff_enforced_before_market_close(self, monkeypatch):
        """Manual import for today before 18:30 Shanghai must be rejected."""
        cutoff = time(18, 30)
        before_cutoff = datetime(2026, 7, 27, 10, 0, 0, tzinfo=SHANGHAI)
        assert before_cutoff.time().replace(tzinfo=None) < cutoff

        now_utc = before_cutoff.astimezone(timezone.utc)
        shanghai_today = before_cutoff.date()

        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": shanghai_today.isoformat(),
            "availability_time": now_utc.isoformat(),
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5,
                 "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result = parse_manual_import_dict(data, now=now_utc)

        assert any("cutoff" in e.lower() or "close" in e.lower() or "not yet" in e.lower()
                    for e in result.errors), (
            f"Expected cutoff enforcement error, got: {result.errors}"
        )

    def test_cutoff_allowed_if_date_not_today(self):
        """Manual import for a past date is always allowed regardless of time."""
        now = datetime(2026, 7, 27, 10, 0, 0, tzinfo=SHANGHAI).astimezone(timezone.utc)

        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00+08:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5,
                 "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result = parse_manual_import_dict(data, now=now)

        assert result.accepted_count == 1
        assert not result.errors

    def test_future_clock_skew_boundary(self):
        """availability_time exactly 5 min in future is tolerated, 6 min is not."""
        now = datetime(2026, 7, 27, 10, 0, 0, tzinfo=timezone.utc)

        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": (now + timedelta(minutes=5)).isoformat(),
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5,
                 "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result_5min = parse_manual_import_dict(data, now=now)
        assert not any("future" in e for e in result_5min.errors), (
            f"5-min skew should be tolerated: {result_5min.errors}"
        )

        data["availability_time"] = (now + timedelta(minutes=6)).isoformat()
        result_6min = parse_manual_import_dict(data, now=now)
        assert any("future" in e for e in result_6min.errors), (
            "6-min skew should be rejected"
        )


class TestReportStorageNoLookahead:
    def test_recalculation_produces_new_fingerprint(self, tmp_path: Path):
        """Different outcome data for same evaluation_date yields different fingerprint.

        The old report must remain on disk after recalculation.
        """
        storage = ReportStorage(output_dir=tmp_path / "reports")
        eval_date = date(2026, 7, 24)

        report_a = {
            "shadow_run": True,
            "market": {"trade_date": eval_date.isoformat()},
            "outcomes": {"accuracy": 0.85},
        }
        storage.save_report(report_a, date_dir=eval_date)
        fp_a = report_a["_fingerprint"]

        report_b = {
            "shadow_run": True,
            "market": {"trade_date": eval_date.isoformat()},
            "outcomes": {"accuracy": 0.92},
        }
        storage.save_report(report_b, date_dir=eval_date)
        fp_b = report_b["_fingerprint"]

        assert fp_a != fp_b, "Different outcomes must produce different fingerprints"

        fp_a_path = tmp_path / "reports" / eval_date.isoformat() / f"{fp_a}.json"
        fp_b_path = tmp_path / "reports" / eval_date.isoformat() / f"{fp_b}.json"
        assert fp_a_path.exists(), "Old report must be preserved on disk"
        assert fp_b_path.exists(), "New report must exist"

    def test_latest_points_to_newest_report(self, tmp_path: Path):
        """load_latest_for_date returns the most recent report by _stored_at."""
        storage = ReportStorage(output_dir=tmp_path / "reports")
        eval_date = date(2026, 7, 24)

        report_old = {
            "shadow_run": True,
            "market": {"trade_date": eval_date.isoformat()},
            "version": 1,
        }
        storage.save_report(report_old, date_dir=eval_date)

        import time as time_module
        time_module.sleep(0.01)

        report_new = {
            "shadow_run": True,
            "market": {"trade_date": eval_date.isoformat()},
            "version": 2,
        }
        storage.save_report(report_new, date_dir=eval_date)

        latest = storage.load_latest_for_date(eval_date)
        assert latest is not None
        assert latest["version"] == 2
        assert latest["_fingerprint"] != report_old["_fingerprint"]
