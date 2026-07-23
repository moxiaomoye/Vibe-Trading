"""A股盘后恐慌初筛 MVP 编排入口。

默认不加载，不进入核心 startup/shutdown。
通过调用 run_panic_scan() 手动触发 dry-run。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.value_hunter.market_snapshot import (
    DataGap,
    MarketSnapshot,
    build_snapshot_from_akshare,
)
from src.value_hunter.panic_classifier import (
    PanicClassification,
    PanicThresholds,
    RULE_VERSION,
    classify_panic,
)
from src.value_hunter.post_close_provider import (
    ComponentFallbackPostCloseProvider,
    PostCloseProvider,
    ProviderDataGap,
    SinaBenchmarkAdapter,
    UpstreamError,
)
from src.value_hunter.relative_strength import (
    RelativeStrengthResult,
    compute_relative_strength,
)
from src.value_hunter.sector_relative_strength import resolve_sector_relative_input
from src.value_hunter.trading_rules import (
    classify_limit_rule,
    is_limit_down as check_limit_down,
    is_stock_st,
)
from src.value_hunter.watchlist_loader import load_watchlist

logger = logging.getLogger(__name__)


@dataclass
class ScannedCandidate:
    symbol: str
    name: str
    close: float | None
    change_pct: float | None
    relative_to_market: float | None
    relative_to_sector: float | None
    is_limit_down: bool | None
    is_sharp_decline: bool
    is_suspended: bool | None
    data_gap: DataGap


@dataclass
class PanicScanResult:
    scanned_at: datetime
    market_snapshot: MarketSnapshot
    panic: PanicClassification
    watchlist: list[ScannedCandidate]
    rule_version: str = RULE_VERSION
    data_date: date | None = None
    availability_date: date | None = None
    source: str = "unknown"
    watchlist_hash: str = ""
    watchlist_version: str = ""
    data_gaps: list[ProviderDataGap] = field(default_factory=list)
    provider_errors: list[UpstreamError] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_panic_scan(
    *,
    panel_data: Optional[dict[str, Any]] = None,
    watchlist_path: Optional[str] = None,
    thresholds: Optional[PanicThresholds] = None,
    provider: PostCloseProvider | None = None,
    as_of: date | None = None,
) -> PanicScanResult:
    """执行一次 A 股盘后恐慌初筛 dry-run。

    参数：
        panel_data: 预加载的行情数据（用于测试）。为 None 时尝试实时获取。
        watchlist_path: 观察池配置文件路径。为 None 时使用默认路径。
        thresholds: 恐慌阈值。为 None 时使用默认值。
    """
    errors: list[str] = []

    if panel_data is None:
        normalized = (
            provider
            or ComponentFallbackPostCloseProvider(
                benchmark_fallback=SinaBenchmarkAdapter()
            )
        ).load(as_of=as_of)
        panel_data = normalized.to_panel_data()
    now = panel_data.get("now", datetime.now(timezone.utc))

    # 第 1 步：获取市场数据
    snapshot = _fetch_market_data(panel_data)
    if snapshot.data_gap.is_stale:
        errors.append(snapshot.data_gap.description)

    # 第 2 步：恐慌分类
    panic = classify_panic(
        total_stocks=snapshot.total_stocks,
        advance=snapshot.advance,
        decline=snapshot.decline,
        limit_down_count=snapshot.limit_down,
        thresholds=thresholds,
    )

    # 第 3 步：加载观察池
    try:
        watchlist_config = load_watchlist(Path(watchlist_path) if watchlist_path else None)
        symbols = list(watchlist_config.symbols)
    except (FileNotFoundError, ValueError) as exc:
        errors.append(f"观察池加载失败: {exc}")
        return PanicScanResult(
            scanned_at=now,
            market_snapshot=snapshot,
            panic=panic,
            watchlist=[],
            data_date=snapshot.trade_date,
            availability_date=panel_data.get("availability_date", snapshot.trade_date),
            source=panel_data.get("source", "fixture"),
            watchlist_hash="",
            watchlist_version="",
            data_gaps=list(panel_data.get("data_gaps", [])),
            provider_errors=list(panel_data.get("provider_errors", [])),
            errors=errors,
        )

    # 第 4 步：扫描观察池
    candidates = _scan_watchlist(symbols, panel_data, snapshot)

    return PanicScanResult(
        scanned_at=now,
        market_snapshot=snapshot,
        panic=panic,
        watchlist=candidates,
        data_date=snapshot.trade_date,
        availability_date=panel_data.get("availability_date", snapshot.trade_date),
        source=panel_data.get("source", "fixture"),
        watchlist_hash=watchlist_config.content_hash,
        watchlist_version=watchlist_config.version,
        data_gaps=list(panel_data.get("data_gaps", [])),
        provider_errors=list(panel_data.get("provider_errors", [])),
        errors=errors,
    )


def _fetch_market_data(panel_data: dict) -> MarketSnapshot:
    """从 Provider 标准面板构建市场快照。"""
    return build_snapshot_from_akshare(
        spot_df=panel_data.get("spot_df", __import__("pandas").DataFrame()),
        limit_up_symbols=set(panel_data.get("limit_up_symbols", [])),
        limit_down_symbols=set(panel_data.get("limit_down_symbols", [])),
        data_date=panel_data.get("data_date", date.today()),
        now=panel_data.get("now", datetime.now(timezone.utc)),
        source=panel_data.get("source", "fixture"),
    )


def _scan_watchlist(
    symbols: list[str],
    panel_data: dict | None,
    snapshot: MarketSnapshot,
) -> list[ScannedCandidate]:
    """扫描观察池个股。"""
    if panel_data is None:
        return [
            ScannedCandidate(
                symbol=s,
                name="",
                close=None, change_pct=None,
                relative_to_market=None, relative_to_sector=None,
                is_limit_down=None, is_sharp_decline=False,
                is_suspended=None,
                data_gap=DataGap(description="无实时数据"),
            )
            for s in symbols
        ]

    spot_df = panel_data.get("spot_df")
    market_change = panel_data.get("market_change_pct")
    sector_map = panel_data.get("sector_map", {})
    code_to_row = {}
    if spot_df is not None:
        normalized_codes = spot_df["代码"].astype(str).str.strip()
        for code, (_, row) in zip(normalized_codes, spot_df.iterrows()):
            code_to_row[code] = row

    results: list[ScannedCandidate] = []
    for symbol in symbols:
        raw_code = symbol.split(".")[0]
        row = code_to_row.get(symbol)
        if row is None:
            row = code_to_row.get(raw_code)
        if row is None:
            results.append(ScannedCandidate(
                symbol=symbol, name="",
                close=None, change_pct=None,
                relative_to_market=None, relative_to_sector=None,
                is_limit_down=None, is_sharp_decline=False,
                is_suspended=None,
                data_gap=DataGap(description="未在当日行情中找到"),
            ))
            continue

        close = row.get("最新价")
        change_pct = row.get("涨跌幅", row.get("pct_chg", 0))
        if isinstance(change_pct, str):
            change_pct = float(change_pct) if change_pct else None
        if isinstance(change_pct, (int, float)):
            change_pct_f = float(change_pct) / 100 if abs(float(change_pct)) > 1 else float(change_pct)
        else:
            change_pct_f = None

        rule = classify_limit_rule(symbol)
        st = is_stock_st(symbol)
        prev_close = row.get("昨收")
        ld = None
        if close is not None and prev_close is not None:
            try:
                ld = check_limit_down(float(close), float(prev_close), rule, is_st=st)
            except (ValueError, TypeError):
                ld = None

        sector_gap = None
        if "sector_memberships" in panel_data or "sector_returns" in panel_data:
            sector_input = resolve_sector_relative_input(
                symbol=symbol,
                scan_date=snapshot.trade_date,
                memberships=panel_data.get("sector_memberships", []),
                sector_returns=panel_data.get("sector_returns", {}),
                sector_return_date=panel_data.get("sector_return_date"),
                sector_return_availability_date=panel_data.get("sector_return_availability_date"),
            )
            sector_cp = sector_input.sector_change_pct
            sector_gap = sector_input.data_gap
        else:
            sector_cp = sector_map.get(symbol)
            if sector_cp is None:
                sector_cp = sector_map.get(raw_code)
            if sector_cp is None:
                sector_gap = DataGap(description="缺少行业收益数据")
        rs = compute_relative_strength(
            stock_change_pct=change_pct_f,
            market_change_pct=market_change,
            sector_change_pct=sector_cp,
            is_limit_down=ld,
        )

        results.append(ScannedCandidate(
            symbol=symbol,
            name=str(row.get("名称", "")),
            close=float(close) if close is not None else None,
            change_pct=change_pct_f,
            relative_to_market=rs.relative_to_market,
            relative_to_sector=rs.relative_to_sector,
            is_limit_down=ld,
            is_sharp_decline=rs.is_sharp_decline,
            is_suspended=None,
            data_gap=sector_gap or DataGap(),
        ))

    return results
