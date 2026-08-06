"""Real Research Validation runner (v2, RRV-RELIABILITY-CLOSURE-001).

Reruns the five historical panic events through the closure production code
with an independent SQLite store and cache (data/rrv2/) so v2 never reuses
v1 snapshots. Dumps full reports (candidate contract, universe audit,
provider health, market state reconciliation) to docs/research_validation_v2/.

Usage:
    python automation/research_validation_v2.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
sys.path.insert(0, str(AGENT_ROOT))

from src.investment_research.application.research_mvp import build_historical_evaluation
from src.market_data import fetch_market_data
from src.value_hunter.config import ValueHunterConfig
from src.value_hunter.service import ValueHunterService

EVENTS: list[tuple[str, str]] = [
    ("2015-06-26", "2015 股灾第一波暴跌"),
    ("2018-10-11", "2018 贸易战暴跌传导"),
    ("2020-02-03", "2020 疫情节后千股跌停"),
    ("2022-03-15", "2022 俄乌冲突+疫情大跌"),
    ("2024-02-05", "2024 微盘股踩踏"),
]

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "rrv2"
OUT_DIR = ROOT / "docs" / "research_validation_v2"
WATCHLIST = ROOT / "config" / "watchlist.yaml"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = ValueHunterConfig(
        enabled=False,
        provider="akshare",
        schedule="18:10",
        timezone="Asia/Shanghai",
        market_alert_score=70,
        candidate_alert_score=75,
        max_candidates=5,
        database_path=DATA_DIR / "research-v2.sqlite3",
        watchlist_path=WATCHLIST if WATCHLIST.exists() else None,
        feishu_webhook_url="",
        smtp_host="", smtp_port=465, smtp_username="", smtp_password="",
        smtp_from="", email_to="", notify_on_demo=False,
    )
    service = ValueHunterService(config)
    summary = {
        "runner": "research_validation_v2",
        "independent_store": str(DATA_DIR),
        "events": [],
    }
    for iso, label in EVENTS:
        trade_date = date.fromisoformat(iso)
        target = OUT_DIR / f"{iso}.json"
        t0 = time.time()
        print(f"[run ] {iso} {label} ...", flush=True)
        try:
            report = build_historical_evaluation(service, trade_date, fetch_market_data)
            target.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            reconciliation = report.get("market_state_reconciliation", {})
            elapsed = round(time.time() - t0, 1)
            entry = {
                "trade_date": iso,
                "label": label,
                "seconds": elapsed,
                "market_state": report.get("market_state"),
                "effective_market_state": reconciliation.get("effective_market_state"),
                "intelligence_state": reconciliation.get("intelligence_state"),
                "reconciliation_upgraded": reconciliation.get("upgraded"),
                "coverage_gate_passed": reconciliation.get("coverage_gate_passed"),
                "candidates": len(report.get("candidates", [])),
                "excluded": len([
                    row for row in report.get("universe_audit", [])
                    if row.get("eligibility_status") == "CONFIRMED_NOT_LISTED"
                ]),
                "gaps": len(report.get("data_gaps", [])),
                "provider_health": report.get("provider_health", []),
            }
            summary["events"].append(entry)
            print(
                f"[ok  ] {iso} seconds={elapsed} "
                f"state={report.get('market_state')} "
                f"effective={entry['effective_market_state']} "
                f"intel={entry['intelligence_state']} "
                f"candidates={len(report.get('candidates', []))} "
                f"excluded={entry['excluded']} "
                f"file={target}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - record any failure honestly
            entry = {
                "trade_date": iso,
                "label": label,
                "seconds": round(time.time() - t0, 1),
                "error": f"{type(exc).__name__}: {exc}",
            }
            summary["events"].append(entry)
            print(f"[fail] {iso} {label} after {round(time.time() - t0, 1)}s: {type(exc).__name__}: {exc}", flush=True)
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[done] summary -> {OUT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
