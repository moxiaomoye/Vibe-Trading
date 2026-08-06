"""Fear Memory System (Phase 5) - Historical Crisis Library contract.

A curated, versioned library of real A-share crisis episodes. Its purpose is
to help a human researcher understand the environment during panic: episodes
are historical facts (dates, known index moves, documented causes), never
predictions and never trading directives.

PIT safety is the core contract: ``query_fear_memory`` only returns episodes
whose start date is <= the research as-of date. Episodes that begin after the
as-of date are counted and hidden, never leaked into the past.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

FEAR_MEMORY_VERSION = "fear-memory-v1"


class CrisisSeverity(StrEnum):
    """Severity class of a curated crisis episode (historical classification)."""

    SYSTEMIC = "SYSTEMIC"
    LOCALIZED = "LOCALIZED"
    SHOCK = "SHOCK"


class CrisisEpisode(BaseModel):
    """One curated historical crisis episode (facts only, PIT-safe)."""

    crisis_id: str
    label: str
    start_date: date
    end_date: date
    severity: CrisisSeverity
    narrative: str
    """Documented historical context (facts, causes); never a prediction."""
    key_stats: dict[str, Any] = Field(default_factory=dict)
    """Historical observed stats (e.g. index drawdown over the episode)."""
    sources: list[str] = Field(default_factory=list)


class FearMemoryConfig(BaseModel):
    """Frozen, curated crisis library (versioned; changes go through review)."""

    version: str = FEAR_MEMORY_VERSION
    episodes: list[CrisisEpisode] = Field(default_factory=list)

    @classmethod
    def curated(cls) -> "FearMemoryConfig":
        return cls(
            episodes=[
                CrisisEpisode(
                    crisis_id="2015-leverage-crash",
                    label="2015年杠杆股灾",
                    start_date=date(2015, 6, 15),
                    end_date=date(2015, 8, 26),
                    severity=CrisisSeverity.SYSTEMIC,
                    narrative=(
                        "场外配资去杠杆叠加汇率冲击引发系统性下跌，上证综指从5178点回落至"
                        "2850点附近，为A股历史上规模最大的去杠杆危机之一。"
                    ),
                    key_stats={"index_peak": 5178, "index_trough_approx": 2850},
                    sources=["公开历史行情记录（历史事实，非预测）"],
                ),
                CrisisEpisode(
                    crisis_id="2016-circuit-breaker",
                    label="2016年初熔断机制",
                    start_date=date(2016, 1, 4),
                    end_date=date(2016, 1, 27),
                    severity=CrisisSeverity.SYSTEMIC,
                    narrative=(
                        "指数熔断机制推出后四天内两度触发，引发流动性踩踏，随后机制被暂停；"
                        "1月全月主要指数跌幅约两成。"
                    ),
                    key_stats={"month_drawdown_approx_pct": -20},
                    sources=["公开历史记录（历史事实，非预测）"],
                ),
                CrisisEpisode(
                    crisis_id="2018-deleveraging",
                    label="2018年去杠杆与贸易摩擦熊市",
                    start_date=date(2018, 1, 29),
                    end_date=date(2018, 10, 19),
                    severity=CrisisSeverity.SYSTEMIC,
                    narrative=(
                        "资管新规去杠杆叠加外部贸易摩擦，A股全年单边下行，上证综指最低触及"
                        "约2449点，估值进入历史低位区域。"
                    ),
                    key_stats={"index_trough_approx": 2449},
                    sources=["公开历史记录（历史事实，非预测）"],
                ),
                CrisisEpisode(
                    crisis_id="2020-covid-shock",
                    label="2020年新冠疫情冲击",
                    start_date=date(2020, 2, 3),
                    end_date=date(2020, 3, 23),
                    severity=CrisisSeverity.SHOCK,
                    narrative=(
                        "疫情冲击叠加海外流动性危机，节后开盘大幅补跌，上证综指最低触及"
                        "约2646点；此后在全球宽松下快速修复。"
                    ),
                    key_stats={"index_trough_approx": 2646},
                    sources=["公开历史记录（历史事实，非预测）"],
                ),
                CrisisEpisode(
                    crisis_id="2024-microcap-liquidity",
                    label="2024年2月微盘股流动性危机",
                    start_date=date(2024, 1, 29),
                    end_date=date(2024, 2, 8),
                    severity=CrisisSeverity.SYSTEMIC,
                    narrative=(
                        "微盘股踩踏与雪球结构性产品敲入形成负反馈，中小盘指数短期大幅下跌；"
                        "中央汇金宣布扩大ETF增持范围后市场逐步企稳。"
                    ),
                    key_stats={"duration_trading_days_approx": 9},
                    sources=["公开历史记录（历史事实，非预测）"],
                ),
            ]
        )


class FearMemory(BaseModel):
    """The typed Fear Memory response for one research point in time."""

    version: str = FEAR_MEMORY_VERSION
    as_of: str
    visible_episodes: list[CrisisEpisode] = Field(default_factory=list)
    hidden_episodes_count: int = 0
    """Episodes starting after the as-of date; hidden for PIT safety."""
    summary: list[str] = Field(default_factory=list)


def query_fear_memory(
    as_of: date,
    config: FearMemoryConfig | None = None,
) -> FearMemory:
    """Return the crisis library visible at ``as_of`` (pure, no I/O).

    PIT rule: an episode is visible iff its ``start_date <= as_of``. Episodes
    in the future relative to the research date are counted in
    ``hidden_episodes_count`` but never returned.
    """
    config = config or FearMemoryConfig.curated()
    visible = [
        episode for episode in config.episodes
        if episode.start_date <= as_of
    ]
    hidden = len(config.episodes) - len(visible)
    summary = [
        f"历史危机案例库：as_of={as_of.isoformat()}，可见案例{len(visible)}个"
        f"{'，未来案例' + str(hidden) + '个已隐藏（PIT安全）' if hidden else ''}",
    ]
    if visible:
        latest = max(visible, key=lambda episode: episode.start_date)
        summary.append(
            f"距当前as_of最近的历史危机：{latest.label}（{latest.start_date.isoformat()}）"
        )
    return FearMemory(
        version=config.version,
        as_of=as_of.isoformat(),
        visible_episodes=visible,
        hidden_episodes_count=hidden,
        summary=summary,
    )
