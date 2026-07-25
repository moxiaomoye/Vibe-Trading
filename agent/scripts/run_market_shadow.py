"""Run a market shadow report using real market data.

Usage:
    python -m agent.scripts.run_market_shadow [--date YYYY-MM-DD] [--output-dir PATH]

Data sources (no auth required):
    - Sina spot (real-time A-share quotes via AKShare)
    - Sina CSI300 index daily (last trading day)
    - East Money fallback when available

No credentials required.  No notifications sent.  No trades executed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("market_shadow")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run market shadow report")
    parser.add_argument("--date", type=str, default=None, help="Trade date (YYYY-MM-DD, default: today)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory (default: agent/data/)")
    parser.add_argument("--mode", choices=["provider", "manual"], default="provider",
                        help="Input mode: provider (live data) or manual (import file)")
    parser.add_argument("--input-file", type=str, default=None,
                        help="Path to manual import JSON file (required when --mode=manual)")
    return parser.parse_args(argv)


def _fetch_spot_data() -> tuple[pd.DataFrame, date, str]:
    """Fetch A-share real-time spot data from Sina.

    Returns (spot_df, trade_date, source_name).
    May return empty DataFrame when market is closed or data unavailable.
    """
    import akshare as ak
    import pandas as pd

    trade_date = date.today()

    # Try Sina spot first (free, no auth)
    try:
        spot = ak.stock_zh_a_spot()
        if spot is not None and not spot.empty:
            logger.info("Sina spot: %d rows", len(spot))
            return spot, trade_date, "sina"
    except Exception as e:
        logger.warning("Sina spot failed: %s", e)

    # Fallback: East Money spot (may be CDN-blocked from non-China IPs)
    try:
        spot = ak.stock_zh_a_spot_em()
        if spot is not None and not spot.empty:
            logger.info("East Money spot: %d rows", len(spot))
            return spot, trade_date, "eastmoney"
    except Exception as e:
        logger.warning("East Money spot failed: %s", e)

    logger.warning("All spot sources unavailable — returning empty DataFrame")
    return pd.DataFrame(), trade_date, "unavailable"


def _fetch_benchmark(as_of: date) -> float | None:
    """Fetch CSI300 daily return for *as_of*. Returns None if unavailable."""
    import akshare as ak
    from src.value_hunter.post_close_provider import _last_daily_return

    try:
        frame = ak.stock_zh_index_daily(symbol="sh000300")
        return _last_daily_return(frame, as_of)
    except Exception as e:
        logger.warning("Benchmark CSI300 fetch failed: %s", e)
    return None


def _normalize_code(code: str) -> str:
    """Normalize a single code: sh600522 -> 600522.SH"""
    import re
    m = re.match(r"^(sh|sz|bj)(\d{6})$", code.strip())
    if m:
        return f"{m.group(2)}.{m.group(1).upper()}"
    return code


def _normalize_codes(spot_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Sina codes (sh600522) to watchlist format (600522.SH)."""
    import pandas as pd
    df = spot_df.copy()
    # Find the code column by name (代码) — it's always the first column in Sina
    code_col = "代码"
    if code_col not in df.columns:
        logger.warning("No 代码 column found in spot data, cannot normalize codes")
        return df
    raw = df[code_col].astype(str).str.strip()
    df[code_col] = raw.str.replace(r"^sh(\d{6})$", r"\1.SH", regex=True)
    df[code_col] = df[code_col].str.replace(r"^sz(\d{6})$", r"\1.SZ", regex=True)
    df[code_col] = df[code_col].str.replace(r"^bj(\d{6})$", r"\1.BJ", regex=True)
    return df


def _build_panel_data(
    spot_df,
    trade_date: date,
    source: str,
    benchmark_return: float | None,
) -> dict:
    """Build a panel_data dict matching the schema expected by ShadowRunInputs."""
    import pandas as pd

    observed_at = datetime.now(timezone.utc)

    if not spot_df.empty:
        expected_cols = {"代码", "名称", "最新价", "涨跌幅", "昨收"}
        spot = spot_df.copy()
        for col in expected_cols:
            if col not in spot.columns:
                spot[col] = 0
                logger.warning("Spot data missing column: %s", repr(col))
    else:
        spot = spot_df

    # Normalize codes first so limit_up/down and watchlist matching work
    spot = _normalize_codes(spot)

    limit_up_symbols: set[str] = set()
    limit_down_symbols: set[str] = set()
    if not spot.empty and "涨跌幅" in spot.columns:
        up_mask = spot["涨跌幅"].astype(float) >= 9.8
        down_mask = spot["涨跌幅"].astype(float) <= -9.8
        if "代码" in spot.columns:
            limit_up_symbols = set(spot.loc[up_mask, "代码"].astype(str).str.strip())
            limit_down_symbols = set(spot.loc[down_mask, "代码"].astype(str).str.strip())

    return {
        "spot_df": spot,
        "limit_up_symbols": limit_up_symbols,
        "limit_down_symbols": limit_down_symbols,
        "data_date": trade_date,
        "availability_date": trade_date,
        "now": observed_at,
        "market_change_pct": benchmark_return,
        "sector_map": {},
        "sector_memberships": [],
        "sector_returns": {},
        "sector_return_date": trade_date,
        "sector_return_availability_date": trade_date,
        "source": source,
        "component_sources": {"spot": source, "benchmark": "sina_index" if benchmark_return is not None else "unavailable"},
        "provider_errors": [],
        "data_gaps": [],
    }


