"""Tests for RC5 atomic local report storage."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.investment_research.operations.report_storage import REPORT_SCHEMA_VERSION, ReportStorage


@pytest.fixture
def tmp_storage(tmp_path: Path) -> ReportStorage:
    return ReportStorage(output_dir=tmp_path / "reports")


class TestReportStorage:
    def test_save_and_load_latest(self, tmp_storage: ReportStorage) -> None:
        report = {"shadow_run": True, "manual_review_required": True, "market": {"trade_date": "2026-07-24"}}
        tmp_storage.save_report(report)
        loaded = tmp_storage.load_latest()
        assert loaded is not None
        assert loaded["shadow_run"] is True
        assert loaded["_schema_version"] == REPORT_SCHEMA_VERSION

    def test_latest_missing_returns_none(self, tmp_storage: ReportStorage) -> None:
        assert tmp_storage.load_latest() is None

    def test_corrupt_latest_returns_none(self, tmp_storage: ReportStorage) -> None:
        (tmp_storage.output_dir / "latest.json").write_text("not-json{", encoding="utf-8")
        assert tmp_storage.load_latest() is None

    def test_atomic_write_temp_cleaned(self, tmp_storage: ReportStorage) -> None:
        report = {"version": 1}
        tmp_storage.save_report(report)
        tmp_files = list(tmp_storage.output_dir.glob(".*.tmp"))
        assert len(tmp_files) == 0

    def test_fingerprint_is_deterministic(self, tmp_storage: ReportStorage) -> None:
        r1 = {"shadow_run": True, "candidates": []}
        r2 = {"shadow_run": True, "candidates": []}
        tmp_storage.save_report(r1, date_dir=date(2026, 7, 24))
        tmp_storage.save_report(r2, date_dir=date(2026, 7, 24))
        f1 = r1["_fingerprint"]
        f2 = r2["_fingerprint"]
        assert f1 == f2

    def test_report_by_fingerprint(self, tmp_storage: ReportStorage) -> None:
        report = {"shadow_run": True, "data": "test"}
        tmp_storage.save_report(report, date_dir=date(2026, 7, 24))
        fp = report["_fingerprint"]
        loaded = tmp_storage.load_report(fp, date_str="2026-07-24")
        assert loaded is not None
        assert loaded["shadow_run"] is True

    def test_report_directory_created(self, tmp_storage: ReportStorage) -> None:
        report = {"test": True}
        tmp_storage.save_report(report, date_dir=date(2026, 7, 25))
        assert (tmp_storage.output_dir / "2026-07-25").exists()

    def test_markdown_written(self, tmp_storage: ReportStorage) -> None:
        report = {"shadow_run": True, "market": {"trade_date": "2026-07-24"}}
        tmp_storage.save_report(report, date_dir=date(2026, 7, 24))
        fp = report["_fingerprint"]
        md = tmp_storage.output_dir / "2026-07-24" / f"{fp}.md"
        assert md.exists()
        content = md.read_text(encoding="utf-8")
        assert "2026-07-24" in content

    def test_fingerprint_not_in_stable_keys(self, tmp_storage: ReportStorage) -> None:
        report = {"a": 1}
        tmp_storage.save_report(report)
        assert "_fingerprint" in report
        assert "_stored_at" in report
