"""Import validator for bounded historical evaluation inputs.

Validates:
- schema/version is present
- each row has data_date <= today
- each row has source and availability_time
- availability_time <= now (no future data)
- no duplicate data_date
- no conflicting version
- does not silently drop rows
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from .models import (
    HistoricalImportReport,
    HistoricalInputRow,
    HistoricalInputSet,
    InputRowStatus,
    InputSchemaVersion,
)


class HistoricalInputValidator:
    """Validates historical evaluation input sets.

    Does NOT modify thresholds, calibrate parameters, or evaluate
    strategy performance.
    """

    VERSION = InputSchemaVersion.V1

    def validate(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        import_time: datetime | None = None,
    ) -> HistoricalInputSet:
        now = import_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("import_time must be timezone-aware")

        import_errors: list[str] = []
        validated: list[HistoricalInputRow] = []
        seen_dates: set[date] = set()
        seen_versions: set[str] = set()

        for i, row in enumerate(rows):
            row_errors: list[str] = []

            data_date = row.get("data_date")
            if data_date is None:
                row_errors.append(f"row {i}: missing data_date")
                validated.append(HistoricalInputRow(
                    data_date=date.min, source="", availability_time=now,
                    panel_data=row, row_status=InputRowStatus.MALFORMED,
                    errors=tuple(row_errors),
                ))
                continue

            if isinstance(data_date, str):
                try:
                    data_date = date.fromisoformat(data_date)
                except ValueError:
                    row_errors.append(f"row {i}: invalid data_date format: {data_date}")
                    validated.append(HistoricalInputRow(
                        data_date=date.min, source="", availability_time=now,
                        panel_data=row, row_status=InputRowStatus.MALFORMED,
                        errors=tuple(row_errors),
                    ))
                    continue

            source = row.get("source", "")
            if not source:
                row_errors.append(f"row {i}: missing source")

            avail_raw = row.get("availability_time") or row.get("available_at")
            if avail_raw is None:
                row_errors.append(f"row {i}: missing availability_time")
                availability_time = now
            else:
                if isinstance(avail_raw, str):
                    try:
                        availability_time = datetime.fromisoformat(avail_raw)
                    except ValueError:
                        row_errors.append(f"row {i}: invalid availability_time")
                        availability_time = now
                else:
                    availability_time = avail_raw

            if availability_time.tzinfo is None:
                row_errors.append(f"row {i}: availability_time must be timezone-aware")
                availability_time = now

            # Future data check (use exchange-local date, not UTC)
            exchange_date = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
            if data_date > exchange_date:
                validated.append(HistoricalInputRow(
                    data_date=data_date, source=source,
                    availability_time=availability_time,
                    panel_data=row, row_status=InputRowStatus.FUTURE_DATA,
                    errors=tuple(row_errors),
                ))
                continue

            if availability_time > now:
                validated.append(HistoricalInputRow(
                    data_date=data_date, source=source,
                    availability_time=availability_time,
                    panel_data=row, row_status=InputRowStatus.FUTURE_DATA,
                    errors=tuple(row_errors),
                ))
                continue

            # Duplicate check
            if data_date in seen_dates:
                validated.append(HistoricalInputRow(
                    data_date=data_date, source=source,
                    availability_time=availability_time,
                    panel_data=row, row_status=InputRowStatus.DUPLICATE,
                    errors=("duplicate data_date",),
                ))
                continue

            seen_dates.add(data_date)

            # Version check
            sv = row.get("schema_version", self.VERSION.value)
            if isinstance(sv, str):
                seen_versions.add(sv)

            status = InputRowStatus.MALFORMED if row_errors else InputRowStatus.ACCEPTED
            validated.append(HistoricalInputRow(
                data_date=data_date, source=source,
                availability_time=availability_time,
                panel_data=row, row_status=status,
                errors=tuple(row_errors),
            ))

        if len(seen_versions) > 1:
            import_errors.append(f"conflicting schema versions: {seen_versions}")
            validated = [
                r if r.row_status != InputRowStatus.ACCEPTED
                else HistoricalInputRow(
                    data_date=r.data_date, source=r.source,
                    availability_time=r.availability_time,
                    panel_data=r.panel_data,
                    row_status=InputRowStatus.CONFLICTING_VERSION,
                    errors=tuple(list(r.errors) + ["conflicting schema version"]),
                )
                for r in validated
            ]

        accepted = sum(1 for r in validated if r.row_status == InputRowStatus.ACCEPTED)
        future = sum(1 for r in validated if r.row_status == InputRowStatus.FUTURE_DATA)
        malformed = sum(1 for r in validated if r.row_status == InputRowStatus.MALFORMED)
        dups = sum(1 for r in validated if r.row_status == InputRowStatus.DUPLICATE)

        return HistoricalInputSet(
            schema_version=self.VERSION,
            created_at=now,
            rows=tuple(validated),
            import_errors=tuple(import_errors),
        )

    def report(self, result: HistoricalInputSet) -> HistoricalImportReport:
        cv_count = sum(1 for r in result.rows if r.row_status == InputRowStatus.CONFLICTING_VERSION)
        return HistoricalImportReport(
            total_rows=len(result.rows),
            accepted=sum(1 for r in result.rows if r.row_status == InputRowStatus.ACCEPTED),
            future_data_rejected=sum(1 for r in result.rows if r.row_status == InputRowStatus.FUTURE_DATA),
            malformed=sum(1 for r in result.rows if r.row_status == InputRowStatus.MALFORMED),
            duplicates=sum(1 for r in result.rows if r.row_status == InputRowStatus.DUPLICATE),
            conflicting_versions=cv_count,
            errors=result.import_errors,
        )
