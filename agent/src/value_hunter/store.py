"""SQLite persistence for scan snapshots and notification deduplication."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class ValueHunterStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS scans (
                    run_id TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL,
                    market_score REAL NOT NULL,
                    market_level TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    notification_required INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS notifications (
                    fingerprint TEXT PRIMARY KEY,
                    sent_at TEXT NOT NULL,
                    channels_json TEXT NOT NULL
                )"""
            )

    def save_scan(self, payload: dict[str, Any]) -> None:
        market = payload["market"]
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO scans
                (run_id, completed_at, market_score, market_level, provider,
                 notification_required, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["run_id"], payload["completed_at"], market["score"],
                    market["level"], payload["mode"],
                    int(payload["notification_required"]),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def latest(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM scans ORDER BY completed_at DESC LIMIT 1").fetchone()
        return json.loads(row["payload_json"]) if row else None

    def history(self, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM scans ORDER BY completed_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def notification_seen(self, fingerprint: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM notifications WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return row is not None

    def mark_notification(self, fingerprint: str, sent_at: str, channels: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO notifications (fingerprint, sent_at, channels_json) VALUES (?, ?, ?)",
                (fingerprint, sent_at, json.dumps(channels, ensure_ascii=False)),
            )
