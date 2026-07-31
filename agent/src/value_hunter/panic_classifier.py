"""恐慌等级分类器。纯函数，无网络，无可变状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PanicLevel(Enum):
    NORMAL = "normal"
    CAUTION = "caution"
    PANIC = "panic"
    EXTREME_PANIC = "extreme_panic"


@dataclass(frozen=True)
class PanicThresholds:
    caution_decline_ratio: float = 0.70
    caution_limit_down: int = 30
    panic_decline_ratio: float = 0.85
    panic_limit_down: int = 80
    extreme_decline_ratio: float = 0.95
    extreme_limit_down: int = 200


RULE_VERSION = "1.0.0"


@dataclass
class PanicClassification:
    level: PanicLevel
    reasons: list[str]
    rule_version: str = RULE_VERSION
    components: dict[str, float] = field(default_factory=dict)


def classify_panic(
    *,
    total_stocks: int,
    advance: int,
    decline: int,
    limit_down_count: int,
    thresholds: Optional[PanicThresholds] = None,
) -> PanicClassification:
    """根据市场宽度数据判断恐慌等级。

    所有参数都应来自 MarketSnapshot。当数据不足（total_stocks == 0）
    时返回 NORMAL 并注明数据不足。
    """
    t = thresholds or PanicThresholds()
    reasons: list[str] = []
    components: dict[str, float] = {}

    if total_stocks == 0:
        return PanicClassification(
            level=PanicLevel.NORMAL,
            reasons=["数据不足，无法判断恐慌等级"],
            components={"total_stocks": 0},
        )

    decline_ratio = decline / total_stocks
    components["decline_ratio"] = round(decline_ratio, 4)
    components["advance_ratio"] = round(advance / total_stocks, 4)
    components["limit_down_count"] = limit_down_count

    if decline_ratio >= t.extreme_decline_ratio or limit_down_count >= t.extreme_limit_down:
        level = PanicLevel.EXTREME_PANIC
        if decline_ratio >= t.extreme_decline_ratio:
            reasons.append(f"下跌比例 {decline_ratio:.1%} ≥ {t.extreme_decline_ratio:.0%}")
        if limit_down_count >= t.extreme_limit_down:
            reasons.append(f"跌停 {limit_down_count} 只 ≥ {t.extreme_limit_down}")
    elif decline_ratio >= t.panic_decline_ratio or limit_down_count >= t.panic_limit_down:
        level = PanicLevel.PANIC
        if decline_ratio >= t.panic_decline_ratio:
            reasons.append(f"下跌比例 {decline_ratio:.1%} ≥ {t.panic_decline_ratio:.0%}")
        if limit_down_count >= t.panic_limit_down:
            reasons.append(f"跌停 {limit_down_count} 只 ≥ {t.panic_limit_down}")
    elif decline_ratio >= t.caution_decline_ratio or limit_down_count >= t.caution_limit_down:
        level = PanicLevel.CAUTION
        if decline_ratio >= t.caution_decline_ratio:
            reasons.append(f"下跌比例 {decline_ratio:.1%} ≥ {t.caution_decline_ratio:.0%}")
        if limit_down_count >= t.caution_limit_down:
            reasons.append(f"跌停 {limit_down_count} 只 ≥ {t.caution_limit_down}")
    else:
        level = PanicLevel.NORMAL
        reasons.append(f"市场正常，下跌比例 {decline_ratio:.1%}，跌停 {limit_down_count} 只")

    return PanicClassification(
        level=level,
        reasons=reasons,
        components=components,
    )
