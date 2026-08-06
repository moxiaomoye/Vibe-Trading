"""Real Research Validation runner.

Runs the historical evaluation pipeline (unchanged production code) against
five historical panic events and dumps full reports to docs/research_validation/.

Usage:
    python automation/research_validation.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
sys.path.insert(0, str(AGENT_ROOT))

from src.api.value_hunter_routes import get_value_hunter_service
from src.investment_research.application.research_mvp import build_historical_evaluation
from src.market_data import fetch_market_data

EVENTS: list[tuple[str, str]] = [
    ("2015-06-26", "2015 股灾第一波暴跌"),
    ("2018-10-11", "2018 贸易战暴跌传导"),
    ("2020-02-03", "2020 疫情节后千股跌停"),
    ("2022-03-15", "2022 俄乌冲突+疫情大跌"),
    ("2024-02-05", "2024 微盘股踩踏"),
]

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "research_validation"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    service = get_value_hunter_service()
    for iso, label in EVENTS:
        trade_date = date.fromisoformat(iso)
        target = OUT_DIR / f"{iso}.json"
        if target.exists():
            print(f"[skip] {iso} {label}: report already exists")
            continue
        t0 = time.time()
        print(f"[run ] {iso} {label} ...")
        try:
            report = build_historical_evaluation(service, trade_date, fetch_market_data)
            target.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            intel = report.get("market_intelligence", {})
            print(
                f"[ok  ] {iso} seconds={round(time.time() - t0, 1)} "
                f"state={report.get('market_state')} "
                f"intel={intel.get('state')} "
                f"candidates={len(report.get('candidates', []))} "
                f"gaps={len(report.get('data_gaps', []))} "
                f"file={target}"
            )
        except Exception as exc:  # noqa: BLE001 - record any failure honestly
            print(f"[fail] {iso} {label} after {round(time.time() - t0, 1)}s: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
