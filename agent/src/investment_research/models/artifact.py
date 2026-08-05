"""Artifact identity and versioning (Tasks 2).

Minimal, extensible artifact metadata for reproducible research results:
identity (``research_id``), generation time, point-in-time date, and the
version tracks for rules / provider / schema. No raw market data is stored
here, and no object storage is designed — only the identity structure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from .rules_version import RULES_VERSION

ARTIFACT_SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization (sorted keys, compact, UTF-8)."""

    def _default(item: Any) -> Any:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        return str(item)

    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_default,
    )


def compute_content_hash(value: Any) -> str:
    """SHA-256 over the canonical serialization of a research payload."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def make_research_id(as_of_date: date, rules_version: str = RULES_VERSION) -> str:
    """Deterministic artifact identity for one (date, rules) pair."""
    return f"{as_of_date:%Y%m%d}-{rules_version}"


def provider_version_for(provider_name: str) -> str:
    """Map a provider name to a stable version tag."""
    return f"{provider_name}-v1"


class ArtifactMetadata(BaseModel):
    """Identity block attached to every research artifact."""

    research_id: str
    created_at: datetime
    as_of_date: date
    requested_date: date
    rules_version: str = RULES_VERSION
    provider_version: str
    schema_version: int = ARTIFACT_SCHEMA_VERSION
    rules_fingerprint: str | None = None
    content_hash: str | None = None

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("requested_date")
    @classmethod
    def _requested_date_not_after_as_of(cls, value: date, info: Any) -> date:
        as_of = info.data.get("as_of_date")
        if as_of is not None and value > as_of:
            raise ValueError("requested_date cannot be after as_of_date")
        return value
