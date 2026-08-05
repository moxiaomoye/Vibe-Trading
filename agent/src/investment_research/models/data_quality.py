"""Unified data quality expression (Task 4).

Replaces bare ``None`` ambiguity in research payloads with an explicit
four-state classification so missing data can never be mistaken for a real
zero. Pure data model: no I/O.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DataQualityStatus(StrEnum):
    """Four-state data quality classification."""

    MISSING = "missing"
    """Data does not exist for the research point in time at all."""

    AVAILABLE = "available"
    """Data exists and is usable as of the research point in time."""

    ESTIMATED = "estimated"
    """Data is an estimate or derived value; the reason must say how."""

    UNAVAILABLE = "unavailable"
    """Data exists in principle but cannot be obtained as of this date."""


class DataQualityIssue(BaseModel):
    """One field's quality verdict."""

    field: str
    status: DataQualityStatus
    reason: str | None = None
    as_of: date | None = None
    source: str | None = None


class DataQualityReport(BaseModel):
    """Aggregated quality verdicts for one research artifact."""

    issues: list[DataQualityIssue] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.status.value] = counts.get(issue.status.value, 0) + 1
        return counts

    def issues_for(self, prefix: str) -> list[DataQualityIssue]:
        return [issue for issue in self.issues if issue.field.startswith(prefix)]

    def all_available(self) -> bool:
        return all(issue.status is DataQualityStatus.AVAILABLE for issue in self.issues)


def classify_data_quality(
    field: str,
    value: Any,
    *,
    unavailable_reason: str | None = None,
    missing_reason: str | None = None,
    estimate_note: str | None = None,
    as_of: date | None = None,
    source: str | None = None,
) -> DataQualityIssue:
    """Classify one observed value.

    ``None`` maps to ``unavailable`` when a specific ``unavailable_reason`` is
    given (the field exists in principle but cannot be obtained), otherwise to
    ``missing``. A non-``None`` value maps to ``available`` unless
    ``estimate_note`` is given (then ``estimated``). A real zero (0.0/0/False)
    is a valid value and maps to ``available`` — this is the core guarantee
    against missing data being mistaken for zero.
    """
    if value is None:
        if unavailable_reason:
            return DataQualityIssue(
                field=field,
                status=DataQualityStatus.UNAVAILABLE,
                reason=unavailable_reason,
                as_of=as_of,
                source=source,
            )
        return DataQualityIssue(
            field=field,
            status=DataQualityStatus.MISSING,
            reason=missing_reason or "no data for the research point in time",
            as_of=as_of,
            source=source,
        )
    if estimate_note:
        return DataQualityIssue(
            field=field,
            status=DataQualityStatus.ESTIMATED,
            reason=estimate_note,
            as_of=as_of,
            source=source,
        )
    return DataQualityIssue(
        field=field,
        status=DataQualityStatus.AVAILABLE,
        as_of=as_of,
        source=source,
    )