def run():
    import pandas as pd  # noqa: F811

    args = _parse_args()
    if args.date:
        trade_date = date.fromisoformat(args.date)
    else:
        trade_date = date.today()

    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parents[1] / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"shadow-{trade_date.isoformat()}-{args.mode}"
    observed_at = datetime.now(timezone.utc)
    information_cutoff = observed_at + timedelta(hours=1)
    data_available_at = observed_at

    if args.mode == "manual":
        if not args.input_file:
            logger.error("--input-file is required when --mode=manual")
            sys.exit(1)
        from src.investment_research.operations.manual_import import parse_manual_import_json, row_to_panel_entry
        result = parse_manual_import_json(args.input_file)
        if result.errors:
            for e in result.errors:
                logger.error("Import error: %s", e)
            logger.error("Accepted %d, rejected %d rows", result.accepted_count, result.rejected_count)
            sys.exit(1)
        source = "manual_import"
        spot_rows = [row_to_panel_entry(r) for r in result.rows]
        spot_df = pd.DataFrame(spot_rows)
        source_date = result.source_date
        benchmark_return = result.rows[0].benchmark if result.rows else None
        logger.info("Manual import: %d rows from %s", len(spot_rows), result.source_date)
    else:
        logger.info("Loading market data for %s ...", trade_date.isoformat())

        # Step 1: Fetch spot data
        spot_df, source_date, source = _fetch_spot_data()
        if spot_df.empty:
            logger.warning("Spot data is empty — report will reflect data gaps")

        # Step 2: Fetch benchmark (try today first, then yesterday)
        benchmark_return = _fetch_benchmark(trade_date)
        if benchmark_return is None:
            prev = trade_date - timedelta(days=1)
            while prev.weekday() >= 5:
                prev -= timedelta(days=1)
            benchmark_return = _fetch_benchmark(prev)
            if benchmark_return is None:
                logger.warning("Benchmark return unavailable — report will reflect data gap")
            else:
                logger.info("Benchmark CSI300 return (from %s): %+f%%", prev, benchmark_return * 100)
        else:
            logger.info("Benchmark CSI300 return: %+f%%", benchmark_return * 100)

    # Step 3: Build panel_data
    panel_data = _build_panel_data(spot_df, trade_date, source, benchmark_return)

    logger.info("Panel: %d spot rows | source=%s | benchmark=%s",
                len(spot_df), source,
                f"{benchmark_return*100:+.2f}%" if benchmark_return else "N/A")

    # Step 4: Run shadow pipeline
    from datetime import time

    from src.investment_research.application.shadow_run import (
        PanicResearchShadowRunner,
        ShadowRunConfig,
        ShadowRunInputs,
    )
    from src.investment_research.application.panic_orchestration import (
        OrchestrationRequest,
    )
    from src.investment_research.operations.scheduling import TradingDaySchedule

    watchlist_path = str(Path(__file__).resolve().parents[2] / "config" / "research" / "a_share_watchlist.yaml")

    logger.info("Running shadow pipeline ...")
    runner = PanicResearchShadowRunner(
        ShadowRunConfig(
            enabled=True,
            schedule=TradingDaySchedule(run_after=time(0, 0)),
        )
    )

    request = OrchestrationRequest(
        run_id=run_id,
        now=observed_at,
        data_date=trade_date,
        data_available_at=data_available_at,
    )
    inputs = ShadowRunInputs(
        panel_data=panel_data,
        watchlist_path=watchlist_path,
        information_cutoff=information_cutoff,
    )

    result = runner.run(request, inputs)

    if result.status.value == "succeeded" and result.output is not None:
        report = result.output.to_dict()
        report["shadow_run"] = True
        report["manual_review_required"] = True
        report["data_source"] = source

        json_path = output_dir / f"shadow_report_{trade_date.isoformat()}.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("JSON report saved: %s", json_path)

        md_path = output_dir / f"shadow_report_{trade_date.isoformat()}.md"
        md_lines = _format_markdown(report, source, panel_data)
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        logger.info("Markdown report saved: %s", md_path)

        _print_summary(report, source, spot_df)
    elif result.status.value != "succeeded" and result.output is None:
        err_detail = result.error if hasattr(result, 'error') and result.error else "see debug file"
        logger.error("Shadow run failed: status=%s reasons=%s error=%s", result.status.value, list(result.reasons), err_detail)
        # Save partial output for debugging
        debug = {
            "run_id": run_id,
            "status": result.status.value,
            "reasons": list(result.reasons),
            "error": result.error,
            "trade_date": trade_date.isoformat(),
            "spot_rows": len(spot_df),
            "source": source,
            "benchmark": benchmark_return,
        }
        debug_path = output_dir / f"shadow_debug_{trade_date.isoformat()}.json"
        debug_path.write_text(json.dumps(debug, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("Debug info saved: %s", debug_path)
        sys.exit(1)


def _format_markdown(report: dict, source: str, panel_data: dict) -> list[str]:
    market = report.get("market", {})
    lines = []
    lines.append(f"# Market Shadow Report — {market.get('trade_date', 'unknown')}")
    lines.append("")
    lines.append(f"- **Data Source:** {source}")
    lines.append(f"- **Shadow Run:** {report.get('shadow_run', False)}")
    lines.append(f"- **Manual Review Required:** {report.get('manual_review_required', True)}")
    lines.append(f"- **Information Cutoff:** {report.get('information_cutoff', 'N/A')}")
    lines.append("")
    lines.append("## Market State")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Trade Date | {market.get('trade_date', 'N/A')} |")
    lines.append(f"| Regime | {market.get('regime', 'N/A')} |")
    lines.append(f"| Panic Level | {market.get('panic_observation', 'N/A')} |")
    lines.append(f"| Advancing | {market.get('advance', 'N/A')} |")
    lines.append(f"| Declining | {market.get('decline', 'N/A')} |")
    lines.append(f"| Large Rise (>=4%) | {market.get('large_rise', 'N/A')} |")
    lines.append(f"| Large Decline (<=-4%) | {market.get('large_decline', 'N/A')} |")
    lines.append(f"| Limit Down | {market.get('limit_down', 'N/A')} |")
    lines.append(f"| Median Return | {market.get('median_daily_return', 'N/A')} |")
    lines.append("")

    screen = report.get("screened_watchlist", [])
    if screen:
        lines.append("## Watchlist Screening")
        lines.append("")
        lines.append("| Symbol | Change% | vs Market | vs Sector | Limit Down | Data Gap |")
        lines.append("|---|---|---|---|---|---|")
        for item in screen:
            gap = item.get("data_gap") or ""
            ld = "Y" if item.get("is_limit_down") else "N"
            lines.append(
                f"| {item['symbol']} | {item.get('change_pct', '')} | "
                f"{item.get('relative_to_market', '')} | {item.get('relative_to_sector', '')} | {ld} | {gap} |"
            )
        lines.append("")

    candidates = report.get("research_candidates", [])
    if candidates:
        lines.append("## Research Candidates")
        lines.append("")
        for c in candidates:
            lines.append(f"- **{c['symbol']}** — Action: {c.get('action_level', 'N/A')}, "
                         f"Confidence: {c.get('confidence', 'N/A')}")
            lines.append(f"  - Quality: {c.get('quality_status', 'N/A')}, "
                         f"Valuation: {c.get('valuation_status', 'N/A')}")
            ev = c.get("supporting_evidence", [])
            if ev:
                lines.append(f"  - Supporting Evidence: {len(ev)} items")
            cv = c.get("counter_evidence", [])
            if cv:
                lines.append(f"  - Counter Evidence: {len(cv)} items")
            lines.append("")

    data_gaps = report.get("data_gaps", [])
    if data_gaps:
        lines.append("## Data Gaps & Warnings")
        lines.append("")
        for g in data_gaps:
            lines.append(f"- {g}")
        lines.append("")

    return lines


def _print_summary(report: dict, source: str, spot_df):
    market = report.get("market", {})
    print()
    print("=" * 60)
    print(f"  MARKET SHADOW REPORT — {market.get('trade_date', 'unknown')}")
    print("=" * 60)
    print(f"  Source:          {source}")
    print(f"  Spot rows:       {len(spot_df)}")
    print(f"  Regime:          {market.get('regime', 'N/A')}")
    print(f"  Panic Level:     {market.get('panic_observation', 'N/A')}")
    print(f"  Advance/Decline: {market.get('advance', 'N/A')} / {market.get('decline', 'N/A')}")
    print(f"  Limit Down:      {market.get('limit_down', 'N/A')}")
    print(f"  Median Return:   {market.get('median_daily_return', 'N/A')}")
    print(f"  Data Gaps:       {len(report.get('data_gaps', []))}")
    print(f"  Research Candidates: {len(report.get('research_candidates', []))}")
    print(f"  Manual Review:   {report.get('manual_review_required', True)}")
    print("=" * 60)

    screen = report.get("screened_watchlist", [])
    if screen:
        print(f"  Watchlist ({len(screen)} symbols):")
        for item in screen[:5]:
            ld = " [LIMIT DOWN]" if item.get("is_limit_down") else ""
            print(f"    {item['symbol']}: {item.get('change_pct', '?')}%{ld}")
        if len(screen) > 5:
            print(f"    ... and {len(screen) - 5} more")
    print("=" * 60)


if __name__ == "__main__":
    run()
