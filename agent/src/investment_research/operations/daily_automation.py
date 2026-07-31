"""Small opt-in scheduler for the read-only daily research workflow."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scheduling import TradingDaySchedule


logger = logging.getLogger(__name__)
RunCallback = Callable[[datetime], Awaitable[dict[str, Any]]]


class DailyOpportunityAutomation:
    """Run at most once per exchange date and preserve failure isolation."""

    def __init__(
        self,
        callback: RunCallback,
        state_path: Path,
        *,
        schedule: TradingDaySchedule,
        poll_seconds: float = 60.0,
        enabled: bool = False,
    ) -> None:
        self.callback = callback
        self.state_path = state_path
        self.schedule = schedule
        self.poll_seconds = poll_seconds
        self.enabled = enabled
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(
            self._loop(),
            name="investment-research-daily-automation",
        )

    async def stop(self) -> None:
        self._stopping = True
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def tick(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        state = self.status()
        if not self.enabled:
            return {**state, "tick": "disabled"}
        if not self.schedule.is_due(current):
            return {**state, "tick": "not_due"}
        trade_date = self.schedule.local_now(current).date().isoformat()
        if state.get("last_completed_trade_date") == trade_date:
            return {**state, "tick": "already_completed"}
        try:
            result = await self.callback(current)
        except Exception as exc:
            failed = {
                **state,
                "enabled": True,
                "last_attempted_trade_date": trade_date,
                "last_status": "failed",
                "last_error": type(exc).__name__,
                "updated_at": current.isoformat(),
            }
            self._save(failed)
            logger.exception("daily investment research automation failed")
            return {**failed, "tick": "failed"}
        completed = {
            **state,
            "enabled": True,
            "last_attempted_trade_date": trade_date,
            "last_completed_trade_date": trade_date,
            "last_status": "completed",
            "last_error": None,
            "last_result": result,
            "updated_at": current.isoformat(),
        }
        self._save(completed)
        return {**completed, "tick": "completed"}

    def status(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                value = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    value["enabled"] = self.enabled
                    value["running"] = self._task is not None and not self._task.done()
                    return value
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "enabled": self.enabled,
            "running": self._task is not None and not self._task.done(),
            "last_attempted_trade_date": None,
            "last_completed_trade_date": None,
            "last_status": "never_run",
            "last_error": None,
            "last_result": None,
            "updated_at": None,
        }

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("daily automation tick boundary failed")
            await asyncio.sleep(self.poll_seconds)

    def _save(self, value: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f".{self.state_path.name}.tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
