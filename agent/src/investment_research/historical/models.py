from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class InputSchemaVersion(StrEnum):
    V1 = "1.0.0"


class InputRowStatus(StrEnum):
    ACCEPTED = "accepted"
    FUTURE_DATA = "future_data"
    MALFORMED = "malformed"
    DUPLICATE = "duplicate"
    CONFLICTING_VERSION = "conflicting_version"


@dataclass(frozen=True, slots=True)
class HistoricalInputRow:
    data_date: date
    source: str
    availability_time: datetime
    panel_data: dict[str, Any]
    row_status: InputRowStatus = InputRowStatus.ACCEPTED
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalInputSet:
    schema_version: InputSchemaVersion
    created_at: datetime
    rows: tuple[HistoricalInputRow, ...]
    import_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalImportReport:
    total_rows: int
    accepted: int
    future_data_rejected: int
    malformed: int
    duplicates: int
    conflicting_versions: int
    errors: tuple[str, ...] = ()
