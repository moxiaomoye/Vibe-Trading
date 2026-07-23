"""相对强弱计算。纯函数，无网络，无可变状态。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RelativeStrengthResult:
    change_pct: float
    relative_to_market: Optional[float]  # 个股涨跌幅 - 大盘涨跌幅
    relative_to_sector: Optional[float]  # 个股涨跌幅 - 行业涨跌幅
    is_sharp_decline: bool               # 大跌但未跌停
    is_limit_down: Optional[bool]        # None=数据不足


SHARP_DECLINE_THRESHOLD = -0.05  # 大跌阈值 -5%（可配置）


def compute_relative_strength(
    *,
    stock_change_pct: float | None,
    market_change_pct: float | None,
    sector_change_pct: float | None,
    is_limit_down: bool | None,
    sharp_decline_threshold: float = SHARP_DECLINE_THRESHOLD,
) -> RelativeStrengthResult:
    """计算个股的相对强弱指标。

    所有涨跌幅应为小数形式（如 -0.05 表示 -5%）。
    当数据不可用时相应字段返回 None。
    """
    if stock_change_pct is None:
        return RelativeStrengthResult(
            change_pct=0.0,
            relative_to_market=None,
            relative_to_sector=None,
            is_sharp_decline=False,
            is_limit_down=None,
        )

    rel_market = (
        round(stock_change_pct - market_change_pct, 4)
        if market_change_pct is not None
        else None
    )
    rel_sector = (
        round(stock_change_pct - sector_change_pct, 4)
        if sector_change_pct is not None
        else None
    )
    is_sharp = stock_change_pct <= sharp_decline_threshold and is_limit_down is not True

    return RelativeStrengthResult(
        change_pct=stock_change_pct,
        relative_to_market=rel_market,
        relative_to_sector=rel_sector,
        is_sharp_decline=is_sharp,
        is_limit_down=is_limit_down,
    )
