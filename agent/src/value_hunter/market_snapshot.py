"""市场快照结构、AKShare 集中适配器、DataGap 检查。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd

from src.value_hunter.panic_classifier import RULE_VERSION
from src.value_hunter.trading_rules import (
    classify_limit_rule,
    is_limit_down,
    is_limit_up,
    is_stock_st,
)


@dataclass
class DataGap:
    is_stale: bool = False
    last_trade_date: Optional[date] = None
    gap_days: int = 0
    description: str = ""


@dataclass
class MarketSnapshot:
    trade_date: date
    data_time: datetime
    total_stocks: int
    advance: int
    decline: int
    flat: int
    large_rise: int      # >= 4%
    large_decline: int    # <= -4%
    limit_up: int
    limit_down: int
    median_daily_return: float | None
    advance_ratio: float
    decline_ratio: float
    source: str
    data_gap: DataGap = field(default_factory=DataGap)
    rule_version: str = RULE_VERSION


def build_snapshot_from_akshare(
    spot_df: pd.DataFrame,
    *,
    limit_up_symbols: set[str],
    limit_down_symbols: set[str],
    data_date: date,
    now: Optional[datetime] = None,
    source: str = "akshare",
) -> MarketSnapshot:
    """从 AKShare 实时行情 DataFrame 构建 MarketSnapshot。

    spot_df 应包含列：代码, 名称, 最新价, 涨跌幅, 昨收
    """
    if now is None:
        now = datetime.now(timezone.utc)

    total = len(spot_df)
    if total == 0:
        return MarketSnapshot(
            trade_date=data_date,
            data_time=now,
            total_stocks=0, advance=0, decline=0, flat=0,
            large_rise=0, large_decline=0,
            limit_up=0, limit_down=0,
            median_daily_return=None,
            advance_ratio=0.0, decline_ratio=0.0,
            source=source,
            data_gap=DataGap(description="无数据"),
        )

    df = spot_df.copy()
    df["涨跌幅"] = pd.to_numeric(df.get("涨跌幅", df.get("pct_chg", 0)), errors="coerce").fillna(0)
    df["代码_str"] = df["代码"].astype(str).str.strip()

    # 涨停/跌停数量（优先使用专用 pool）
    lu = sum(1 for s in df["代码_str"] if s in limit_up_symbols)
    ld = sum(1 for s in df["代码_str"] if s in limit_down_symbols)

    advance = int((df["涨跌幅"] > 0).sum())
    decline = int((df["涨跌幅"] < 0).sum())
    flat = total - advance - decline
    large_rise = int((df["涨跌幅"] >= 4).sum())
    large_decline = int((df["涨跌幅"] <= -4).sum())
    median_daily_return = float(df["涨跌幅"].median()) / 100.0

    # 若专用 pool 不可用则逐行复用交易规则，不用固定涨跌幅阈值预筛。
    if ld == 0 and decline > 0:
        for _, row in df.iterrows():
            try:
                code = row["代码_str"]
                name = str(row.get("名称", ""))
                rule = classify_limit_rule(code)
                prev_close = row.get("昨收", None)
                close = row.get("最新价", None)
                if is_limit_down(
                    float(close),
                    float(prev_close),
                    rule,
                    is_st=is_stock_st(name),
                ):
                    ld += 1
            except (ValueError, TypeError):
                pass
    if lu == 0 and advance > 0:
        for _, row in df.iterrows():
            try:
                code = row["代码_str"]
                name = str(row.get("名称", ""))
                rule = classify_limit_rule(code)
                prev_close = row.get("昨收", None)
                close = row.get("最新价", None)
                if is_limit_up(
                    float(close),
                    float(prev_close),
                    rule,
                    is_st=is_stock_st(name),
                ):
                    lu += 1
            except (ValueError, TypeError):
                pass

    advance_ratio = round(advance / total, 4) if total > 0 else 0.0
    decline_ratio = round(decline / total, 4) if total > 0 else 0.0

    data_gap = DataGap()
    today = date.today()
    if data_date < today:
        gap = (today - data_date).days
        data_gap = DataGap(
            is_stale=True,
            last_trade_date=data_date,
            gap_days=gap,
            description=f"数据日期 {data_date} 早于当前日期 {today}，相差 {gap} 天",
        )

    return MarketSnapshot(
        trade_date=data_date,
        data_time=now,
        total_stocks=total,
        advance=advance,
        decline=decline,
        flat=flat,
        large_rise=large_rise,
        large_decline=large_decline,
        limit_up=lu,
        limit_down=ld,
        median_daily_return=median_daily_return,
        advance_ratio=advance_ratio,
        decline_ratio=decline_ratio,
        source=source,
        data_gap=data_gap,
    )
