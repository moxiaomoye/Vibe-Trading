"""Contract alignment tests (Phase 0.5): ResearchContext, artifact
versioning, rules_version tracking, and the data quality contract."""

from __future__ import annotations

import copy
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.investment_research.models.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactMetadata,
    canonical_json,
    compute_content_hash,
    compute_data_snapshot_id,
    make_research_id,
    provider_version_for,
)
from src.investment_research.models.data_quality import (
    DataQualityReport,
    DataQualityStatus,
    classify_data_quality,
)
from src.investment_research.models.research_context import (
    ResearchContext,
    attach_contract_metadata,
)
from src.investment_research.models.rules_version import (
    RULES_VERSION,
    current_rules_version,
    rules_fingerprint,
)


def _scan_payload() -> dict:
    return {
        "run_id": "research-mvp:2025-04-07",
        "mode": "akshare-historical",
        "market": {
            "score": 68.6,
            "level": "恐慌",
            "observation": {
                "as_of": "2025-04-07",
                "source": "akshare-historical",
                "coverage": ["indices", "watchlist_breadth"],
                "warnings": ["历史回溯：跌停数量为Data Gap"],
                "indices": [{
                    "symbol": "000300.SH",
                    "name": "沪深300",
                    "close": 3589.44,
                    "daily_return_pct": -7.05,
                    "drawdown_252_pct": -15.7,
                    "below_ma250": True,
                    "below_120d_low": True,
                }],
                "advancer_ratio": 0.0,
                "above_ma60_ratio": 0.0,
                "limit_down_count": None,
                "turnover_zscore": None,
                "advancer_count": 0,
                "decliner_count": 14,
                "limit_up_count": None,
                "turnover_amount": None,
            },
        },
        "candidates": [{
            "status": "A - 深入研究",
            "observation": {
                "symbol": "601991.SH",
                "name": "大唐发电",
                "sector": "电力",
                "theme": "火电与新能源",
                "pe_ttm": 12.0,
                "pb": 1.5,
                "pe_history_percentile": 0.1,
                "pe_industry_percentile": None,
                "roe_5y_median_pct": 8.0,
                "drawdown_252_pct": -30.0,
                "market_cap_billion": 60.0,
                "current_price": 3.2,
                "relative_to_sector_pct": None,
                "daily_return_pct": -5.0,
                "missing_fields": ["catalyst_evidence"],
                "etf_valuation": None,
            },
        }],
    }


class TestDataQuality:
    def test_none_defaults_to_missing(self) -> None:
        issue = classify_data_quality("market.limit_down_count", None)
        assert issue.status is DataQualityStatus.MISSING
        assert "research point in time" in (issue.reason or "")

    def test_none_with_unavailable_reason(self) -> None:
        issue = classify_data_quality(
            "market.limit_down_count", None,
            unavailable_reason="historical provider missing",
        )
        assert issue.status is DataQualityStatus.UNAVAILABLE
        assert issue.reason == "historical provider missing"

    def test_zero_is_available_not_missing(self) -> None:
        issue = classify_data_quality("market.advancer_ratio", 0.0)
        assert issue.status is DataQualityStatus.AVAILABLE

    def test_estimated_value(self) -> None:
        issue = classify_data_quality("candidate.pe_ttm", 12.0, estimate_note="derived from last annual report")
        assert issue.status is DataQualityStatus.ESTIMATED
        assert issue.reason == "derived from last annual report"

    def test_report_counts_and_filters(self) -> None:
        report = DataQualityReport(issues=[
            classify_data_quality("a", None),
            classify_data_quality("b", None),
            classify_data_quality("c", 0),
        ])
        assert report.counts() == {"missing": 2, "available": 1}
        assert len(report.issues_for("a")) == 1
        assert report.all_available() is False


