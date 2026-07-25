from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class HistoricalMarketPanel:
    date: date
    market_price: float
    market_change_pct: float
    ma_5: float
    ma_10: float
    ma_20: float
    volume: int
    turnover: float
    amplitude: float

    def __post_init__(self) -> None:
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.turnover < 0:
            raise ValueError("turnover must be non-negative")
        if self.amplitude < 0:
            raise ValueError("amplitude must be non-negative")
