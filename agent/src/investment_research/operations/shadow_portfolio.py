"""Persistent, read-only shadow portfolio for research-candidate evaluation.

The tracker never calls broker, order, mandate, or notification code.  A
post-close signal becomes a pending intent and can only be filled from a later
trade-date report, which prevents same-close look-ahead.  Positions are closed
after 20 distinct observed trading dates so the result remains comparable with
the existing T+20 evaluation workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


SHADOW_SCHEMA_VERSION = "1.0"
DEFAULT_INITIAL_CASH = 70_000.0
DEFAULT_POSITION_FRACTION = 0.05
DEFAULT_HORIZON = 20
QUALIFYING_LEVELS = {"prepare", "action_candidate"}


@dataclass(slots=True)
class ShadowPortfolioTracker:
    path: Path
    initial_cash: float = DEFAULT_INITIAL_CASH
    position_fraction: float = DEFAULT_POSITION_FRACTION
    horizon: int = DEFAULT_HORIZON

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.initial_cash <= 0 or not 0 < self.position_fraction <= 1:
            raise ValueError("shadow capital and position fraction must be positive")
        if self.horizon < 1:
            raise ValueError("shadow evaluation horizon must be positive")

    def status(self) -> dict[str, Any]:
        return self._load()

    def process(self, report: dict[str, Any]) -> dict[str, Any]:
        state = self._load()
        fingerprint = str(report.get("_fingerprint") or "")
        if fingerprint and state.get("last_report_fingerprint") == fingerprint:
            return state

        report_date = str(report.get("report_date") or "")
        assets = {
            str(item.get("symbol")): item
            for item in report.get("assets", [])
            if isinstance(item, dict) and item.get("symbol")
        }
        if not report_date:
            raise ValueError("shadow processing requires report_date")

        self._fill_pending(state, assets, report_date)
        self._mark_positions(state, assets, report_date)
        self._create_intents(state, report, assets, report_date)
        self._append_snapshot(state, assets, report_date)
        state["last_report_fingerprint"] = fingerprint or None
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(state)
        return state

    def _fill_pending(
        self,
        state: dict[str, Any],
        assets: dict[str, dict[str, Any]],
        report_date: str,
    ) -> None:
        remaining: list[dict[str, Any]] = []
        open_symbols = {item["symbol"] for item in state["open_positions"]}
        for intent in state["pending_intents"]:
            asset = assets.get(intent["symbol"])
            effective_date = str((asset or {}).get("effective_trade_date") or "")
            price = _positive_number((asset or {}).get("latest_close"))
            if (
                not asset
                or not effective_date
                or effective_date <= intent["signal_trade_date"]
                or price is None
                or intent["symbol"] in open_symbols
            ):
                remaining.append(intent)
                continue
            notional = min(
                self.initial_cash * self.position_fraction,
                float(state["cash"]),
            )
            if notional <= 0:
                remaining.append(intent)
                continue
            units = notional / price
            position_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"shadow:{intent['symbol']}:{intent['signal_trade_date']}:{effective_date}",
                )
            )
            state["open_positions"].append(
                {
                    "position_id": position_id,
                    "symbol": intent["symbol"],
                    "name": intent["name"],
                    "signal_trade_date": intent["signal_trade_date"],
                    "entry_trade_date": effective_date,
                    "entry_price": round(price, 6),
                    "units": round(units, 8),
                    "notional": round(notional, 2),
                    "last_price": round(price, 6),
                    "market_value": round(notional, 2),
                    "pnl": 0.0,
                    "return_pct": 0.0,
                    "observed_sessions": 0,
                    "last_observed_trade_date": effective_date,
                    "horizon": self.horizon,
                    "status": "open",
                    "action_level_at_signal": intent["action_level"],
                    "rationale": intent["rationale"],
                    "data_quality": intent["data_quality"],
                }
            )
            state["cash"] = round(float(state["cash"]) - notional, 2)
            open_symbols.add(intent["symbol"])
        state["pending_intents"] = remaining

    def _mark_positions(
        self,
        state: dict[str, Any],
        assets: dict[str, dict[str, Any]],
        report_date: str,
    ) -> None:
        still_open: list[dict[str, Any]] = []
        for position in state["open_positions"]:
            asset = assets.get(position["symbol"])
            effective_date = str((asset or {}).get("effective_trade_date") or "")
            price = _positive_number((asset or {}).get("latest_close"))
            if price is not None:
                position["last_price"] = round(price, 6)
                position["market_value"] = round(price * float(position["units"]), 2)
                position["pnl"] = round(
                    float(position["market_value"]) - float(position["notional"]), 2
                )
                position["return_pct"] = round(
                    (price / float(position["entry_price"]) - 1.0) * 100.0, 2
                )
            if (
                effective_date
                and effective_date > position["last_observed_trade_date"]
            ):
                position["observed_sessions"] += 1
                position["last_observed_trade_date"] = effective_date
            if position["observed_sessions"] < position["horizon"]:
                still_open.append(position)
                continue
            position["status"] = "closed_t20"
            position["exit_trade_date"] = effective_date or report_date
            position["exit_price"] = position["last_price"]
            state["cash"] = round(
                float(state["cash"]) + float(position["market_value"]), 2
            )
            state["closed_positions"].append(position)
        state["open_positions"] = still_open

    def _create_intents(
        self,
        state: dict[str, Any],
        report: dict[str, Any],
        assets: dict[str, dict[str, Any]],
        report_date: str,
    ) -> None:
        if not bool((report.get("market") or {}).get("panic")):
            return
        occupied = {
            item["symbol"]
            for item in [*state["pending_intents"], *state["open_positions"]]
        }
        for symbol, asset in assets.items():
            if symbol in occupied or asset.get("action_level") not in QUALIFYING_LEVELS:
                continue
            support = asset.get("supporting_evidence")
            counter = asset.get("counter_evidence")
            if not isinstance(support, list) or not support:
                continue
            if not isinstance(counter, list):
                continue
            state["pending_intents"].append(
                {
                    "intent_id": str(
                        uuid5(NAMESPACE_URL, f"shadow-intent:{symbol}:{report_date}")
                    ),
                    "symbol": symbol,
                    "name": str(asset.get("name") or symbol),
                    "signal_trade_date": str(
                        asset.get("effective_trade_date") or report_date
                    ),
                    "action_level": str(asset.get("action_level")),
                    "rationale": [str(item) for item in support[:5]],
                    "counter_evidence": [str(item) for item in counter[:5]],
                    "data_quality": str(asset.get("data_quality") or "unknown"),
                    "status": "pending_next_trade_date",
                }
            )

    def _append_snapshot(
        self,
        state: dict[str, Any],
        assets: dict[str, dict[str, Any]],
        report_date: str,
    ) -> None:
        market_value = round(
            sum(float(item["market_value"]) for item in state["open_positions"]), 2
        )
        equity = round(float(state["cash"]) + market_value, 2)
        snapshot = {
            "report_date": report_date,
            "cash": state["cash"],
            "market_value": market_value,
            "equity": equity,
            "total_return_pct": round(
                (equity / float(state["initial_cash"]) - 1.0) * 100.0, 2
            ),
            "open_position_count": len(state["open_positions"]),
            "pending_intent_count": len(state["pending_intents"]),
            "prices": {
                symbol: asset.get("latest_close")
                for symbol, asset in assets.items()
            },
        }
        existing = [
            item
            for item in state["daily_snapshots"]
            if item.get("report_date") != report_date
        ]
        state["daily_snapshots"] = [*existing, snapshot][-260:]

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "schema_version": SHADOW_SCHEMA_VERSION,
            "mode": "shadow_only",
            "initial_cash": round(self.initial_cash, 2),
            "cash": round(self.initial_cash, 2),
            "position_fraction": self.position_fraction,
            "horizon": self.horizon,
            "pending_intents": [],
            "open_positions": [],
            "closed_positions": [],
            "daily_snapshots": [],
            "last_report_fingerprint": None,
            "updated_at": None,
            "trading_executed": False,
        }

    def _save(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _positive_number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
