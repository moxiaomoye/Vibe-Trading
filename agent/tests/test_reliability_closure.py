"""Work-package tests: provider policy, eligibility, contract, signals, reconciliation."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.value_hunter.provider_policy import (
    CACHE_SCHEMA_VERSION,
    EndpointDegradedError,
    PitEndpointCache,
    PublicEndpointPolicy,
    is_retryable_error,
)
from src.value_hunter.models import CandidateObservation, CandidateResult, ScoreBreakdown
from src.investment_research.models.eligibility import (
    EligibilityStatus,
    listing_date_from_value,
    resolve_eligibility,
)
from src.investment_research.models.candidate_contract import build_candidate_payload
from src.investment_research.models.market_intelligence import (
    MarketDimension,
    MarketDimensionVerdict,
    MarketIntelligence,
    MarketState,
    evaluate_market_intelligence,
)
from src.investment_research.models.reconciliation import (
    reconcile_market_state,
    coverage_gate,
)
from src.investment_research.models.data_quality import DataQualityStatus


def _noop_sleep(_seconds: float) -> None:
    return None


def _candidate(**overrides) -> CandidateResult:
    observation = CandidateObservation(
        symbol=overrides.get("symbol", "600522.SH"),
        name=overrides.get("name", "测试股票"),
        sector="测试",
        theme="测试主题",
        warnings=overrides.get("warnings", []),
    )
    score = ScoreBreakdown(0.0, 0.0, 0.0, 0.0, 0.0)
    return CandidateResult(
        observation=observation,
        score=score,
        bucket="Panic Value Hunter",
        status=overrides.get("status", "Research Candidate"),
        reasons=overrides.get("reasons", []),
        first_rejection=overrides.get("first_rejection", ""),
        missing_fields=overrides.get("missing_fields", []),
    )


class TestRetryableClassification:
    def test_transient_errors_are_retryable(self) -> None:
        import socket

        assert is_retryable_error(socket.timeout("deadline"))
        assert is_retryable_error(ConnectionError("reset"))
        assert is_retryable_error(TimeoutError("deadline"))

    def test_schema_and_parse_errors_are_never_retryable(self) -> None:
        assert not is_retryable_error(KeyError("PE(TTM)"))
        assert not is_retryable_error(ValueError("bad date"))
        assert not is_retryable_error(TypeError("no rows"))


class TestEndpointPolicy:
    def test_transient_failure_is_retried_then_succeeds(self) -> None:
        policy = PublicEndpointPolicy(
            "fixture", max_attempts=3, sleep=_noop_sleep, clock=lambda: 0.0
        )
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise ConnectionError("reset")
            return 42

        assert policy.call("600522", flaky) == 42
        assert len(calls) == 2
        assert policy.health.successes == 1
        assert policy.health.failures == 1

    def test_non_retryable_error_is_not_retried(self) -> None:
        policy = PublicEndpointPolicy(
            "fixture", max_attempts=3, sleep=_noop_sleep, clock=lambda: 0.0
        )
        calls = []

        def boom():
            calls.append(1)
            raise KeyError("missing column")

        with pytest.raises(KeyError):
            policy.call("600522", boom)
        assert len(calls) == 1

    def test_circuit_breaker_opens_after_consecutive_failures(self) -> None:
        policy = PublicEndpointPolicy(
            "fixture", max_attempts=1, consecutive_failure_threshold=3,
            sleep=_noop_sleep, clock=lambda: 0.0,
        )

        def boom():
            raise ConnectionError("reset")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                policy.call("600522", boom)
        assert policy.health.circuit_open is True
        assert policy.health.state == "DEGRADED"
        with pytest.raises(EndpointDegradedError):
            policy.call("600522", boom)

    def test_cache_hit_skips_the_callback(self, tmp_path) -> None:
        cache = PitEndpointCache(tmp_path)
        policy = PublicEndpointPolicy(
            "fixture", sleep=_noop_sleep, clock=lambda: 0.0, cache=cache
        )
        frame = pd.DataFrame({"date": ["2024-02-05"], "close": [100.0]})
        as_of = date(2024, 2, 5)
        calls = []

        def source():
            calls.append(1)
            return frame

        first = policy.call("600522", source, requested_as_of=as_of)
        second = policy.call("600522", source, requested_as_of=as_of)
        assert bool((first["close"].astype(float).values == second["close"].values).all())
        assert len(calls) == 1
        assert policy.health.cache_hits == 1

    def test_cache_key_isolates_symbol_and_as_of(self, tmp_path) -> None:
        cache = PitEndpointCache(tmp_path)
        policy = PublicEndpointPolicy("fixture", sleep=_noop_sleep, clock=lambda: 0.0, cache=cache)
        calls = []

        def source():
            calls.append(1)
            return pd.DataFrame({"date": ["2024-02-05"], "close": [100.0]})

        policy.call("600522", source, requested_as_of=date(2024, 2, 5))
        policy.call("601991", source, requested_as_of=date(2024, 2, 5))
        policy.call("600522", source, requested_as_of=date(2024, 3, 5))
        assert len(calls) == 3

    def test_corrupt_cache_entry_is_invalidated_and_refetched(self, tmp_path) -> None:
        cache = PitEndpointCache(tmp_path)
        as_of = date(2024, 2, 5)
        cache.put("fixture", "600522", as_of, pd.DataFrame({"a": [1]}), pd.DataFrame({"a": [1]}))
        (file,) = tmp_path.glob("*.json")
        file.write_text("{not json", encoding="utf-8")
        policy = PublicEndpointPolicy("fixture", sleep=_noop_sleep, clock=lambda: 0.0, cache=cache)
        calls = []

        def source():
            calls.append(1)
            return pd.DataFrame({"b": [2]})

        result = policy.call("600522", source, requested_as_of=as_of)
        assert calls == [1]
        assert result["b"].iloc[0] == 2
        assert cache.invalidated_entries() == [file.name]


class TestEligibility:
    def test_metadata_listing_date_after_as_of_confirms_not_listed(self) -> None:
        verdict = resolve_eligibility(
            "588060", "etf", date(2020, 6, 1),
            listing_date=date(2020, 11, 16),
        )
        assert verdict.eligibility_status is EligibilityStatus.CONFIRMED_NOT_LISTED
        assert verdict.eligibility_evidence_source == "asset-metadata"

    def test_metadata_listing_date_before_as_of_confirms_eligible(self) -> None:
        verdict = resolve_eligibility(
            "588060", "etf", date(2021, 1, 4),
            listing_date=date(2020, 11, 16),
        )
        assert verdict.eligibility_status is EligibilityStatus.ELIGIBLE

    def test_trading_records_qualify_without_metadata(self) -> None:
        verdict = resolve_eligibility(
            "600522", "stock", date(2024, 2, 5), has_trading_history=True
        )
        assert verdict.eligibility_status is EligibilityStatus.ELIGIBLE
        assert verdict.eligibility_evidence_source == "trading-records"

    def test_provider_failure_is_unknown_never_not_listed(self) -> None:
        verdict = resolve_eligibility("600522", "stock", date(2024, 2, 5), has_trading_history=None)
        assert verdict.eligibility_status is EligibilityStatus.UNKNOWN
        assert verdict.eligibility_evidence_source == "provider-failure"

    def test_no_evidence_is_unknown(self) -> None:
        verdict = resolve_eligibility(
            "600522", "stock", date(2024, 2, 5), has_trading_history=False
        )
        assert verdict.eligibility_status is EligibilityStatus.UNKNOWN
        assert verdict.eligibility_evidence_source == "no-evidence"

    def test_listing_date_parser_tolerates_bad_values(self) -> None:
        assert listing_date_from_value("2020-11-16") == date(2020, 11, 16)
        assert listing_date_from_value(None) is None
        assert listing_date_from_value("not-a-date") is None
        assert listing_date_from_value("") is None


class TestCandidateContract:
    def test_etf_issuer_only_fields_are_not_applicable_not_missing(self) -> None:
        candidate = _candidate(symbol="588060.SH", name="科创50ETF")
        candidate.observation.security_type = "etf"
        payload = build_candidate_payload(candidate, as_of=date(2024, 2, 5))
        assert payload["quality"]["roe_5y_median_pct"] == "NOT_APPLICABLE"
        assert payload["valuation"]["pe_history_percentile"] == "NOT_APPLICABLE"
        assert "roe_5y_median_pct" not in payload["missing_fields"]
        assert "roe_5y_median_pct" not in payload["data_gaps"]

    def test_stock_missing_issuer_fields_stay_null(self) -> None:
        candidate = _candidate(symbol="600522.SH")
        payload = build_candidate_payload(candidate, as_of=date(2024, 2, 5))
        assert payload["quality"]["roe_5y_median_pct"] is None

    def test_provider_failure_warnings_become_data_gaps(self) -> None:
        candidate = _candidate(warnings=["历史估值读取失败: RemoteDisconnected"])
        payload = build_candidate_payload(candidate, as_of=date(2024, 2, 5))
        assert any("历史估值读取失败" in gap for gap in payload["data_gaps"])

    def test_horizon_legacy_keys_and_forward_validation(self) -> None:
        candidate = _candidate()
        payload = build_candidate_payload(
            candidate,
            as_of=date(2024, 2, 5),
            horizon_payload={
                "t5": 5.0, "t20": 20.0, "t60": None,
                "t5_max_drawdown": -1.0, "t5_excess": 0.5, "t5_outcome": "正确",
                "t20_max_drawdown": 0.0, "t20_excess": 0.0, "t20_outcome": "不确定",
                "t60_max_drawdown": None, "t60_excess": None, "t60_outcome": "不确定",
            },
        )
        assert payload["t5"] == 5.0
        assert payload["t20_outcome"] == "不确定"
        assert payload["forward_validation"]["t5"] == {
            "return_pct": 5.0, "max_drawdown_pct": -1.0, "excess_pct": 0.5, "outcome": "正确",
        }
        assert payload["forward_validation"]["t60"] is not None
        assert payload["forward_validation"]["t60"]["return_pct"] is None

    def test_no_horizon_payload_leaves_forward_validation_null(self) -> None:
        payload = build_candidate_payload(_candidate(), as_of=date(2024, 2, 5))
        assert payload["forward_validation"] == {"t5": None, "t20": None, "t60": None}
        assert payload["t5"] is None

    def test_excluded_candidate_carries_explicit_reason(self) -> None:
        payload = build_candidate_payload(
            _candidate(symbol="588060.SH"),
            as_of=date(2020, 6, 1),
            eligibility=resolve_eligibility(
                "588060.SH", "etf", date(2020, 6, 1),
                listing_date=date(2020, 11, 16),
            ),
        )
        assert payload["selected_excluded_reason"]


class TestIntelligenceSignals:
    def _panic_market(self):
        from src.investment_research.models.research_context import MarketSnapshotModel

        return MarketSnapshotModel(
            as_of="2024-02-05",
            indices=[{
                "symbol": "000300.SH",
                "name": "沪深300",
                "close": 3000.0,
                "daily_return_pct": -5.0,
                "drawdown_252_pct": -25.0,
                "below_ma250": True,
                "below_120d_low": True,
            }],
            advancer_ratio=0.1,
            above_ma60_ratio=0.2,
            limit_down_count=120,
            turnover_zscore=None,
        )

    def _sparse_market(self):
        from src.investment_research.models.research_context import MarketSnapshotModel

        return MarketSnapshotModel(
            as_of="2024-02-05",
            indices=[],
            advancer_ratio=None,
            above_ma60_ratio=None,
            limit_down_count=None,
            turnover_zscore=None,
        )

    def test_index_verdict_carries_four_explicit_signals(self) -> None:
        intel = evaluate_market_intelligence(self._panic_market())
        index = next(v for v in intel.dimensions if v.dimension is MarketDimension.INDEX)
        signals = {item.signal: item for item in index.signals}
        assert set(signals) == {
            "index_daily_return", "index_drawdown",
            "index_all_below_ma250", "index_all_below_120d_low",
        }
        assert signals["index_daily_return"].triggered is True
        assert signals["index_daily_return"].observed == -5.0
        assert signals["index_daily_return"].threshold == -2.0
        assert signals["index_all_below_ma250"].triggered is True
        assert signals["index_all_below_ma250"].observed == 1.0

    def test_breadth_verdict_carries_two_signals(self) -> None:
        intel = evaluate_market_intelligence(self._panic_market())
        breadth = next(v for v in intel.dimensions if v.dimension is MarketDimension.BREADTH)
        signals = {item.signal: item for item in breadth.signals}
        assert set(signals) == {
            "breadth_advancer_ratio", "breadth_above_ma60_ratio",
        }
        assert signals["breadth_advancer_ratio"].triggered is True
        assert signals["breadth_above_ma60_ratio"].triggered is True

    def test_unavailable_dimension_carries_no_signals(self) -> None:
        intel = evaluate_market_intelligence(self._sparse_market())
        index = next(v for v in intel.dimensions if v.dimension is MarketDimension.INDEX)
        assert index.signals == []
        breadth = next(v for v in intel.dimensions if v.dimension is MarketDimension.BREADTH)
        assert breadth.signals == []


class TestReconciliation:
    @staticmethod
    def _verdict(dimension: MarketDimension, status: DataQualityStatus, triggered: bool):
        return MarketDimensionVerdict(
            dimension=dimension, status=status, triggered=triggered
        )

    def _intel(self, state: MarketState = MarketState.PANIC) -> MarketIntelligence:
        return MarketIntelligence(
            state=state,
            stress_score=70,
            coverage={"available": 2, "estimated": 0, "total": 6},
            dimensions=[
                self._verdict(MarketDimension.INDEX, DataQualityStatus.AVAILABLE, True),
                self._verdict(MarketDimension.BREADTH, DataQualityStatus.AVAILABLE, False),
            ],
        )

    def test_gate_passes_only_with_available_triggered_evidence(self) -> None:
        assert coverage_gate(self._intel())["passed"] is True

    def test_gate_fails_without_available_trigger(self) -> None:
        intel = self._intel()
        intel.dimensions = [
            self._verdict(MarketDimension.INDEX, DataQualityStatus.AVAILABLE, False),
            self._verdict(MarketDimension.BREADTH, DataQualityStatus.AVAILABLE, False),
        ]
        assert coverage_gate(intel)["passed"] is False
        assert coverage_gate(intel)["has_available_trigger"] is False

    def test_estimated_only_trigger_never_passes_the_gate(self) -> None:
        intel = self._intel()
        intel.dimensions = [
            self._verdict(MarketDimension.LIMIT, DataQualityStatus.ESTIMATED, True),
            self._verdict(MarketDimension.TURNOVER, DataQualityStatus.AVAILABLE, False),
        ]
        gate = coverage_gate(intel)
        assert gate["passed"] is False
        assert gate["has_available_trigger"] is False

    def test_upgrade_only_when_gate_passes(self) -> None:
        reconciliation = reconcile_market_state("CAUTION", self._intel(MarketState.PANIC))
        assert reconciliation.effective_market_state == "PANIC"
        assert reconciliation.upgraded is True
        assert reconciliation.legacy_market_state == "CAUTION"
        assert reconciliation.intelligence_state == "PANIC"

    def test_never_downgrades_legacy_state(self) -> None:
        reconciliation = reconcile_market_state("EXTREME_PANIC", self._intel(MarketState.NORMAL))
        assert reconciliation.effective_market_state == "EXTREME_PANIC"
        assert reconciliation.upgraded is False

    def test_unknown_intel_keeps_legacy_with_reason(self) -> None:
        intel = self._intel(MarketState.UNKNOWN)
        intel.dimensions = []
        reconciliation = reconcile_market_state("NORMAL", intel)
        assert reconciliation.effective_market_state == "NORMAL"
        assert reconciliation.coverage_gate_passed is False
        assert any("UNKNOWN" in reason for reason in reconciliation.reasons)

    def test_missing_intel_keeps_legacy_state(self) -> None:
        reconciliation = reconcile_market_state("PANIC", None)
        assert reconciliation.effective_market_state == "PANIC"
        assert reconciliation.intelligence_state == "UNKNOWN"
