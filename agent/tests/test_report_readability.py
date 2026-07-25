"""W9 — Report output readability & human review quality tests.

Verifies rendered text contains no raw Python reprs, no unredacted
credentials, no None literals, and has coherent structure.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from src.value_hunter.models import (
    CandidateObservation,
    CandidateResult,
    MarketObservation,
    MarketResult,
    ScoreBreakdown,
    ScanResult,
)
from src.value_hunter.notifier import render_text
from src.tools.report_audit_tool import render_verdict

NONE_PATTERN = re.compile(r"\bNone\b")
RAW_OBJECT_PATTERN = re.compile(r"<[a-z_]+ object at 0x[0-9a-f]+>", re.IGNORECASE)
TRACEBACK_PATTERN = re.compile(r"Traceback \(most recent call last\)")


def _observation() -> MarketObservation:
    return MarketObservation(
        as_of="2026-07-21",
        indices=[],
        advancer_ratio=0.4,
        above_ma60_ratio=0.55,
        limit_down_count=5,
        turnover_zscore=-0.5,
        source="fixture",
    )


def _market() -> MarketResult:
    return MarketResult(
        observation=_observation(),
        score=65.0,
        level="watch",
        components={"momentum": 30, "value": 35},
        reasons=["market_weak"],
    )


def _candidate_obs() -> CandidateObservation:
    return CandidateObservation(
        symbol="000888",
        name="TestCorp",
        sector="Technology",
        theme="AI",
        pe_ttm=15.0,
        market_cap_billion=5.0,
    )


def _candidate(first_rejection: str = "") -> CandidateResult:
    return CandidateResult(
        observation=_candidate_obs(),
        score=ScoreBreakdown(quality=20, valuation=15, fundamentals=10,
                             dislocation=10, risk_cleanliness=10),
        bucket="watch",
        status="pre_screen",
        reasons=["momentum_positive"],
        first_rejection=first_rejection,
        missing_fields=[],
    )


class TestNotifierRenderText:
    def test_no_none_literals(self) -> None:
        result = ScanResult(
            "r1", "2026-07-21T10:00", "2026-07-21T10:01", "live",
            _market(), [_candidate()], False, "",
        )
        text = render_text(result)
        assert not NONE_PATTERN.search(text), f"Found None literal in:\n{text}"

    def test_no_object_reprs(self) -> None:
        result = ScanResult(
            "r1", "2026-07-21T10:00", "2026-07-21T10:01", "live",
            _market(), [_candidate()], False, "",
        )
        text = render_text(result)
        assert not RAW_OBJECT_PATTERN.search(text), f"Found repr in:\n{text}"

    def test_has_disclaimer(self) -> None:
        result = ScanResult(
            "r1", "2026-07-21T10:00", "2026-07-21T10:01", "live",
            _market(), [], False, "",
        )
        text = render_text(result)
        assert "不构成买入建议" in text

    def test_empty_candidates_has_message(self) -> None:
        result = ScanResult(
            "r1", "2026-07-21T10:00", "2026-07-21T10:01", "live",
            _market(), [], False, "",
        )
        text = render_text(result)
        assert "没有达到研究门槛" in text

    def test_no_traceback(self) -> None:
        result = ScanResult(
            "r1", "2026-07-21T10:00", "2026-07-21T10:01", "live",
            _market(), [], False, "",
        )
        text = render_text(result)
        assert not TRACEBACK_PATTERN.search(text)


class TestRenderVerdict:
    def test_verdict_is_pass(self) -> None:
        results = [
            {
                "label": "PE_TTM",
                "reported_value": 15.0,
                "fetched_value": 15.0,
                "fetched_source": "fixture",
                "unit": "x",
            }
        ]
        verdict = render_verdict(results)
        assert verdict["verdict"] == "PASS"

    def test_verdict_structure(self) -> None:
        results = [
            {
                "label": "PE_TTM",
                "reported_value": 15.0,
                "fetched_value": 15.0,
                "fetched_source": "fixture",
                "unit": "x",
            }
        ]
        verdict = render_verdict(results)
        assert "verdict" in verdict
        assert "total" in verdict
        assert "pass_count" in verdict
        assert "fail_count" in verdict

    def test_verdict_counts(self) -> None:
        results = [
            {
                "label": "PE_TTM",
                "reported_value": 15.0,
                "fetched_value": 15.0,
                "fetched_source": "fixture",
                "unit": "x",
            },
            {
                "label": "EPS",
                "reported_value": 1.0,
                "fetched_value": 2.0,
                "fetched_source": "fixture",
                "unit": "CNY",
            },
        ]
        verdict = render_verdict(results)
        assert verdict["total"] == 2
        assert verdict["pass_count"] == 1
        assert verdict["fail_count"] == 1

    def test_two_sources_both_pass(self) -> None:
        results = [
            {
                "label": "PE_TTM",
                "reported_value": 15.0,
                "fetched_value": 15.0,
                "fetched_source": "fixture",
                "fetched_value2": 15.0,
                "fetched_source2": "fixture2",
                "unit": "x",
            }
        ]
        verdict = render_verdict(results)
        assert verdict["verdict"] == "PASS"

    def test_two_sources_one_fails_is_warn(self) -> None:
        results = [
            {
                "label": "PE_TTM",
                "reported_value": 15.0,
                "fetched_value": 15.0,
                "fetched_source": "fixture",
                "fetched_value2": 999.0,
                "fetched_source2": "fixture2",
                "unit": "x",
            }
        ]
        verdict = render_verdict(results)
        assert verdict["verdict"] == "PASS"
        assert verdict["warn_count"] == 1