class TestArtifactMetadata:
    def test_created_at_requires_timezone(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactMetadata(
                research_id="x", created_at=datetime(2025, 4, 7),
                as_of_date=date(2025, 4, 7), requested_date=date(2025, 4, 7),
                provider_version="akshare-v1",
            )

    def test_requested_date_cannot_follow_as_of(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactMetadata(
                research_id="x",
                created_at=datetime.now(timezone.utc),
                as_of_date=date(2025, 4, 7),
                requested_date=date(2025, 4, 8),
                provider_version="akshare-v1",
            )

    def test_research_id_format(self) -> None:
        assert make_research_id(date(2025, 4, 7)) == "20250407-panic-core-v1"
        assert make_research_id(date(2024, 2, 5), "custom-v1") == "20240205-custom-v1"

    def test_artifact_version_defaults_to_schema_version(self) -> None:
        metadata = ArtifactMetadata(
            research_id="x",
            created_at=datetime.now(timezone.utc),
            as_of_date=date(2025, 4, 7),
            requested_date=date(2025, 4, 7),
            provider_version="akshare-v1",
        )
        assert metadata.artifact_version == ARTIFACT_SCHEMA_VERSION
        assert metadata.schema_version == metadata.artifact_version

    def test_provider_version_for(self) -> None:
        assert provider_version_for("akshare") == "akshare-v1"
        assert provider_version_for("akshare-historical") == "akshare-historical-v1"
        assert provider_version_for("demo") == "demo-v1"

    def test_canonical_hash_stable_across_key_order(self) -> None:
        payload_a = {"market": {"score": 1, "level": "PANIC"}, "candidates": []}
        payload_b = {"candidates": [], "market": {"level": "PANIC", "score": 1}}
        assert canonical_json(payload_a) == canonical_json(payload_b)
        assert compute_content_hash(payload_a) == compute_content_hash(payload_b)

    def test_hash_changes_with_content(self) -> None:
        assert compute_content_hash({"a": 1}) != compute_content_hash({"a": 2})

    def test_data_snapshot_id_deterministic_and_sensitive(self) -> None:
        payload = _scan_payload()
        assert compute_data_snapshot_id(payload) == compute_data_snapshot_id(dict(payload))
        changed = copy.deepcopy(payload)
        changed["market"]["observation"]["advancer_ratio"] = 0.25
        assert compute_data_snapshot_id(changed) != compute_data_snapshot_id(payload)
        changed = copy.deepcopy(payload)
        changed["candidates"][0]["observation"]["pe_ttm"] = 15.0
        assert compute_data_snapshot_id(changed) != compute_data_snapshot_id(payload)

    def test_data_snapshot_id_ignores_derived_state(self) -> None:
        payload = _scan_payload()
        enriched = copy.deepcopy(payload)
        enriched["research_context"] = {"schema_version": 1, "context": {"x": 1}}
        enriched["universe"] = [{"ignored": True}]
        enriched["errors"] = ["transient"]
        assert compute_data_snapshot_id(enriched) == compute_data_snapshot_id(payload)


class TestRulesVersion:
    def test_current_rules_version(self) -> None:
        assert current_rules_version() == "panic-core-v1"
        assert current_rules_version() == RULES_VERSION

    def test_fingerprint_stable_for_same_profile(self) -> None:
        profile = {
            "value": 50, "label": "平衡",
            "index_daily_return_pct": -2.25, "max_advancer_ratio": 0.35,
            "min_limit_down_count": 42, "required_confirmations": 2,
            "config_version": 2,
        }
        assert rules_fingerprint(profile) == rules_fingerprint(dict(profile))

    def test_fingerprint_changes_with_thresholds(self) -> None:
        base = {
            "index_daily_return_pct": -2.25, "max_advancer_ratio": 0.35,
            "min_limit_down_count": 42, "required_confirmations": 2,
        }
        stricter = dict(base, min_limit_down_count=20)
        assert rules_fingerprint(base) != rules_fingerprint(stricter)

    def test_fingerprint_ignores_transient_keys(self) -> None:
        base = {
            "index_daily_return_pct": -2.25, "max_advancer_ratio": 0.35,
            "min_limit_down_count": 42, "required_confirmations": 2,
        }
        enriched = dict(base, trigger_count=2, checks={})
        assert rules_fingerprint(base) == rules_fingerprint(enriched)

    def test_fingerprint_none_profile(self) -> None:
        assert rules_fingerprint(None) is None


class TestResearchContext:
    def test_from_scan_payload(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(),
            requested_date=date(2025, 4, 7),
            provider="akshare-historical",
            profile={"min_limit_down_count": 20},
        )
        assert context.as_of_date == date(2025, 4, 7)
        assert context.requested_date == date(2025, 4, 7)
        assert context.market_snapshot.source == "akshare-historical"
        assert context.market_snapshot.indices[0].symbol == "000300.SH"
        assert context.market_snapshot.indices[0].below_ma250 is True
        assert context.market_snapshot.advancer_ratio == 0.0
        assert "601991.SH" in context.valuation_snapshot
        assert context.valuation_snapshot["601991.SH"].pe_ttm == 12.0
        assert context.valuation_snapshot["601991.SH"].pe_industry_percentile is None

    def test_data_quality_from_scan_payload(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(),
            provider="akshare-historical",
        )
        limit_down = next(
            issue for issue in context.data_quality.issues
            if issue.field == "market.limit_down_count"
        )
        assert limit_down.status is DataQualityStatus.UNAVAILABLE
        assert "跌停" in (limit_down.reason or "")
        turnover = next(
            issue for issue in context.data_quality.issues
            if issue.field == "market.turnover_zscore"
        )
        assert turnover.status is DataQualityStatus.UNAVAILABLE
        candidate_gap = next(
            issue for issue in context.data_quality.issues
            if issue.field == "candidate.601991.SH.catalyst_evidence"
        )
        assert candidate_gap.status is DataQualityStatus.MISSING

    def test_estimated_fields_flow_through_data_quality_and_intel(self) -> None:
        payload = _scan_payload()
        payload["market"]["observation"]["limit_down_count"] = 8
        payload["market"]["observation"]["limit_up_count"] = 2
        payload["market"]["observation"]["estimated_fields"] = [
            "limit_down_count", "limit_up_count",
        ]
        context = ResearchContext.from_scan_payload(payload, provider="akshare-historical")
        limit_down = next(
            issue for issue in context.data_quality.issues
            if issue.field == "market.limit_down_count"
        )
        assert limit_down.status is DataQualityStatus.ESTIMATED
        assert "研究标的池" in (limit_down.reason or "")
        limit_up = next(
            issue for issue in context.data_quality.issues
            if issue.field == "market.limit_up_count"
        )
        assert limit_up.status is DataQualityStatus.ESTIMATED
        intel = context.market_intelligence
        assert intel is not None
        limit_verdict = next(
            v for v in intel.dimensions if v.dimension.value == "limit"
        )
        assert limit_verdict.status is DataQualityStatus.ESTIMATED
        assert intel.coverage["estimated"] == 1
        assert intel.coverage["available"] == 2
        assert intel.coverage["total"] == 6

    def test_market_intelligence_embedded_in_context(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(), provider="akshare-historical"
        )
        intel = context.market_intelligence
        assert intel is not None
        assert intel.state.value in {"NORMAL", "STRESS", "PANIC", "EXTREME_PANIC", "UNKNOWN"}
        assert intel.coverage["total"] == 6
        verdicts = {v.dimension.value: v for v in intel.dimensions}
        assert verdicts["index"].status is DataQualityStatus.AVAILABLE
        assert verdicts["limit"].status is DataQualityStatus.UNAVAILABLE
        assert "Data Gap" in (verdicts["limit"].note or "")
        assert verdicts["volatility"].status is DataQualityStatus.UNAVAILABLE

    def test_market_intelligence_deterministic_across_roundtrip(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(), provider="akshare-historical"
        )
        restored = ResearchContext.model_validate(context.model_dump(mode="json"))
        assert (
            restored.market_intelligence.model_dump()
            == context.market_intelligence.model_dump()
        )

    def test_artifact_metadata_embedded(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(),
            provider="akshare-historical",
            profile={"min_limit_down_count": 20, "required_confirmations": 2},
        )
        metadata = context.artifact_metadata
        assert metadata.research_id == "20250407-panic-core-v1"
        assert metadata.research_run_id == context.research_run_id
        assert metadata.research_run_id is not None
        assert metadata.rules_version == "panic-core-v1"
        assert metadata.provider_version == "akshare-historical-v1"
        assert metadata.artifact_version == ARTIFACT_SCHEMA_VERSION
        assert metadata.schema_version == ARTIFACT_SCHEMA_VERSION
        assert metadata.created_at.tzinfo is not None
        assert metadata.rules_fingerprint is not None
        assert metadata.data_snapshot_id == compute_data_snapshot_id(_scan_payload())
        assert metadata.data_snapshot_id is not None


class TestAttachContractMetadata:
    def test_attaches_artifact_and_data_quality(self) -> None:
        report = {
            "trade_date": "2025-04-07",
            "market_state": "PANIC",
            "panic_sensitivity": {},
            "market_summary": {},
            "candidates": [],
            "data_gaps": ["market.limit_down_count"],
        }
        result = attach_contract_metadata(
            _scan_payload(),
            report,
            provider="akshare-historical",
        )
        assert result is report
        assert "artifact" in result
        assert result["artifact"]["research_id"] == "20250407-panic-core-v1"
        assert result["artifact"]["content_hash"] is not None
        assert result["research_run_id"] == result["artifact"]["research_run_id"]
        assert result["research_run_id"] is not None
        assert "market_intelligence" in result
        assert result["market_intelligence"]["state"] in {
            "NORMAL", "STRESS", "PANIC", "EXTREME_PANIC", "UNKNOWN",
        }
        assert result["market_intelligence"]["coverage"]["total"] == 6
        assert "data_quality" in result
        assert result["data_quality"]["counts"]["unavailable"] >= 1
        assert result["data_quality"]["all_available"] is False

    def test_content_hash_covers_research_content_not_artifact(self) -> None:
        report = {
            "trade_date": "2025-04-07",
            "market_state": "PANIC",
            "market_summary": {"source": "akshare-historical"},
            "candidates": [],
            "data_gaps": [],
        }
        attach_contract_metadata(_scan_payload(), report, provider="akshare-historical")
        first_hash = report["artifact"]["content_hash"]
        report["data_gaps"].append("candidate.601991.SH.t60")
        attach_contract_metadata(_scan_payload(), report, provider="akshare-historical")
        assert report["artifact"]["content_hash"] != first_hash

    def test_attach_is_deterministic_for_same_content(self) -> None:
        def build() -> dict:
            return {
                "trade_date": "2025-04-07",
                "market_state": "PANIC",
                "market_summary": {"source": "akshare-historical"},
                "candidates": [],
                "data_gaps": [],
            }

        first = attach_contract_metadata(_scan_payload(), build(), provider="akshare-historical")
        second = attach_contract_metadata(_scan_payload(), build(), provider="akshare-historical")
        assert first["artifact"]["content_hash"] == second["artifact"]["content_hash"]
        assert first["artifact"]["research_id"] == second["artifact"]["research_id"]
        assert (
            first["artifact"]["data_snapshot_id"]
            == second["artifact"]["data_snapshot_id"]
            == compute_data_snapshot_id(_scan_payload())
        )
        assert first["artifact"]["artifact_version"] == ARTIFACT_SCHEMA_VERSION
        assert (
            first["research_run_id"]
            == second["research_run_id"]
            == first["artifact"]["research_run_id"]
        )

    def test_attach_accepts_preexisting_context(self) -> None:
        context = ResearchContext.from_scan_payload(
            _scan_payload(),
            requested_date=date(2025, 4, 7),
            provider="akshare-historical",
            profile={"min_limit_down_count": 20},
        )
        report = {
            "trade_date": "2025-04-07",
            "market_state": "PANIC",
            "market_summary": {"source": "akshare-historical"},
            "candidates": [],
            "data_gaps": [],
        }
        result = attach_contract_metadata(
            _scan_payload(), report, context=context
        )
        assert result["artifact"]["research_id"] == "20250407-panic-core-v1"
        assert result["artifact"]["data_snapshot_id"] == context.artifact_metadata.data_snapshot_id
        assert result["data_quality"]["counts"]["unavailable"] >= 1

    def test_attach_requires_provider_without_context(self) -> None:
        with pytest.raises(ValueError, match="provider"):
            attach_contract_metadata(_scan_payload(), {})
