"""B6 — Bounded Historical Evaluation Input Format tests."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pytest

from src.investment_research.historical.models import InputRowStatus
from src.investment_research.historical.validator import HistoricalInputValidator
from src.investment_research.historical.fixture_data import (
    two_day_sample,
    mixed_quality_sample,
    sample_market_day,
)


class TestValidator:
    def test_accepts_valid_rows(self):
        v = HistoricalInputValidator()
        result = v.validate(two_day_sample())
        assert len(result.rows) == 2
        assert all(r.row_status == InputRowStatus.ACCEPTED for r in result.rows)

    def test_rejects_future_data(self):
        v = HistoricalInputValidator()
        rows = mixed_quality_sample()
        result = v.validate(rows)
        future = [r for r in result.rows if r.row_status == InputRowStatus.FUTURE_DATA]
        assert len(future) >= 1

    def test_rejects_malformed(self):
        v = HistoricalInputValidator()
        rows = mixed_quality_sample()
        result = v.validate(rows)
        malformed = [r for r in result.rows if r.row_status == InputRowStatus.MALFORMED]
        assert len(malformed) >= 1

    def test_rejects_duplicate_dates(self):
        v = HistoricalInputValidator()
        rows = two_day_sample() + two_day_sample()[:1]  # duplicate first day
        result = v.validate(rows)
        dups = [r for r in result.rows if r.row_status == InputRowStatus.DUPLICATE]
        assert len(dups) >= 1

    def test_stable_ordering(self):
        v = HistoricalInputValidator()
        rows = two_day_sample()
        r1 = v.validate(rows)
        r2 = v.validate(rows)
        assert len(r1.rows) == len(r2.rows)
        for a, b in zip(r1.rows, r2.rows):
            assert a.row_status == b.row_status

    def test_deterministic_replay(self):
        v = HistoricalInputValidator()
        rows = two_day_sample()
        r = v.validate(rows)
        report = v.report(r)
        assert report.accepted == len(rows)
        assert report.future_data_rejected == 0

    def test_future_timestamp(self):
        v = HistoricalInputValidator()
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=365)
        row = {
            "data_date": date.today(),
            "source": "test",
            "availability_time": future,
        }
        result = v.validate([row])
        assert result.rows[0].row_status == InputRowStatus.FUTURE_DATA

    def test_report_counts(self):
        v = HistoricalInputValidator()
        rows = mixed_quality_sample()
        result = v.validate(rows)
        report = v.report(result)
        assert report.total_rows == len(rows)
        assert report.accepted + report.future_data_rejected + report.malformed == report.total_rows
