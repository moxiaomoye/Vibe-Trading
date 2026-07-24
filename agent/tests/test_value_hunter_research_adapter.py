from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.investment_research.contracts import MarketRegime
from src.investment_research.discovery.models import DiscoveryDisposition
from src.investment_research.integrations.value_hunter_market import (
    PanicScanResearchAdapter,
    ResearchBinding,
)
from src.value_hunter.panic_classifier import PanicLevel
from src.value_hunter.panic_scan import run_panic_scan


TRADE_DATE = date(2026, 7, 22)
SCANNED_AT = datetime(2026, 7, 22, 18, 30, tzinfo=timezone.utc)
CUTOFF = SCANNED_AT + timedelta(minutes=1)


def _scan(tmp_path):
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text(
        'version: "adapter-v1"\nwatchlist:\n  name: "fixture"\n  symbols:\n    - "600522.SH"\n',
        encoding="utf-8",
    )
    count = 100
    codes = ["600522"] + [f"000{i:03d}" for i in range(1, count)]
    panel = {
        "spot_df": pd.DataFrame(
            {
                "代码": codes,
                "名称": ["fixture"] * count,
                "最新价": [94.0] + [10.0] * (count - 1),
                "涨跌幅": [-6.0] * 95 + [1.0] * 5,
                "昨收": [100.0] + [10.0] * (count - 1),
            }
        ),
        "limit_up_symbols": [],
        "limit_down_symbols": codes,
        "data_date": TRADE_DATE,
        "availability_date": TRADE_DATE,
        "now": SCANNED_AT,
        "market_change_pct": -0.05,
        "source": "fixture-provider",
    }
    return run_panic_scan(panel_data=panel, watchlist_path=str(watchlist))


def _binding():
    return ResearchBinding("600522.SH", "asset-600522", "thesis-ai-v3")


def test_maps_observations_to_market_state_and_evidence_gap_lead(tmp_path):
    scan = _scan(tmp_path)
    bundle = PanicScanResearchAdapter().map(
        scan,
        information_cutoff=CUTOFF,
        bindings=(_binding(),),
    )
    assert bundle.market_state.regime == MarketRegime.PANIC
    assert bundle.market_snapshot.advancer_ratio == pytest.approx(0.05)
    assert bundle.market_snapshot.median_daily_return == pytest.approx(-0.06)
    mapping = bundle.discovery_leads[0]
    assert mapping.lead is not None
    assert mapping.lead.disposition == DiscoveryDisposition.EVIDENCE_GAP
    assert "fundamental_integrity_evidence" in mapping.lead.missing_evidence
    assert mapping.facts.data_date == TRADE_DATE
    assert mapping.facts.availability_date == TRADE_DATE
    assert mapping.facts.rule_version == scan.rule_version
    assert mapping.facts.watchlist_hash == scan.watchlist_hash
    assert mapping.facts.source == "fixture-provider"
    assert "relative_strength_as_valuation" in mapping.incompatible_fields


def test_upstream_panic_label_is_not_directly_mapped_to_market_state(tmp_path):
    scan = _scan(tmp_path)
    relabeled = replace(
        scan,
        panic=replace(scan.panic, level=PanicLevel.NORMAL, reasons=["fixture relabel"]),
    )
    adapter = PanicScanResearchAdapter()
    original = adapter.map(scan, information_cutoff=CUTOFF)
    changed = adapter.map(relabeled, information_cutoff=CUTOFF)
    assert original.market_state.regime == changed.market_state.regime == MarketRegime.PANIC


def test_missing_binding_is_explicit_and_creates_no_formal_lead(tmp_path):
    mapping = PanicScanResearchAdapter().map(
        _scan(tmp_path),
        information_cutoff=CUTOFF,
    ).discovery_leads[0]
    assert mapping.lead is None
    assert "missing_asset_or_thesis_binding" in mapping.incompatible_fields


def test_future_availability_is_rejected(tmp_path):
    scan = replace(_scan(tmp_path), availability_date=TRADE_DATE + timedelta(days=1))
    with pytest.raises(ValueError, match="future"):
        PanicScanResearchAdapter().map(scan, information_cutoff=CUTOFF)


def test_adapter_is_deterministic_and_has_no_persistence(tmp_path):
    scan = _scan(tmp_path)
    adapter = PanicScanResearchAdapter()
    first = adapter.map(scan, information_cutoff=CUTOFF, bindings=(_binding(),))
    second = adapter.map(scan, information_cutoff=CUTOFF, bindings=(_binding(),))
    assert first == second
    assert first.evidence[0].direction.value == "neutral"
