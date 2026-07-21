"""Value Hunter orchestration service."""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone

from .config import ValueHunterConfig
from .models import ScanResult
from .notifier import NotificationSender
from .providers import ValueHunterProvider, build_provider
from .scoring import score_candidate, score_market
from .store import ValueHunterStore


class ValueHunterService:
    def __init__(
        self,
        config: ValueHunterConfig | None = None,
        provider: ValueHunterProvider | None = None,
        store: ValueHunterStore | None = None,
        notifier: NotificationSender | None = None,
    ):
        self.config = config or ValueHunterConfig.from_env()
        self.provider = provider or build_provider(
            self.config.provider,
            self.config.watchlist_path,
            self.config.database_path.parent / "cache",
        )
        self.store = store or ValueHunterStore(self.config.database_path)
        self.notifier = notifier or NotificationSender(self.config)
        self._lock = threading.Lock()

    def run(self, *, notify: bool = True) -> ScanResult:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Value Hunter扫描正在运行")
        try:
            started = datetime.now(timezone.utc).isoformat()
            market = score_market(self.provider.load_market())
            scored = [score_candidate(item) for item in self.provider.load_candidates()]
            eligible = [
                item for item in scored
                if item.status in {"A - 深入研究", "B - 观察名单"}
                and not item.missing_fields
                and item.score.total >= self.config.candidate_alert_score
            ]
            eligible.sort(key=lambda item: item.score.total, reverse=True)
            selected = eligible[: self.config.max_candidates]
            required = market.score >= self.config.market_alert_score and bool(selected)
            reason = (
                f"市场{market.score:.1f}分且{len(selected)}家公司达到研究门槛"
                if required else "市场或候选未同时达到通知门槛"
            )
            result = ScanResult(
                run_id=str(uuid.uuid4()), started_at=started,
                completed_at=datetime.now(timezone.utc).isoformat(),
                mode=self.provider.name, market=market, candidates=selected,
                notification_required=required, notification_reason=reason,
            )
            payload = result.to_dict()
            self.store.save_scan(payload)

            should_notify = required and notify and (self.provider.name != "demo" or self.config.notify_on_demo)
            if should_notify:
                fingerprint = self._fingerprint(result)
                if not self.store.notification_seen(fingerprint):
                    channels = self.notifier.send(result)
                    result.errors.extend(self.notifier.last_errors)
                    if channels:
                        self.store.mark_notification(fingerprint, result.completed_at, channels)
                    if self.notifier.last_errors:
                        self.store.save_scan(result.to_dict())
            return result
        finally:
            self._lock.release()

    @staticmethod
    def _fingerprint(result: ScanResult) -> str:
        state = {
            "as_of": result.market.observation.as_of,
            "level": result.market.level,
            "symbols": [item.observation.symbol for item in result.candidates],
        }
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()

    def status(self) -> dict:
        channels = self.notifier.configured_channels()
        missing_notification_settings: list[str] = []
        if "feishu" not in channels:
            missing_notification_settings.append("VALUE_HUNTER_FEISHU_WEBHOOK")
        if "email" not in channels:
            missing_notification_settings.extend([
                "VALUE_HUNTER_SMTP_HOST",
                "VALUE_HUNTER_EMAIL_TO",
            ])
        return {
            "enabled": self.config.enabled,
            "provider": self.provider.name,
            "schedule": self.config.schedule,
            "timezone": self.config.timezone,
            "notification_channels": channels,
            "notification_ready": bool(channels),
            "missing_notification_settings": missing_notification_settings,
            "latest": self.store.latest(),
        }

    def history(self, limit: int = 30) -> list[dict]:
        return self.store.history(limit)
