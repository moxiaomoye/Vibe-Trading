"""Reliability policy for per-symbol public endpoints (RRV-RELIABILITY-CLOSURE-001).

Shared, injectable call strategy for endpoints such as ``stock_value_em`` and
``stock_financial_analysis_indicator``: bounded attempts, exponential backoff,
per-endpoint minimum interval, run-level circuit breaker, health accounting,
and a point-in-time-safe success cache. Never retries non-transient errors and
never stores secrets, tokens, cookies, or full request headers.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

CACHE_SCHEMA_VERSION = "pit-cache-v1"
HEALTH_SUMMARY_LIMIT = 200

_RETRYABLE_ERROR_NAMES = {
    "RemoteDisconnected",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "BrokenPipeError",
    "TimeoutError",
    "ConnectTimeout",
    "ReadTimeout",
    "ChunkedEncodingError",
    "IncompleteRead",
    "ProtocolError",
    "ProxyError",
    "SSLError",
    "ConnectionRefusedError",
    "OSError",
}

_NON_RETRYABLE_SENTINELS = ("KeyError", "SchemaError", "ValueError", "TypeError")


def is_retryable_error(exc: BaseException) -> bool:
    """True only for errors that may transiently recover.

    Retryable: connection resets / disconnects, timeouts, TLS resets,
    HTTP 429, HTTP 5xx. Never retried: missing fields, schema changes,
    parse errors, invalid dates, explicit 4xx business rejections.
    """
    name = type(exc).__name__
    if name in _RETRYABLE_ERROR_NAMES:
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int):
        if status == 429 or 500 <= status < 600:
            return True
        return False
    if name in _NON_RETRYABLE_SENTINELS:
        return False
    return False


def classify_error_summary(exc: BaseException) -> tuple[str, str]:
    """Return (error_type, truncated_error_summary) with no sensitive payloads."""
    summary = str(exc).strip()
    if len(summary) > HEALTH_SUMMARY_LIMIT:
        summary = summary[:HEALTH_SUMMARY_LIMIT] + "..."
    return type(exc).__name__, summary


def _frame_to_json_safe(frame: Any) -> dict[str, Any]:
    """Convert a pandas DataFrame to a JSON-safe dict (orient='split')."""
    if hasattr(frame, "to_json"):
        return {"kind": "pandas-split", "payload": frame.to_json(orient="split")}
    raise TypeError(f"cannot cache response of type {type(frame).__name__}")


def _frame_from_json_safe(value: dict[str, Any]) -> Any:
    import pandas as pd

    if value.get("kind") == "pandas-split":
        return pd.read_json(value["payload"], orient="split")
    raise ValueError("unknown cached response kind")


@dataclass
class EndpointHealth:
    """Aggregated health of one endpoint for the current provider run."""

    endpoint: str
    provider: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    circuit_open: bool = False
    last_error_type: str | None = None
    last_error_summary: str | None = None
    cache_hits: int = 0
    cache_original_as_of: str | None = None

    @property
    def state(self) -> str:
        if self.attempts == 0:
            return "NOT_USED"
        if self.circuit_open:
            return "DEGRADED"
        if self.failures > 0 and self.successes == 0:
            return "UNAVAILABLE"
        return "HEALTHY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "provider": self.provider,
            "attempts": self.attempts,
            "successes": self.successes,
            "failures": self.failures,
            "state": self.state,
            "last_error_type": self.last_error_type,
            "last_error_summary": self.last_error_summary,
            "cooldown_triggered": self.circuit_open,
            "cache_hits": self.cache_hits,
            "cache_original_as_of": self.cache_original_as_of,
        }


class PitEndpointCache:
    """Point-in-time-safe success cache for per-symbol endpoint responses.

    Keys include provider, endpoint, symbol, requested_as_of and schema
    versions. Only successful raw responses are cached; the normalized
    (PIT-filtered) view is stored separately in the same entry so raw and
    normalized never mix. Corrupt entries are invalidated explicitly.
    """

    def __init__(self, cache_dir: Path | None, provider_version: str = "akshare"):
        self.cache_dir = cache_dir
        self.provider_version = provider_version
        self._invalidated: list[str] = []

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get(
        self,
        endpoint: str,
        symbol: str,
        requested_as_of: date,
        schema_version: str = CACHE_SCHEMA_VERSION,
    ) -> tuple[Any, str] | None:
        """Return (raw_response, original_requested_as_of) or None on miss."""
        if self.cache_dir is None:
            return None
        path = self._path(self._key(endpoint, symbol, requested_as_of, schema_version))
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry.get("schema_version") != schema_version:
                return None
            raw = _frame_from_json_safe(entry["raw"])
            return raw, entry["requested_as_of"]
        except (ValueError, KeyError, TypeError, OSError):
            self._invalidated.append(path.name)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def put(
        self,
        endpoint: str,
        symbol: str,
        requested_as_of: date,
        raw: Any,
        normalized: Any,
        schema_version: str = CACHE_SCHEMA_VERSION,
    ) -> None:
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            entry = {
                "schema_version": schema_version,
                "provider_version": self.provider_version,
                "endpoint": endpoint,
                "symbol": symbol,
                "requested_as_of": requested_as_of.isoformat(),
                "captured_at": time.time(),
                "raw": _frame_to_json_safe(raw),
                "normalized": _frame_to_json_safe(normalized),
            }
            path = self._path(self._key(endpoint, symbol, requested_as_of, schema_version))
            path.write_text(json.dumps(entry), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            return

    def invalidated_entries(self) -> list[str]:
        return list(self._invalidated)

    def _key(
        self,
        endpoint: str,
        symbol: str,
        requested_as_of: date,
        schema_version: str,
    ) -> str:
        return "|".join([
            self.provider_version,
            endpoint,
            symbol,
            requested_as_of.isoformat(),
            schema_version,
        ])


class EndpointDegradedError(RuntimeError):
    """Raised when the run-level circuit breaker is open for an endpoint."""


class PublicEndpointPolicy:
    """Per-endpoint retry/backoff/throttle/breaker policy (injectable)."""

    def __init__(
        self,
        endpoint: str,
        *,
        provider: str = "akshare",
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 8.0,
        endpoint_min_interval: float = 0.0,
        consecutive_failure_threshold: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        cache: PitEndpointCache | None = None,
    ):
        self.endpoint = endpoint
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, int(max_attempts))
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.endpoint_min_interval = endpoint_min_interval
        self.consecutive_failure_threshold = max(1, int(consecutive_failure_threshold))
        self._sleep = sleep
        self._clock = clock
        self._cache = cache
        self.health = EndpointHealth(endpoint=endpoint, provider=provider)
        self._consecutive_failures = 0
        self._last_call_at: float | None = None

    def call(
        self,
        symbol: str,
        fn: Callable[[], Any],
        *,
        requested_as_of: date | None = None,
        cache_schema_version: str = CACHE_SCHEMA_VERSION,
        cache_normalize: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Execute ``fn`` with retry/backoff/breaker; cache success when enabled."""
        if self.health.circuit_open:
            raise EndpointDegradedError(
                f"endpoint {self.endpoint} DEGRADED this run after "
                f"{self.health.failures} consecutive failures"
            )
        if requested_as_of is not None and self._cache is not None:
            cached = self._cache.get(
                self.endpoint, symbol, requested_as_of, cache_schema_version
            )
            if cached is not None:
                raw, original_as_of = cached
                self.health.cache_hits += 1
                self.health.cache_original_as_of = original_as_of
                return raw

        if self._last_call_at is not None:
            elapsed = self._clock() - self._last_call_at
            if elapsed < self.endpoint_min_interval:
                self._sleep(self.endpoint_min_interval - elapsed)

        last_error: BaseException | None = None
        for attempt in range(self.max_attempts):
            self.health.attempts += 1
            try:
                result = self._execute(fn)
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = exc
                self.health.failures += 1
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.consecutive_failure_threshold:
                    self.health.circuit_open = True
                    self.health.last_error_type, self.health.last_error_summary = (
                        classify_error_summary(exc)
                    )
                    raise
                if is_retryable_error(exc) and attempt + 1 < self.max_attempts:
                    backoff = min(
                        self.max_backoff, self.initial_backoff * (2.0 ** attempt)
                    )
                    self._sleep(backoff)
                    continue
                self.health.last_error_type, self.health.last_error_summary = (
                    classify_error_summary(exc)
                )
                raise
            self.health.successes += 1
            self._consecutive_failures = 0
            self._last_call_at = self._clock()
            if requested_as_of is not None and self._cache is not None:
                normalized = (
                    cache_normalize(result)
                    if cache_normalize is not None
                    else result
                )
                self._cache.put(
                    self.endpoint, symbol, requested_as_of, result, normalized,
                    cache_schema_version,
                )
            return result
        raise last_error  # pragma: no cover - loop always returns or raises

    def _execute(self, fn: Callable[[], Any]) -> Any:
        from src.value_hunter.providers import _call_with_timeout

        return _call_with_timeout(fn, self.timeout_seconds)

    def health_entry(self) -> dict[str, Any]:
        return self.health.to_dict()
