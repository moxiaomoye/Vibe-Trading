"""Environment-backed configuration for Value Hunter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config.accessor import get_env_bool, get_env_value
from src.config.paths import get_runtime_root


def _bool(name: str, default: bool = False) -> bool:
    return get_env_bool(name, default)


def _float(name: str, default: float) -> float:
    try:
        return float(get_env_value(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(get_env_value(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class ValueHunterConfig:
    enabled: bool
    provider: str
    schedule: str
    timezone: str
    market_alert_score: float
    candidate_alert_score: float
    max_candidates: int
    database_path: Path
    watchlist_path: Path | None
    feishu_webhook_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    email_to: str
    notify_on_demo: bool

    @classmethod
    def from_env(cls) -> "ValueHunterConfig":
        root = get_runtime_root() / "value-hunter"
        db_value = get_env_value("VALUE_HUNTER_DB_PATH").strip()
        watchlist = get_env_value("VALUE_HUNTER_WATCHLIST_PATH").strip()
        return cls(
            enabled=_bool("VALUE_HUNTER_ENABLED"),
            provider=get_env_value("VALUE_HUNTER_PROVIDER", "akshare").strip().lower(),
            schedule=get_env_value("VALUE_HUNTER_SCHEDULE", "18:10").strip(),
            timezone=get_env_value("VALUE_HUNTER_TIMEZONE", "Asia/Shanghai").strip(),
            market_alert_score=_float("VALUE_HUNTER_MARKET_ALERT_SCORE", 70.0),
            candidate_alert_score=_float("VALUE_HUNTER_CANDIDATE_ALERT_SCORE", 75.0),
            max_candidates=max(1, _int("VALUE_HUNTER_MAX_CANDIDATES", 5)),
            database_path=Path(db_value) if db_value else root / "value_hunter.sqlite3",
            watchlist_path=Path(watchlist) if watchlist else None,
            feishu_webhook_url=get_env_value("VALUE_HUNTER_FEISHU_WEBHOOK").strip(),
            smtp_host=get_env_value("VALUE_HUNTER_SMTP_HOST").strip(),
            smtp_port=_int("VALUE_HUNTER_SMTP_PORT", 465),
            smtp_username=get_env_value("VALUE_HUNTER_SMTP_USERNAME").strip(),
            smtp_password=get_env_value("VALUE_HUNTER_SMTP_PASSWORD").strip(),
            smtp_from=get_env_value("VALUE_HUNTER_SMTP_FROM").strip(),
            email_to=get_env_value("VALUE_HUNTER_EMAIL_TO").strip(),
            notify_on_demo=_bool("VALUE_HUNTER_NOTIFY_ON_DEMO"),
        )
