"""Temporary anti-corruption adapter from the V1 public market-data provider."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
from dataclasses import asdict, dataclass
from datetime import date, datetime
from statistics import median
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection
from ..discovery.models import DiscoveryDisposition, ResearchLead
from ..evidence.context import ContextEvidenceBundle, EvidenceSubjectType
from ..evidence.models import Evidence
from ..market.assessment import MarketSnapshot, MarketStateAssessmentEngine
from ..market.models import MarketState
from ...value_hunter.panic_scan import PanicScanResult, ScannedCandidate


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


@dataclass(frozen=True, slots=True)
class ResearchBinding:
    symbol: str
    asset_id: str
    thesis_version_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.symbol, self.asset_id, self.thesis_version_id)):
            raise ValueError("research binding fields must not be empty")


@dataclass(frozen=True, slots=True)
class ValueHunterDiscoveryFacts:
    symbol: str
    data_date: date
    availability_date: date
    rule_version: str
    watchlist_hash: str
    source: str
    trigger_reasons: tuple[str, ...]
    change_pct: float | None
    relative_to_market: float | None
    relative_to_sector: float | None
    is_limit_down: bool | None
    is_sharp_decline: bool
    data_gaps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryLeadMapping:
    facts: ValueHunterDiscoveryFacts
    lead: ResearchLead | None
    incompatible_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PanicResearchAdapterBundle:
    market_snapshot: MarketSnapshot
    market_state: MarketState
    evidence_bundle: ContextEvidenceBundle
    evidence: tuple[Evidence, ...]
    discovery_leads: tuple[DiscoveryLeadMapping, ...]


class PanicScanResearchAdapter:
    """Map screening facts without upgrading them to investment conclusions."""

    _INCOMPATIBLE_FIELDS = (
        "panic_level_as_investment_decision",
        "relative_strength_as_valuation",
        "sharp_decline_as_mispricing_conclusion",
    )

    def map(
        self,
        scan: PanicScanResult,
        *,
        information_cutoff: datetime,
        bindings: tuple[ResearchBinding, ...] = (),
    ) -> PanicResearchAdapterBundle:
        self._validate_point_in_time(scan, information_cutoff)
        payload = self._payload(scan)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        namespace = (
            f"panic-scan:{scan.source}:{scan.data_date}:{scan.rule_version}:"
            f"{scan.watchlist_hash}:{content_hash}"
        )
        evidence_id = str(uuid5(NAMESPACE_URL, f"evidence:{namespace}"))
        bundle_id = str(uuid5(NAMESPACE_URL, f"bundle:{namespace}"))
        snapshot_id = str(uuid5(NAMESPACE_URL, f"snapshot:{namespace}"))
        market_state_id = str(uuid5(NAMESPACE_URL, f"market-state:{namespace}"))
        data_gaps = self._scan_gaps(scan)

        evidence = Evidence(
            evidence_id=evidence_id,
            provider=f"value-hunter-panic/{scan.source}",
            source_locator=f"provider://{scan.source}/panic-scan/{scan.data_date}",
            title=f"A-share panic screening observations — {scan.data_date}",
            summary=serialized,
            direction=EvidenceDirection.NEUTRAL,
            published_at=scan.scanned_at,
            available_at=scan.scanned_at,
            observed_at=scan.scanned_at,
            content_hash=content_hash,
            quality_warnings=data_gaps,
        )
        context = ContextEvidenceBundle(
            bundle_id,
            EvidenceSubjectType.MARKET,
            "cn-a-share-market",
            scan.scanned_at,
            (evidence_id,),
            scan.scanned_at,
        )
        vh_market = scan.market_snapshot
        snapshot = MarketSnapshot(
            snapshot_id=snapshot_id,
            evidence_set_id=bundle_id,
            as_of=scan.scanned_at,
            broad_index_drawdown=None,
            index_below_long_trend_ratio=None,
            advancer_ratio=vh_market.advance_ratio,
            limit_down_count=vh_market.limit_down,
            median_daily_return=vh_market.median_daily_return,
            turnover_stress_zscore=None,
            data_gaps=tuple(
                dict.fromkeys(
                    (*data_gaps, "broad_index_drawdown", "index_long_trend", "turnover_stress")
                )
            ),
        )
        market_state = MarketStateAssessmentEngine().assess(
            market_state_id,
            snapshot,
            information_cutoff,
        )
        binding_map = {
            alias: binding
            for binding in bindings
            for alias in (binding.symbol, binding.symbol.split(".")[0])
        }
        leads = tuple(
            self._map_candidate(candidate, scan, bundle_id, binding_map, data_gaps)
            for candidate in scan.watchlist
        )
        return PanicResearchAdapterBundle(snapshot, market_state, context, (evidence,), leads)

    @staticmethod
    def _validate_point_in_time(scan: PanicScanResult, information_cutoff: datetime) -> None:
        if information_cutoff.tzinfo is None or information_cutoff.utcoffset() is None:
            raise ValueError("information_cutoff must be timezone-aware")
        if scan.scanned_at.tzinfo is None or scan.scanned_at.utcoffset() is None:
            raise ValueError("scan.scanned_at must be timezone-aware")
        if scan.data_date is None or scan.availability_date is None:
            raise ValueError("scan data_date and availability_date are required")
        if scan.data_date > scan.availability_date:
            raise ValueError("scan availability cannot precede its data date")
        if scan.availability_date > information_cutoff.date() or scan.scanned_at > information_cutoff:
            raise ValueError("future Value Hunter observations cannot enter Investment Research")

    @staticmethod
    def _payload(scan: PanicScanResult) -> dict[str, Any]:
        return {
            "source": scan.source,
            "data_date": scan.data_date.isoformat() if scan.data_date else None,
            "availability_date": scan.availability_date.isoformat() if scan.availability_date else None,
            "rule_version": scan.rule_version,
            "watchlist_hash": scan.watchlist_hash,
            "watchlist_version": scan.watchlist_version,
            "market": {
                "total_stocks": scan.market_snapshot.total_stocks,
                "advance": scan.market_snapshot.advance,
                "decline": scan.market_snapshot.decline,
                "limit_down": scan.market_snapshot.limit_down,
                "median_daily_return": scan.market_snapshot.median_daily_return,
            },
            "upstream_panic_observation": {
                "level": scan.panic.level.value,
                "reasons": list(scan.panic.reasons),
            },
            "candidates": [PanicScanResearchAdapter._candidate_payload(item) for item in scan.watchlist],
        }

    @staticmethod
    def _candidate_payload(candidate: ScannedCandidate) -> dict[str, Any]:
        return {
            "symbol": candidate.symbol,
            "change_pct": candidate.change_pct,
            "relative_to_market": candidate.relative_to_market,
            "relative_to_sector": candidate.relative_to_sector,
            "is_limit_down": candidate.is_limit_down,
            "is_sharp_decline": candidate.is_sharp_decline,
            "data_gap": candidate.data_gap.description,
        }

    @staticmethod
    def _scan_gaps(scan: PanicScanResult) -> tuple[str, ...]:
        gaps = [gap.reason for gap in scan.data_gaps]
        gaps.extend(scan.errors)
        gaps.extend(f"{error.operation}: {error.error_type}" for error in scan.provider_errors)
        if not scan.watchlist_hash:
            gaps.append("watchlist_hash")
        return tuple(dict.fromkeys(gap for gap in gaps if gap))

    def _map_candidate(
        self,
        candidate: ScannedCandidate,
        scan: PanicScanResult,
        evidence_set_id: str,
        binding_map: dict[str, ResearchBinding],
        scan_gaps: tuple[str, ...],
    ) -> DiscoveryLeadMapping:
        assert scan.data_date is not None and scan.availability_date is not None
        candidate_gaps = tuple(
            dict.fromkeys(
                (*scan_gaps, *((candidate.data_gap.description,) if candidate.data_gap.description else ()))
            )
        )
        facts = ValueHunterDiscoveryFacts(
            symbol=candidate.symbol,
            data_date=scan.data_date,
            availability_date=scan.availability_date,
            rule_version=scan.rule_version,
            watchlist_hash=scan.watchlist_hash,
            source=scan.source,
            trigger_reasons=tuple(scan.panic.reasons),
            change_pct=candidate.change_pct,
            relative_to_market=candidate.relative_to_market,
            relative_to_sector=candidate.relative_to_sector,
            is_limit_down=candidate.is_limit_down,
            is_sharp_decline=candidate.is_sharp_decline,
            data_gaps=candidate_gaps,
        )
        binding = binding_map.get(candidate.symbol) or binding_map.get(candidate.symbol.split(".")[0])
        incompatibilities = list(self._INCOMPATIBLE_FIELDS)
        if binding is None:
            incompatibilities.append("missing_asset_or_thesis_binding")
            return DiscoveryLeadMapping(facts, None, tuple(incompatibilities))
        if candidate.close is None or candidate.change_pct is None:
            incompatibilities.append("missing_candidate_market_observation")
            return DiscoveryLeadMapping(facts, None, tuple(incompatibilities))

        reasons = ["Value Hunter screening facts require Investment Research review"]
        reasons.extend(scan.panic.reasons)
        if candidate.is_sharp_decline:
            reasons.append("candidate experienced a sharp decline without a confirmed limit-down state")
        if candidate.relative_to_market is not None:
            reasons.append(f"market-relative return {candidate.relative_to_market:.1%}")
        if candidate.relative_to_sector is not None:
            reasons.append(f"sector-relative return {candidate.relative_to_sector:.1%}")
        missing = tuple(
            dict.fromkeys(
                (*candidate_gaps, "fundamental_integrity_evidence", "counter_evidence", "price_move_attribution")
            )
        )
        lead_key = (
            f"vh-lead:{binding.asset_id}:{binding.thesis_version_id}:"
            f"{scan.data_date}:{scan.rule_version}:{scan.watchlist_hash}:{candidate.symbol}"
        )
        lead = ResearchLead(
            lead_id=str(uuid5(NAMESPACE_URL, lead_key)),
            asset_id=binding.asset_id,
            thesis_version_id=binding.thesis_version_id,
            evidence_set_id=evidence_set_id,
            disposition=DiscoveryDisposition.EVIDENCE_GAP,
            reasons=tuple(reasons),
            missing_evidence=missing,
            first_rejection_question=(
                "What point-in-time evidence proves intact fundamentals and a temporary sell-off cause?"
            ),
            as_of=scan.scanned_at,
        )
        return DiscoveryLeadMapping(facts, lead, tuple(incompatibilities))


def _load_adapter_worker(provider: MarketObservationProvider, observed_at: datetime, queue: Any) -> None:
    try:
        queue.put(("ok", ValueHunterMarketAdapter(provider).load(observed_at)))
    except Exception as exc:
        queue.put(("error", (type(exc).__name__, str(exc))))
