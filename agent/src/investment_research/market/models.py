"""Evidence-backed market regime snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..contracts import MarketRegime, confidence_band


@dataclass(frozen=True, slots=True)
class MarketState:
    market_state_id: str
    regime: MarketRegime
    evidence_set_id: str
    drivers: tuple[str, ...]
    data_gaps: tuple[str, ...]
    confidence: float
    as_of: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("market state as_of must be timezone-aware")
        confidence_band(self.confidence)
        if not self.market_state_id or not self.evidence_set_id:
            raise ValueError("market state identity and evidence set are required")
        if self.regime != MarketRegime.UNKNOWN and not self.drivers:
            raise ValueError("a known market regime must state its drivers")
        if self.regime == MarketRegime.UNKNOWN and not self.data_gaps:
            raise ValueError("an unknown market regime must state its data gaps")

