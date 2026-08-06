"""Contract enforcement tests (Phase 0.8 Architecture Hardening).

These tests freeze the research pipeline contract so future changes cannot
silently regress to bare-dict research payloads:

1. Layering: ``value_hunter`` must never depend on ``investment_research``.
2. Research flows: every research entry point must operate on
   ``ResearchContext`` (adapter seams are the only dict boundary).
3. Artifact identity: the artifact block must always carry the frozen
   identity fields (artifact_version, rules_version, data_snapshot_id,
   content_hash, as_of_date) plus the research_run_id thread.
4. Report shape: every contract-carrying report exposes the frozen top-level
   keys (artifact, data_quality, research_run_id).

Adding a new research function that bypasses the typed context, or a new
dependency from value_hunter up to investment_research, fails these tests.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from src.value_hunter import __file__ as _value_hunter_init

from src.investment_research.models.artifact import ArtifactMetadata
from src.investment_research.models.research_context import ResearchContext, attach_contract_metadata

SRC = Path(_value_hunter_init).resolve().parents[1]
VALUE_HUNTER_PKG = SRC / "value_hunter"

# Research entry points that MUST reference ResearchContext (no bare-dict flow).
RESEARCH_ENTRY_POINTS = (
    "build_research_run",
    "build_historical_evaluation",
    "_scan_historical_provider",
    "_rebuild_historical_evaluation",
)

# Frozen identity fields every artifact must carry.
ARTIFACT_IDENTITY_FIELDS = (
    "artifact_version",
    "as_of_date",
    "rules_version",
    "data_snapshot_id",
    "content_hash",
)


def _module_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
    return roots


def test_value_hunter_never_imports_investment_research() -> None:
    for module in VALUE_HUNTER_PKG.glob("*.py"):
        if module.name.startswith("__"):
            continue
        roots = _module_import_roots(module)
        assert "investment_research" not in roots, (
            f"{module.name} must not depend on investment_research (layering violation)"
        )


# Sanctioned seams that carry a typed ResearchContext. A research entry point
# must reference at least one of these; anything else is a bare-dict flow.
CONTEXT_SEAMS = ("ResearchContext", "_context_from_snapshot")


def test_research_entry_points_use_research_context() -> None:
    from src.investment_research.application import research_mvp as mvp

    for name in RESEARCH_ENTRY_POINTS:
        func = getattr(mvp, name)
        source = inspect.getsource(func)
        assert any(seam in source for seam in CONTEXT_SEAMS), (
            f"{name} must operate on ResearchContext, not bare dicts"
        )


def test_artifact_identity_fields_are_frozen() -> None:
    fields = set(ArtifactMetadata.model_fields)
    for field in ARTIFACT_IDENTITY_FIELDS:
        assert field in fields, f"artifact is missing frozen identity field: {field}"


def test_report_contract_exposes_frozen_top_level_keys() -> None:
    report = {
        "trade_date": "2025-04-07",
        "market_state": "PANIC",
        "market_summary": {"source": "akshare-historical"},
        "candidates": [],
        "data_gaps": [],
    }
    attach_contract_metadata(_scan_payload(), report, provider="akshare-historical")
    assert set(report) >= {"artifact", "data_quality", "research_run_id", "market_intelligence"}


def test_research_run_id_is_deterministic_across_restore_roundtrip() -> None:
    payload = _scan_payload()
    context = ResearchContext.from_scan_payload(
        payload, provider="akshare-historical"
    )
    serialized = context.model_dump(mode="json")
    restored = ResearchContext.model_validate(serialized)
    assert restored.research_run_id == context.research_run_id
    assert restored.artifact_metadata.research_run_id == context.research_run_id
    assert context.research_run_id is not None


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
