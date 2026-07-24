"""Tests for RC3 manual import format."""

from __future__ import annotations

from datetime import date

import pytest

from src.investment_research.operations.manual_import import (
    ManualImportResult,
    parse_manual_import_dict,
)


class TestManualImportValid:
    def test_valid_minimal(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 1
        assert result.rejected_count == 0
        assert not result.errors

    def test_valid_with_optional(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3,
                 "change_percent": 1.63, "volume": 1_000_000, "market": "SZ", "limit_status": "normal",
                 "benchmark": -0.5, "sector_mapping": "banking", "watchlist_override": True},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 1
        assert result.rejected_count == 0
        row = result.rows[0]
        assert row.volume == 1_000_000
        assert row.market == "SZ"
        assert row.limit_status == "normal"

    def test_multiple_rows(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3, "change_percent": 1.63},
                {"symbol": "000002", "name": "万科A", "close": 8.0, "previous_close": 8.1, "change_percent": -1.23},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 2
        assert not result.errors

    def test_source_date_not_future(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": date.today().isoformat(),
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 1
        future_errors = [e for e in result.errors if "future" in e]
        assert not future_errors


class TestManualImportInvalid:
    def test_missing_schema_version(self) -> None:
        data = {
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [],
        }
        result = parse_manual_import_dict(data)
        assert any("schema_version" in e for e in result.errors)

    def test_wrong_source(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "eastmoney",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [],
        }
        result = parse_manual_import_dict(data)
        assert any("source" in e for e in result.errors)

    def test_future_source_date(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2099-01-01",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [],
        }
        result = parse_manual_import_dict(data)
        assert any("future" in e for e in result.errors)

    def test_missing_required_fields(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001"},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.rejected_count == 1
        assert any("name" in e for e in result.errors)
        assert any("close" in e for e in result.errors)

    def test_duplicate_symbols(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 12.5, "previous_close": 12.3, "change_percent": 1.63},
                {"symbol": "000001", "name": "平安银行", "close": 12.6, "previous_close": 12.3, "change_percent": 2.44},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 1
        assert result.rejected_count == 1
        assert any("duplicate" in e for e in result.errors)

    def test_invalid_rows_list(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": "not a list",
        }
        result = parse_manual_import_dict(data)
        assert any("rows" in e for e in result.errors)

    def test_rows_invalid_type(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": ["string", 42],
        }
        result = parse_manual_import_dict(data)
        assert "object" in result.errors[0].lower()

    def test_empty_rows(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [],
        }
        result = parse_manual_import_dict(data)
        assert result.accepted_count == 0
        assert result.rejected_count == 0
        assert not result.errors


class TestManualImportPanelConversion:
    def test_row_to_panel_entry(self) -> None:
        from src.investment_research.operations.manual_import import ManualImportRow, row_to_panel_entry
        row = ManualImportRow(
            symbol="000001",
            name="平安银行",
            close=12.5,
            previous_close=12.3,
            change_percent=1.63,
        )
        entry = row_to_panel_entry(row)
        assert entry["symbol"] == "000001"
        assert entry["close"] == 12.5
        assert entry["change_percent"] == 1.63

    def test_numeric_non_numeric_close(self) -> None:
        data = {
            "schema_version": "1.0",
            "source": "manual_import",
            "source_date": "2026-07-24",
            "availability_time": "2026-07-24T15:00:00",
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": "not-a-number", "previous_close": 12.3, "change_percent": 1.63},
            ],
        }
        result = parse_manual_import_dict(data)
        assert result.rejected_count == 1
