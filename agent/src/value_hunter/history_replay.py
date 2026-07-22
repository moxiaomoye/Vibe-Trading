"""多交易日历史回放。复用现有确定性逻辑，无网络，无持久化，无通知。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Optional

from src.value_hunter.market_snapshot import DataGap, build_snapshot_from_akshare
from src.value_hunter.panic_classifier import PanicThresholds, RULE_VERSION, classify_panic
from src.value_hunter.panic_scan import PanicScanResult, ScannedCandidate
from src.value_hunter.relative_strength import compute_relative_strength
from src.value_hunter.sector_relative_strength import resolve_sector_relative_input
from src.value_hunter.trading_rules import (
    classify_limit_rule,
    is_limit_down,
    is_stock_st,
)
from src.value_hunter.watchlist_loader import WatchlistConfig, load_watchlist

logger = logging.getLogger(__name__)


@dataclass
class HistoryReplayEntry:
    trade_date: date
    result: Optional[PanicScanResult]
    rule_version: str
    watchlist_hash: str
    skip_reason: Optional[str] = None
    data_gap: Optional[DataGap] = None


@dataclass
class HistoryReplayResult:
    entries: list[HistoryReplayEntry]
    rule_version: str
    watchlist_hash: str
    watchlist_version: str
    watchlist_name: str
    replay_start: date
    replay_end: date
    errors: list[str] = field(default_factory=list)

    @property
    def processed_dates(self) -> list[date]:
        return [e.trade_date for e in self.entries if e.skip_reason is None]

    @property
    def skipped_dates(self) -> list[tuple[date, str]]:
        return [(e.trade_date, e.skip_reason) for e in self.entries if e.skip_reason is not None]


def _scan_day_candidates(
    symbols: list[str],
    spot_df: Any,
    *,
    market_change_pct: Optional[float] = None,
    sector_map: Optional[dict[str, float]] = None,
    sector_memberships: Optional[list[Any]] = None,
    sector_returns: Optional[dict[str, float]] = None,
    sector_return_date: Optional[date] = None,
    sector_return_availability_date: Optional[date] = None,
    trade_date: Optional[date] = None,
) -> list[ScannedCandidate]:
    """扫描单日观察池个股。"""
    code_to_row: dict[str, Any] = {}
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
                data_gap=DataGap(description="当日行情中未找到"),
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
                ld = is_limit_down(float(close), float(prev_close), rule, is_st=st)
            except (ValueError, TypeError):
                ld = None

        sector_gap = None
        if sector_memberships is not None or sector_returns is not None:
            sector_input = resolve_sector_relative_input(
                symbol=symbol,
                scan_date=trade_date or date.min,
                memberships=sector_memberships or [],
                sector_returns=sector_returns or {},
                sector_return_date=sector_return_date,
                sector_return_availability_date=sector_return_availability_date,
            )
            sector_cp = sector_input.sector_change_pct
            sector_gap = sector_input.data_gap
        else:
            sector_cp = None
        if sector_cp is None and sector_map is not None and sector_memberships is None:
            sector_cp = sector_map.get(symbol)
            if sector_cp is None:
                sector_cp = sector_map.get(raw_code)
        if sector_cp is None and sector_gap is None:
            sector_gap = DataGap(description="缺少行业收益数据")
        rs = compute_relative_strength(
            stock_change_pct=change_pct_f,
            market_change_pct=market_change_pct,
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


def run_history_replay(
    *,
    daily_panels: dict[date, dict[str, Any]],
    watchlist_path: Optional[Path] = None,
    thresholds: Optional[PanicThresholds] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> HistoryReplayResult:
    """执行多交易日历史回放。

    每个 daily_panels 条目应包含 panic_scan 所需的 panel_data 字段：
        spot_df, limit_up_symbols, limit_down_symbols,
        data_date, market_change_pct, sector_map 等。

    每个交易日 D 只使用 D 日或之前的数据。
    后续日期数据不影响之前日期结果。
    """
    watchlist_cfg: WatchlistConfig = load_watchlist(watchlist_path)
    symbols = list(watchlist_cfg.symbols)
    t = thresholds or PanicThresholds()
    errors: list[str] = []

    sorted_dates = sorted(d for d in daily_panels if start_date is None or d >= start_date)
    if end_date:
        sorted_dates = [d for d in sorted_dates if d <= end_date]

    entries: list[HistoryReplayEntry] = []

    for trade_date in sorted_dates:
        panel = daily_panels[trade_date]
        panel_date = panel.get("data_date", trade_date)

        if panel_date != trade_date:
            dg = DataGap(
                is_stale=True,
                last_trade_date=panel_date,
                gap_days=abs((trade_date - panel_date).days),
                description=f"数据日期 {panel_date} 与回放日期 {trade_date} 不一致",
            )
            entries.append(HistoryReplayEntry(
                trade_date=trade_date,
                result=None,
                rule_version=RULE_VERSION,
                watchlist_hash=watchlist_cfg.content_hash,
                skip_reason=f"数据日期不匹配: {panel_date} != {trade_date}",
                data_gap=dg,
            ))
            continue

        spot_df = panel.get("spot_df")
        if spot_df is None or (hasattr(spot_df, "empty") and spot_df.empty):
            entries.append(HistoryReplayEntry(
                trade_date=trade_date,
                result=None,
                rule_version=RULE_VERSION,
                watchlist_hash=watchlist_cfg.content_hash,
                skip_reason="无行情数据",
                data_gap=DataGap(description="spot_df 为空"),
            ))
            continue

        snapshot = build_snapshot_from_akshare(
            spot_df,
            limit_up_symbols=set(panel.get("limit_up_symbols", [])),
            limit_down_symbols=set(panel.get("limit_down_symbols", [])),
            data_date=trade_date,
            now=panel.get("now"),
        )

        panic = classify_panic(
            total_stocks=snapshot.total_stocks,
            advance=snapshot.advance,
            decline=snapshot.decline,
            limit_down_count=snapshot.limit_down,
            thresholds=t,
        )

        market_change = panel.get("market_change_pct")
        sector_map = panel.get("sector_map")
        candidates = _scan_day_candidates(
            symbols, spot_df,
            market_change_pct=market_change,
            sector_map=sector_map,
            sector_memberships=panel.get("sector_memberships"),
            sector_returns=panel.get("sector_returns"),
            sector_return_date=panel.get("sector_return_date"),
            sector_return_availability_date=panel.get("sector_return_availability_date"),
            trade_date=trade_date,
        )

        scanned_at = panel.get("now") or datetime.combine(
            trade_date,
            time(hour=15),
            tzinfo=timezone.utc,
        )
        result = PanicScanResult(
            scanned_at=scanned_at,
            market_snapshot=snapshot,
            panic=panic,
            watchlist=candidates,
            data_date=trade_date,
        )
        entries.append(HistoryReplayEntry(
            trade_date=trade_date,
            result=result,
            rule_version=RULE_VERSION,
            watchlist_hash=watchlist_cfg.content_hash,
            data_gap=snapshot.data_gap if snapshot.data_gap.is_stale else None,
        ))

    return HistoryReplayResult(
        entries=entries,
        rule_version=RULE_VERSION,
        watchlist_hash=watchlist_cfg.content_hash,
        watchlist_version=watchlist_cfg.version,
        watchlist_name=watchlist_cfg.name,
        replay_start=sorted_dates[0] if sorted_dates else (start_date or end_date or date.min),
        replay_end=sorted_dates[-1] if sorted_dates else (end_date or start_date or date.min),
        errors=errors,
    )
