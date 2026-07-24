"""Versioned manual import format for current-market data.

Schema version ``1.0``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = "1.0"
ALLOWED_SOURCES: set[str] = {"manual_import"}
MINIMUM_FIELDS: set[str] = {"symbol", "name", "close", "previous_close", "change_percent"}
OPTIONAL_FIELDS: set[str] = {"volume", "market", "benchmark", "limit_status", "sector_mapping", "watchlist_override"}


@dataclass
class ManualImportRow:
    symbol: str
    name: str
    close: float
    previous_close: float
    change_percent: float
    volume: float | None = None
    market: str | None = None
    benchmark: float | None = None
    limit_status: str | None = None
    sector_mapping: str | None = None
    watchlist_override: bool | None = None


@dataclass
class ManualImportResult:
    schema_version: str
    source: str
    source_date: date
    availability_time: datetime
    rows: list[ManualImportRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    accepted_count: int = 0
    rejected_count: int = 0


def parse_manual_import_json(path: str | Path) -> ManualImportResult:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _validate_manifest(data)


def parse_manual_import_dict(data: dict[str, Any]) -> ManualImportResult:
    return _validate_manifest(data)


def _validate_manifest(data: dict[str, Any]) -> ManualImportResult:
    errors: list[str] = []
    rows: list[ManualImportRow] = []

    sv = data.get("schema_version")
    if not sv:
        errors.append("missing schema_version")

    source = data.get("source", "")
    if source not in ALLOWED_SOURCES:
        errors.append(f"source must be 'manual_import', got {source!r}")

    try:
        source_date = date.fromisoformat(data.get("source_date", ""))
        if source_date > date.today():
            errors.append(f"source_date {source_date} is in the future")
    except (ValueError, TypeError):
        errors.append("invalid or missing source_date (expected YYYY-MM-DD)")
        source_date = date.today()

    try:
        avail = data.get("availability_time", "")
        availability_time = datetime.fromisoformat(avail) if avail else datetime.now(timezone.utc)
    except (ValueError, TypeError):
        errors.append("invalid availability_time (expected ISO 8601)")
        availability_time = datetime.now(timezone.utc)

    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        errors.append("rows must be a list")
        raw_rows = []

    seen_symbols: set[str] = set()
    for i, row in enumerate(raw_rows):
        row_errors = _validate_row(row, i, seen_symbols)
        if row_errors:
            errors.extend(row_errors)
        else:
            rows.append(ManualImportRow(
                symbol=str(row.get("symbol", "")),
                name=str(row.get("name", "")),
                close=float(row.get("close", 0)),
                previous_close=float(row.get("previous_close", 0)),
                change_percent=float(row.get("change_percent", 0)),
                volume=_safe_float(row.get("volume")),
                market=str(row.get("market", "")) if row.get("market") else None,
                benchmark=_safe_float(row.get("benchmark")),
                limit_status=str(row.get("limit_status", "")) if row.get("limit_status") else None,
                sector_mapping=str(row.get("sector_mapping", "")) if row.get("sector_mapping") else None,
                watchlist_override=bool(row.get("watchlist_override")) if row.get("watchlist_override") is not None else None,
            ))

    return ManualImportResult(
        schema_version=sv or SCHEMA_VERSION,
        source=source,
        source_date=source_date,
        availability_time=availability_time,
        rows=rows,
        errors=errors,
        accepted_count=len(rows),
        rejected_count=len(raw_rows) - len(rows),
    )


def _validate_row(row: Any, index: int, seen: set[str]) -> list[str]:
    errs: list[str] = []
    if not isinstance(row, dict):
        return [f"row {index}: expected object, got {type(row).__name__}"]

    for field_name in MINIMUM_FIELDS:
        if field_name not in row or row[field_name] is None or (isinstance(row[field_name], str) and not row[field_name].strip()):
            errs.append(f"row {index}: missing required field {field_name!r}")

    symbol = str(row.get("symbol", ""))
    if symbol and symbol in seen:
        errs.append(f"row {index}: duplicate symbol {symbol!r}")
    seen.add(symbol)

    if "close" in row and row["close"] is not None:
        try:
            float(row["close"])
        except (ValueError, TypeError):
            errs.append(f"row {index}: close must be numeric")

    if "previous_close" in row and row["previous_close"] is not None:
        try:
            float(row["previous_close"])
        except (ValueError, TypeError):
            errs.append(f"row {index}: previous_close must be numeric")

    if "change_percent" in row and row["change_percent"] is not None:
        try:
            float(row["change_percent"])
        except (ValueError, TypeError):
            errs.append(f"row {index}: change_percent must be numeric")

    return errs


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def row_to_panel_entry(row: ManualImportRow) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "name": row.name,
        "close": row.close,
        "previous_close": row.previous_close,
        "change_percent": row.change_percent,
        "volume": row.volume,
        "market": row.market,
        "limit_status": row.limit_status,
        "benchmark": row.benchmark,
        "sector_mapping": row.sector_mapping,
    }
