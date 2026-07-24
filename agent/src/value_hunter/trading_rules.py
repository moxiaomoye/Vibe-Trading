"""涨跌停判断、交易日检测辅助。纯函数，无可变状态，无网络。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Exchange(Enum):
    SH = "sh"
    SZ = "sz"
    BJ = "bj"


class LimitRule(Enum):
    """涨跌停限制规则。"""
    NORMAL_10PCT = 0.10
    STAR_20PCT = 0.20
    GEM_20PCT = 0.20  # 创业板
    BSE_30PCT = 0.30  # 北交所
    ST_HALF = "st_half"  # ST 在上述规则基础上减半


@dataclass(frozen=True)
class LimitRuleConfig:
    rule: LimitRule
    is_st: bool

    @property
    def limit_pct(self) -> float:
        if self.rule == LimitRule.ST_HALF:
            return 0.05
        if self.is_st:
            return self.rule.value / 2
        return self.rule.value


def classify_limit_rule(symbol: str) -> LimitRule:
    """根据股票代码前缀判断涨跌停限制规则。

    格式：600522.SH 或 600522
    """
    code = symbol.replace(".SH", "").replace(".SZ", "").replace(".BJ", "").strip().split(".")[0]
    prefix = code[:3]

    if code.startswith("4") or code.startswith("8"):
        return LimitRule.BSE_30PCT
    if prefix in ("300", "301"):
        return LimitRule.GEM_20PCT
    if prefix == "688":
        return LimitRule.STAR_20PCT
    return LimitRule.NORMAL_10PCT


def is_stock_st(symbol: str) -> bool:
    """简化判断：代码包含 ST 标记或名称含 ST。"""
    return symbol.endswith(".ST") or "ST" in symbol.upper()


def is_limit_down(
    close: float | None,
    prev_close: float | None,
    rule: LimitRule,
    is_st: bool = False,
) -> bool | None:
    """判断是否跌停。

    返回 None 表示数据不足以做出判断（停牌、无行情等）。
    """
    if close is None or prev_close is None or prev_close == 0:
        return None
    config = LimitRuleConfig(rule=rule, is_st=is_st)
    limit_pct = config.limit_pct
    threshold = prev_close * (1 - limit_pct)
    return close <= threshold + 0.01  # 允许一分钱误差


def is_limit_up(
    close: float | None,
    prev_close: float | None,
    rule: LimitRule,
    is_st: bool = False,
) -> bool | None:
    """判断是否涨停。"""
    if close is None or prev_close is None or prev_close == 0:
        return None
    config = LimitRuleConfig(rule=rule, is_st=is_st)
    limit_pct = config.limit_pct
    threshold = prev_close * (1 + limit_pct)
    return close >= threshold - 0.01
