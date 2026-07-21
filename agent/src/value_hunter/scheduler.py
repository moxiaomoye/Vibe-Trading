"""Small daily scheduler with no extra dependency."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .service import ValueHunterService

logger = logging.getLogger(__name__)


class ValueHunterScheduler:
    def __init__(self, service: ValueHunterService):
        self.service = service
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._loop(), name="value-hunter-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def seconds_until_next_run(self, now: datetime | None = None) -> float:
        try:
            tz = ZoneInfo(self.service.config.timezone)
        except ZoneInfoNotFoundError:
            if self.service.config.timezone != "Asia/Shanghai":
                raise
            # Windows Python distributions may omit the optional tzdata wheel.
            # China has used UTC+8 without DST since 1991, so this fallback is
            # deterministic for the monitor's supported schedule.
            tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
        current = now.astimezone(tz) if now else datetime.now(tz)
        hour, minute = (int(part) for part in self.service.config.schedule.split(":", 1))
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current:
            target += timedelta(days=1)
        return max(0.0, (target - current).total_seconds())

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.seconds_until_next_run())
                continue
            except asyncio.TimeoutError:
                pass
            try:
                await asyncio.to_thread(self.service.run, notify=True)
            except Exception:
                logger.exception("Value Hunter scheduled scan failed")
