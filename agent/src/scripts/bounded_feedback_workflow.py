"""Bounded 20–60 trading-day feedback workflow using existing replay/calibration.

Usage:
    python -m src.scripts.bounded_feedback_workflow [--days 40] [--output-dir PATH]

Output:
    - market-state distribution
    - daily candidate counts
    - evidence completeness
    - 5/20-day outcome availability
    - false-positive/false-negative review rows
    - provenance/survivorship limitations
    - rule/watchlist versions
"""

from __future__ import annotations

import json
import logging
import sys
from argparse import ArgumentParser
from datetime import date, datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("bounded_feedback")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = ArgumentParser(description="Bounded feedback workflow")
    parser.add_argument("--days", type=int, default=40, help="Trading days to evaluate (default 40)")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    return parser.parse_args(argv)


def run_workflow(days: int = 40, output_dir: str | None = None) -> dict:
    from src.value_hunter.calibration import run_panic_calibration
    from src.value_hunter.history_replay import run_history_replay
    from src.value_hunter.post_close_provider import (
        ComponentFallbackPostCloseProvider,
    )
    from src.value_hunter.panic_scan import run_panic_scan

    end_date = date.today()
    logger.info("Running bounded feedback workflow: %d trading days ending %s", days, end_date)

    provider = ComponentFallbackPostCloseProvider()
    replay = run_history_replay(provider=provider, trading_days=days, end_date=end_date)

    calibration = run_panic_calibration(replay)

    result = {
        "workflow": "bounded_feedback",
        "trading_days": days,
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_days_available": len(replay.daily_scans),
        "market_state_distribution": _market_state_distribution(replay),
        "daily_candidate_counts": _candidate_counts(replay),
        "evidence_completeness": _evidence_completeness(replay),
        "outcome_availability": _outcome_availability(calibration),
        "review_rows": _review_rows(calibration),
        "provenance_limitations": _provenance_limitations(replay),
        "versions": _versions(replay),
    }

    if output_dir:
        path = Path(output_dir) / f"bounded_feedback_{days}d_{end_date.isoformat()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info("Workflow output saved: %s", path)

    return result


def _market_state_distribution(replay) -> dict:
    regimes: dict[str, int] = {}
    for scan in replay.daily_scans:
        regime = scan.panic.panic_observation.value if scan.panic else "unknown"
        regimes[regime] = regimes.get(regime, 0) + 1
    return {"regime_counts": regimes, "total_days": len(replay.daily_scans)}


def _candidate_counts(replay) -> list[dict]:
    counts = []
    for scan in replay.daily_scans:
        counts.append({
            "date": scan.data_date.isoformat() if scan.data_date else None,
            "candidate_count": len(scan.watchlist),
        })
    return counts


def _evidence_completeness(replay) -> dict:
    has_financial = 0
    has_event = 0
    total = len(replay.daily_scans)
    for scan in replay.daily_scans:
        if hasattr(scan, "financial_provenance") and scan.financial_provenance:
            has_financial += 1
        if hasattr(scan, "event_provenance") and scan.event_provenance:
            has_event += 1
    return {
        "total_days": total,
        "financial_data_days": has_financial,
        "event_data_days": has_event,
    }


def _outcome_availability(calibration) -> dict:
    if not calibration or not calibration.outcomes:
        return {"total_outcomes": 0}
    five_day = sum(1 for o in calibration.outcomes if hasattr(o, "outcome_5d") and o.outcome_5d is not None)
    twenty_day = sum(1 for o in calibration.outcomes if hasattr(o, "outcome_20d") and o.outcome_20d is not None)
    return {
        "total_outcomes": len(calibration.outcomes),
        "5d_available": five_day,
        "20d_available": twenty_day,
    }


def _review_rows(calibration) -> list[dict]:
    rows = []
    if not calibration or not calibration.outcomes:
        return rows
    for outcome in calibration.outcomes[:20]:
        rows.append({
            "symbol": getattr(outcome, "symbol", "unknown"),
            "date": getattr(outcome, "date", None),
            "action": getattr(outcome, "action_level", None),
            "outcome_5d": getattr(outcome, "outcome_5d", None),
            "outcome_20d": getattr(outcome, "outcome_20d", None),
        })
    return rows


def _provenance_limitations(replay) -> list[str]:
    limitations = []
    if not replay.daily_scans:
        limitations.append("no historical data available")
    else:
        limitations.append("survivorship bias: only current watchlist symbols evaluated")
        limitations.append("point-in-time: data reflects latest available, not original observation")
    return limitations


def _versions(replay) -> dict:
    return {
        "watchlist_version": getattr(replay, "watchlist_version", "unknown"),
        "watchlist_hash": getattr(replay, "watchlist_hash", ""),
    }


if __name__ == "__main__":
    args = _parse_args()
    result = run_workflow(days=args.days, output_dir=args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
