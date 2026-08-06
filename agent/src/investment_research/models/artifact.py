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
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5

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


def compute_data_snapshot_id(scan_payload: Mapping[str, Any]) -> str:
    """Deterministic fingerprint of the input scan snapshot.

    Hashes only the auditable point-in-time data (provider mode, market
    observation and scored market block, candidate observations), so the same
    stored snapshot always yields the same snapshot id regardless of
    generation time or derived report content. Derived state (universe,
    research_context, errors) is excluded to keep live, stored, and rebuild
    paths comparable.
    """
    canonical = {
        "mode": scan_payload.get("mode"),
        "market": scan_payload.get("market"),
        "candidates": scan_payload.get("candidates"),
    }
    return compute_content_hash(canonical)


def make_research_id(as_of_date: date, rules_version: str = RULES_VERSION) -> str:
    """Deterministic artifact identity for one (date, rules) pair."""
    return f"{as_of_date:%Y%m%d}-{rules_version}"


def make_research_run_id(scan_payload: Mapping[str, Any]) -> str:
    """Deterministic research run identity for one scan snapshot.

    Derived from the underlying scan ``run_id``, so the live path, the
    stored-snapshot evaluation, and the rebuild path of the same scan all
    converge on the same research run id. Snapshots without a ``run_id`` fall
    back to the data snapshot fingerprint, keeping the id stable per input.
    """
    run_id = scan_payload.get("run_id")
    seed = f"research:{run_id}" if run_id else f"research:{compute_data_snapshot_id(scan_payload)}"
    return str(uuid5(NAMESPACE_URL, seed))


def provider_version_for(provider_name: str) -> str:
    """Map a provider name to a stable version tag."""
    return f"{provider_name}-v1"


class ArtifactMetadata(BaseModel):
    """Identity block attached to every research artifact.

    Identity is driven by the deterministic fields (``as_of_date``,
    ``rules_version``, ``data_snapshot_id``, ``content_hash``), so the same
    input snapshot and rules produce a traceable artifact across live, stored,
    and rebuild evaluation paths. ``created_at`` is generation time only and
    never participates in identity hashes.
    """

    research_id: str
    research_run_id: str | None = None
    created_at: datetime
    as_of_date: date
    requested_date: date
    rules_version: str = RULES_VERSION
    provider_version: str
    artifact_version: int = ARTIFACT_SCHEMA_VERSION
    rules_fingerprint: str | None = None
    data_snapshot_id: str | None = None
    content_hash: str | None = None

    @property
    def schema_version(self) -> int:
        """Deprecated alias of ``artifact_version`` kept for compatibility."""
        return self.artifact_version

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
