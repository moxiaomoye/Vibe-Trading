"""Asset-neutral research identities and evidence-backed Thesis exposure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import AssetType


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Asset:
    asset_id: str
    symbol: str
    name: str
    asset_type: AssetType
    market: str
    currency: str
    created_at: datetime
    active: bool = True

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        for field_name in ("asset_id", "symbol", "name", "market", "currency"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class ThesisExposure:
    exposure_id: str
    asset_id: str
    thesis_id: str
    thesis_version_id: str
    evidence_set_id: str
    exposure_strength: float
    exposure_purity: float
    rationale: str
    as_of: datetime

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        if not all((self.exposure_id, self.asset_id, self.thesis_id, self.thesis_version_id, self.evidence_set_id)):
            raise ValueError("exposure identity and evidence references are required")
        if not 0 <= self.exposure_strength <= 1 or not 0 <= self.exposure_purity <= 1:
            raise ValueError("exposure strength and purity must be between 0 and 1")
        if not self.rationale.strip():
            raise ValueError("exposure rationale is required")

