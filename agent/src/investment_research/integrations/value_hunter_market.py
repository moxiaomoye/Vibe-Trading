"""Temporary anti-corruption adapter from the V1 public market-data provider."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import median
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection
from ..evidence.context import ContextEvidenceBundle, EvidenceSubjectType
from ..evidence.models import Evidence
from ..market.assessment import MarketSnapshot


class MarketObservationProvider(Protocol):
    name: str

    def load_market(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class MarketObservationAdapterBundle:
    snapshot: MarketSnapshot
    evidence_bundle: ContextEvidenceBundle
    evidence: tuple[Evidence, ...]


class ValueHunterMarketAdapter:
    """Translate observable V1 data only; V1 scores and candidate labels are deliberately ignored."""

    def __init__(self, provider: MarketObservationProvider):
        self.provider = provider

    def load(self, observed_at: datetime) -> MarketObservationAdapterBundle:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        market = self.provider.load_market()
        indices = tuple(market.indices)
        raw_payload = asdict(market)
        serialized = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        evidence_id = str(uuid5(NAMESPACE_URL, f"market-evidence:{self.provider.name}:{content_hash}"))
        bundle_id = str(uuid5(NAMESPACE_URL, f"market-bundle:{self.provider.name}:{content_hash}"))
        snapshot_id = str(uuid5(NAMESPACE_URL, f"market-snapshot:{self.provider.name}:{content_hash}"))
        evidence = Evidence(
            evidence_id=evidence_id,
            provider=f"value-hunter-adapter/{self.provider.name}",
            source_locator=f"provider://{self.provider.name}/market/{market.as_of}",
            title=f"CN equity market observations — {market.as_of}",
            summary=serialized,
            direction=EvidenceDirection.NEUTRAL,
            published_at=observed_at,
            available_at=observed_at,
            observed_at=observed_at,
            content_hash=content_hash,
            quality_warnings=tuple(market.warnings),
        )
        context = ContextEvidenceBundle(
            bundle_id, EvidenceSubjectType.MARKET, "cn-equity-market", observed_at,
            (evidence_id,), observed_at,
        )
        gaps = list(market.warnings)
        field_values = {
            "advancer_ratio": market.advancer_ratio,
            "limit_down_count": market.limit_down_count,
            "turnover_stress_zscore": market.turnover_zscore,
        }
        gaps.extend(name for name, value in field_values.items() if value is None)
        snapshot = MarketSnapshot(
            snapshot_id=snapshot_id,
            evidence_set_id=bundle_id,
            as_of=observed_at,
            broad_index_drawdown=self._median_percent(indices, "drawdown_252_pct"),
            index_below_long_trend_ratio=(sum(item.below_ma250 for item in indices) / len(indices)) if indices else None,
            advancer_ratio=market.advancer_ratio,
            limit_down_count=market.limit_down_count,
            median_daily_return=self._median_percent(indices, "daily_return_pct"),
            turnover_stress_zscore=market.turnover_zscore,
            data_gaps=tuple(dict.fromkeys(gaps)),
        )
        return MarketObservationAdapterBundle(snapshot, context, (evidence,))

    def load_with_timeout(
        self, observed_at: datetime, timeout_seconds: float = 90.0
    ) -> MarketObservationAdapterBundle:
        """Isolate an unstable public provider so a hung request cannot block the daily pipeline."""
        if timeout_seconds <= 0:
            raise ValueError("provider timeout must be positive")
        context = multiprocessing.get_context("spawn")
        queue = context.Queue(maxsize=1)
        process = context.Process(
            target=_load_adapter_worker,
            args=(self.provider, observed_at, queue),
            daemon=True,
            name=f"research-market-{self.provider.name}",
        )
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise TimeoutError(f"market provider {self.provider.name} exceeded {timeout_seconds:g} seconds")
        if queue.empty():
            raise RuntimeError(f"market provider {self.provider.name} exited without a result")
        status, payload = queue.get()
        if status == "error":
            error_type, message = payload
            raise RuntimeError(f"market provider {self.provider.name} failed: {error_type}: {message}")
        return payload

    @staticmethod
    def _median_percent(indices: tuple[Any, ...], field: str) -> float | None:
        values = [float(getattr(item, field)) / 100 for item in indices]
        return median(values) if values else None


def _load_adapter_worker(provider: MarketObservationProvider, observed_at: datetime, queue: Any) -> None:
    try:
        queue.put(("ok", ValueHunterMarketAdapter(provider).load(observed_at)))
    except Exception as exc:
        queue.put(("error", (type(exc).__name__, str(exc))))
