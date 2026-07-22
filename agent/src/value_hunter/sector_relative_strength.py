"""Date-safe sector membership and return resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from src.value_hunter.market_snapshot import DataGap
from src.value_hunter.post_close_provider import SectorMembership


@dataclass(frozen=True)
class SectorRelativeInput:
    sector: str | None
    sector_change_pct: float | None
    data_gap: DataGap | None = None


def resolve_sector_relative_input(
    *,
    symbol: str,
    scan_date: date,
    memberships: Sequence[SectorMembership],
    sector_returns: Mapping[str, float],
    sector_return_date: date | None,
    sector_return_availability_date: date | None,
) -> SectorRelativeInput:
    """Resolve only information that was available and valid on ``scan_date``."""
    aliases = {symbol, symbol.split(".")[0]}
    symbol_memberships = [item for item in memberships if item.symbol in aliases]
    if not symbol_memberships:
        return _gap("缺少行业归属数据")

    available = [
        item
        for item in symbol_memberships
        if item.source_date <= scan_date and item.availability_date <= scan_date
    ]
    if not available:
        return _gap("行业归属数据在扫描日尚不可用")

    valid = [
        item
        for item in available
        if (
            item.source_date == scan_date
            if item.valid_through is None
            else item.source_date <= scan_date <= item.valid_through
        )
    ]
    if not valid:
        return _gap("行业归属数据已过期")

    membership = sorted(
        valid,
        key=lambda item: (item.source_date, item.availability_date, item.sector),
    )[-1]
    if sector_return_date is None or sector_return_availability_date is None:
        return _gap("缺少行业收益日期")
    if sector_return_date > scan_date or sector_return_availability_date > scan_date:
        return _gap("行业收益在扫描日尚不可用")
    if sector_return_date < scan_date:
        return _gap("行业收益不是扫描日数据")

    sector_change = sector_returns.get(membership.sector)
    if sector_change is None:
        return _gap(f"缺少行业收益数据: {membership.sector}")
    return SectorRelativeInput(
        sector=membership.sector,
        sector_change_pct=float(sector_change),
    )


def _gap(description: str) -> SectorRelativeInput:
    return SectorRelativeInput(
        sector=None,
        sector_change_pct=None,
        data_gap=DataGap(description=description),
    )
