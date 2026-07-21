from __future__ import annotations

from datetime import datetime, timezone
from time import sleep

from src.investment_research.evidence.context import EvidenceSubjectType
from src.investment_research.integrations.value_hunter_market import ValueHunterMarketAdapter
from src.value_hunter.providers import DemoProvider


NOW = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)


class SlowDemoProvider(DemoProvider):
    name = "slow-demo"

    def load_market(self):
        sleep(1)
        return super().load_market()


def test_legacy_market_adapter_uses_observations_but_ignores_v1_scores() -> None:
    bundle = ValueHunterMarketAdapter(DemoProvider()).load(NOW)
    snapshot = bundle.snapshot
    assert snapshot.broad_index_drawdown == -0.34
    assert snapshot.index_below_long_trend_ratio == 1.0
    assert snapshot.advancer_ratio == 0.08
    assert snapshot.limit_down_count == 170
    assert snapshot.median_daily_return == -0.034
    assert bundle.evidence_bundle.subject_type == EvidenceSubjectType.MARKET
    assert bundle.evidence_bundle.evidence_ids == (bundle.evidence[0].evidence_id,)
    assert bundle.evidence[0].content_hash


def test_adapter_identity_is_content_addressed_and_idempotent() -> None:
    adapter = ValueHunterMarketAdapter(DemoProvider())
    first = adapter.load(NOW)
    second = adapter.load(NOW)
    assert first == second


def test_provider_process_timeout_prevents_a_hung_daily_pipeline() -> None:
    adapter = ValueHunterMarketAdapter(SlowDemoProvider())
    try:
        adapter.load_with_timeout(NOW, timeout_seconds=0.05)
    except TimeoutError as exc:
        assert "slow-demo" in str(exc)
    else:
        raise AssertionError("slow provider unexpectedly completed")
