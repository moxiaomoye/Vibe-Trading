from __future__ import annotations

import pytest

from src.value_hunter.config import (
    PanicValueMethodConfig,
    load_panic_value_config,
    resolve_panic_sensitivity,
)
from src.value_hunter.providers import DemoProvider
from src.value_hunter.scoring import score_candidate


def test_versioned_yaml_loads_single_method_weights(tmp_path) -> None:
    path = tmp_path / "panic-value.yaml"
    path.write_text(
        """
version: 1
market_panic:
  index_daily_return_pct: -3
  max_advancer_ratio: 0.25
  min_limit_down_count: 50
stock_filters:
  min_roe_pct: 8
  max_pe: 60
  max_daily_decline_pct: 15
  min_market_cap_billion: 5
score_weights:
  mispricing: 35
  quality: 25
  valuation: 20
  relative_strength: 10
  catalyst: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_panic_value_config(path)

    assert config.index_daily_return_pct == -3
    assert config.min_roe_pct == 8
    assert config.mispricing_weight == 35


def test_invalid_weights_fail_clearly() -> None:
    with pytest.raises(ValueError, match="sum to 100"):
        PanicValueMethodConfig(mispricing_weight=20)


def test_configured_filter_is_a_research_rejection() -> None:
    candidate = DemoProvider().load_candidates()[0]
    result = score_candidate(candidate, PanicValueMethodConfig(min_roe_pct=30))

    assert result.status == "Reject"
    assert "ROE" in result.first_rejection


def test_slider_resolves_sensitive_balanced_and_strict_thresholds() -> None:
    _, sensitive = resolve_panic_sensitivity(0)
    _, balanced = resolve_panic_sensitivity(50)
    _, strict = resolve_panic_sensitivity(100)

    assert sensitive.label == "敏感"
    assert sensitive.required_confirmations == 1
    assert balanced.label == "平衡"
    assert balanced.required_confirmations == 2
    assert strict.label == "严谨"
    assert strict.required_confirmations == 3
    assert sensitive.index_daily_return_pct > strict.index_daily_return_pct
    assert sensitive.max_advancer_ratio > strict.max_advancer_ratio
    assert sensitive.min_limit_down_count < strict.min_limit_down_count
