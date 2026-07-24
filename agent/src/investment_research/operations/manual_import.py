"""Versioned manual import format for current-market data.

Schema version ``1.0``
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "1.0"
ALLOWED_SOURCES: set[str] = {"manual_import"}
MINIMUM_FIELDS: set[str] = {"symbol", "name", "close", "previous_close", "change_percent"}
OPTIONAL_FIELDS: set[str] = {"volume", "market", "benchmark", "limit_status", "sector_mapping", "watchlist_override"}
ALLOWED_LIMIT_STATUSES = {"normal", "limit_up", "limit_down"}
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 10_000
FUTURE_CLOCK_SKEW = timedelta(minutes=5)


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
    source_path = Path(path)
    if source_path.suffix.lower() != ".json":
        raise ValueError("manual import file must use the .json extension")
    if not source_path.is_file():
        raise ValueError("manual import file does not exist or is not a regular file")
    if source_path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError(f"manual import file exceeds {MAX_IMPORT_BYTES} bytes")
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manual import file is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("manual import root must be a JSON object")
    return _validate_manifest(data)


def parse_manual_import_dict(data: dict[str, Any]) -> ManualImportResult:
    return _validate_manifest(data)


def _validate_manifest(data: dict[str, Any]) -> ManualImportResult:
    errors: list[str] = []
    rows: list[ManualImportRow] = []

    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}, got {sv!r}")

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
        availability_time = datetime.fromisoformat(avail)
        if availability_time.tzinfo is None or availability_time.utcoffset() is None:
            errors.append("availability_time must include a timezone offset")
            availability_time = availability_time.replace(tzinfo=timezone.utc)
        if availability_time > datetime.now(timezone.utc) + FUTURE_CLOCK_SKEW:
            errors.append("availability_time must not be in the future")
        if availability_time.astimezone(ZoneInfo("Asia/Shanghai")).date() < source_date:
            errors.append("availability_time must not precede source_date")
    except (ValueError, TypeError):
        errors.append("invalid availability_time (expected timezone-aware ISO 8601)")
        availability_time = datetime.now(timezone.utc)

    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list):
        errors.append("rows must be a list")
        raw_rows = []
    elif len(raw_rows) > MAX_IMPORT_ROWS:
        errors.append(f"rows exceeds maximum of {MAX_IMPORT_ROWS}")
        raw_rows = raw_rows[:MAX_IMPORT_ROWS]

    seen_symbols: set[str] = set()
    for i, row in enumerate(raw_rows):
        row_errors = _validate_row(row, i, seen_symbols)
        if row_errors:
            errors.extend(row_errors)
        else:
            rows.append(ManualImportRow(
                symbol=_normalize_symbol(row.get("symbol")),
                name=str(row.get("name", "")).strip(),
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

    symbol = _normalize_symbol(row.get("symbol"))
    if symbol and not re.fullmatch(r"\d{6}", symbol):
        errs.append(f"row {index}: symbol must contain a six-digit A-share code")
    if symbol and symbol in seen:
        errs.append(f"row {index}: duplicate symbol {symbol!r}")
    seen.add(symbol)

    close = _finite_float(row.get("close"))
    previous_close = _finite_float(row.get("previous_close"))
    change_percent = _finite_float(row.get("change_percent"))
    if close is None:
        errs.append(f"row {index}: close must be a finite number")
    elif close <= 0:
        errs.append(f"row {index}: close must be greater than zero")
    if previous_close is None:
        errs.append(f"row {index}: previous_close must be a finite number")
    elif previous_close <= 0:
        errs.append(f"row {index}: previous_close must be greater than zero")
    if change_percent is None:
        errs.append(f"row {index}: change_percent must be a finite number")
    elif not -100 <= change_percent <= 100:
        errs.append(f"row {index}: change_percent must be between -100 and 100 percentage points")
    if close is not None and previous_close and change_percent is not None:
        calculated = (close / previous_close - 1.0) * 100.0
        if abs(calculated - change_percent) > 0.2:
            errs.append(
                f"row {index}: change_percent is inconsistent with close and previous_close"
            )

    for field_name in ("volume", "benchmark"):
        if row.get(field_name) is not None and _finite_float(row[field_name]) is None:
            errs.append(f"row {index}: {field_name} must be a finite number")
    if _finite_float(row.get("volume")) is not None and float(row["volume"]) < 0:
        errs.append(f"row {index}: volume must not be negative")
    if row.get("limit_status") not in (None, "", *ALLOWED_LIMIT_STATUSES):
        errs.append(
            f"row {index}: limit_status must be one of {sorted(ALLOWED_LIMIT_STATUSES)}"
        )

    return errs


def _safe_float(v: Any) -> float | None:
    return _finite_float(v)


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    match = re.fullmatch(r"(?:(?:SH|SZ|BJ)[.-]?)?(\d{6})(?:[.-]?(?:SH|SZ|BJ))?", raw)
    return match.group(1) if match else raw


def row_to_panel_entry(row: ManualImportRow) -> dict[str, Any]:
    return {
        "代码": row.symbol,
        "名称": row.name,
        "最新价": row.close,
        "昨收": row.previous_close,
        "涨跌幅": row.change_percent,
        "成交量": row.volume,
        "market": row.market,
        "limit_status": row.limit_status,
        "benchmark": row.benchmark,
        "sector_mapping": row.sector_mapping,
    }
