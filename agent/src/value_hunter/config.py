"""Environment-backed configuration for Value Hunter."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.config.paths import get_runtime_root


@dataclass(frozen=True, slots=True)
class PanicValueMethodConfig:
    index_daily_return_pct: float = -2.0
    max_advancer_ratio: float = 0.35
    min_limit_down_count: int = 20
    min_roe_pct: float = -100.0
    max_pe: float = 10000.0
    max_daily_decline_pct: float = 100.0
    min_market_cap_billion: float = 0.0
    mispricing_weight: float = 30.0
    quality_weight: float = 30.0
    valuation_weight: float = 20.0
    relative_strength_weight: float = 10.0
    catalyst_weight: float = 10.0

    def __post_init__(self) -> None:
        weights = (
            self.mispricing_weight, self.quality_weight, self.valuation_weight,
            self.relative_strength_weight, self.catalyst_weight,
        )
        if any(weight < 0 for weight in weights) or abs(sum(weights) - 100.0) > 1e-6:
            raise ValueError("Panic Value Hunter score weights must be non-negative and sum to 100")
        if not 0 <= self.max_advancer_ratio <= 1:
            raise ValueError("market_panic.max_advancer_ratio must be between 0 and 1")


def load_panic_value_config(path: Path | None = None) -> PanicValueMethodConfig:
    config_path = path or Path(os.getenv("PANIC_VALUE_CONFIG_PATH", "").strip() or (
        Path(__file__).resolve().parents[3] / "config" / "panic_value_config.yaml"
    ))
    if not config_path.exists():
        return PanicValueMethodConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    panic = raw.get("market_panic", {})
    filters = raw.get("stock_filters", {})
    weights = raw.get("score_weights", {})
    return PanicValueMethodConfig(
        index_daily_return_pct=float(panic.get("index_daily_return_pct", -2.0)),
        max_advancer_ratio=float(panic.get("max_advancer_ratio", 0.35)),
        min_limit_down_count=int(panic.get("min_limit_down_count", 20)),
        min_roe_pct=float(filters.get("min_roe_pct", -100.0)),
        max_pe=float(filters.get("max_pe", 10000.0)),
        max_daily_decline_pct=float(filters.get("max_daily_decline_pct", 100.0)),
        min_market_cap_billion=float(filters.get("min_market_cap_billion", 0.0)),
        mispricing_weight=float(weights.get("mispricing", 30.0)),
        quality_weight=float(weights.get("quality", 30.0)),
        valuation_weight=float(weights.get("valuation", 20.0)),
        relative_strength_weight=float(weights.get("relative_strength", 10.0)),
        catalyst_weight=float(weights.get("catalyst", 10.0)),
    )


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
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
    method: PanicValueMethodConfig = field(default_factory=PanicValueMethodConfig)

    @classmethod
    def from_env(cls) -> "ValueHunterConfig":
        root = get_runtime_root() / "value-hunter"
        db_value = os.getenv("VALUE_HUNTER_DB_PATH", "").strip()
        watchlist = os.getenv("VALUE_HUNTER_WATCHLIST_PATH", "").strip()
        default_watchlist = Path(__file__).resolve().parents[3] / "config" / "watchlist.yaml"
        return cls(
            enabled=_bool("VALUE_HUNTER_ENABLED"),
            provider=os.getenv("VALUE_HUNTER_PROVIDER", "akshare").strip().lower(),
            schedule=os.getenv("VALUE_HUNTER_SCHEDULE", "18:10").strip(),
            timezone=os.getenv("VALUE_HUNTER_TIMEZONE", "Asia/Shanghai").strip(),
            market_alert_score=_float("VALUE_HUNTER_MARKET_ALERT_SCORE", 70.0),
            candidate_alert_score=_float("VALUE_HUNTER_CANDIDATE_ALERT_SCORE", 75.0),
            max_candidates=max(1, _int("VALUE_HUNTER_MAX_CANDIDATES", 5)),
            database_path=Path(db_value) if db_value else root / "value_hunter.sqlite3",
            watchlist_path=(
                Path(watchlist) if watchlist
                else default_watchlist if default_watchlist.exists()
                else None
            ),
            feishu_webhook_url=os.getenv("VALUE_HUNTER_FEISHU_WEBHOOK", "").strip(),
            smtp_host=os.getenv("VALUE_HUNTER_SMTP_HOST", "").strip(),
            smtp_port=_int("VALUE_HUNTER_SMTP_PORT", 465),
            smtp_username=os.getenv("VALUE_HUNTER_SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("VALUE_HUNTER_SMTP_PASSWORD", "").strip(),
            smtp_from=os.getenv("VALUE_HUNTER_SMTP_FROM", "").strip(),
            email_to=os.getenv("VALUE_HUNTER_EMAIL_TO", "").strip(),
            notify_on_demo=_bool("VALUE_HUNTER_NOTIFY_ON_DEMO"),
            method=load_panic_value_config(),
        )
