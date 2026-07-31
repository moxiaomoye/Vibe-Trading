"""Simple, point-in-time-safe macro evidence contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection
from ..evidence.inbox import EvidenceInboxItem, EvidenceInboxSubjectType


class MacroProviderStatus(StrEnum):
    CONFIGURED = "configured"
    UNCONFIGURED = "unconfigured"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    PARTIAL = "partial"
    HISTORICAL_UNSUPPORTED = "historical_unsupported"


@dataclass(frozen=True, slots=True)
class MacroObservationEvidence:
    provider: str
    series_id: str
    title: str
    observation_date: date
    value: Decimal
    retrieved_at: datetime
    source_url: str
    subject_id: str
    previous_observation_date: date | None = None
    previous_value: Decimal | None = None
    realtime_start: date | None = None
    realtime_end: date | None = None
    units: str | None = None
    frequency: str | None = None
    quality_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        for field_name in ("provider", "series_id", "title", "source_url", "subject_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if "://" in self.source_url:
            from urllib.parse import parse_qsl, urlparse

            parsed = urlparse(self.source_url)
            if parsed.username or parsed.password:
                raise ValueError("source_url must not contain credentials")
            secret_fields = {"api_key", "token", "access_token", "key"}
            if any(key.lower() in secret_fields for key, _ in parse_qsl(parsed.query)):
                raise ValueError("source_url must not contain credentials")

    @property
    def evidence_id(self) -> str:
        identity = (
            f"{self.provider}:{self.series_id}:{self.observation_date.isoformat()}:"
            f"{self.value}:{self.realtime_start}:{self.realtime_end}"
        )
        return str(uuid5(NAMESPACE_URL, f"macro-observation:{identity}"))

    def to_inbox_item(self, ingested_at: datetime) -> EvidenceInboxItem:
        """Create pending market evidence; direction remains neutral until review."""
        if ingested_at.tzinfo is None or ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        summary_parts = [
            f"{self.series_id} observation for {self.observation_date.isoformat()} "
            f"was {self.value}"
        ]
        if self.units:
            summary_parts[-1] += f" {self.units}"
        if self.previous_observation_date is not None and self.previous_value is not None:
            summary_parts.append(
                "previous observation "
                f"{self.previous_observation_date.isoformat()} was {self.previous_value}"
            )
        summary = "; ".join(summary_parts) + "."
        content_hash = hashlib.sha256(
            (
                f"{self.series_id}|{self.observation_date.isoformat()}|{self.value}|"
                f"{self.realtime_start}|{self.realtime_end}"
            ).encode("utf-8")
        ).hexdigest()
        # FRED's observations response does not provide an exact release
        # timestamp. First retrieval is therefore the earliest safe
        # availability time; this prevents historical replay from backfilling
        # today's revised value into the past.
        return EvidenceInboxItem(
            inbox_item_id=self.evidence_id,
            provider=self.provider,
            source_locator=(
                f"{self.provider}:{self.series_id}:"
                f"{self.observation_date.isoformat()}"
            ),
            title=self.title,
            summary=summary,
            published_at=self.retrieved_at,
            available_at=self.retrieved_at,
            observed_at=self.retrieved_at,
            content_hash=content_hash,
            quality_warnings=tuple(
                dict.fromkeys(
                    (
                        *self.quality_warnings,
                        "exact_release_time_unavailable_first_retrieval_used",
                        "current_revision_not_approved_for_historical_replay",
                    )
                )
            ),
            ingested_at=ingested_at,
            proposed_subject_type=EvidenceInboxSubjectType.MARKET,
            proposed_subject_id=self.subject_id,
            proposed_direction=EvidenceDirection.NEUTRAL,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "provider": self.provider,
            "series_id": self.series_id,
            "title": self.title,
            "observation_date": self.observation_date.isoformat(),
            "value": str(self.value),
            "previous_observation_date": (
                self.previous_observation_date.isoformat()
                if self.previous_observation_date
                else None
            ),
            "previous_value": (
                str(self.previous_value) if self.previous_value is not None else None
            ),
            "realtime_start": (
                self.realtime_start.isoformat() if self.realtime_start else None
            ),
            "realtime_end": (
                self.realtime_end.isoformat() if self.realtime_end else None
            ),
            "units": self.units,
            "frequency": self.frequency,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_url": self.source_url,
            "subject_id": self.subject_id,
            "quality_warnings": list(self.quality_warnings),
        }


@dataclass(frozen=True, slots=True)
class MacroEvidenceBatch:
    provider: str
    status: MacroProviderStatus
    as_of: date
    retrieved_at: datetime
    observations: tuple[MacroObservationEvidence, ...] = ()
    data_gaps: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "as_of": self.as_of.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "observations": [item.to_dict() for item in self.observations],
            "data_gaps": list(self.data_gaps),
            "errors": list(self.errors),
            "historical_replay_eligible": False,
        }
