"""Phase 6 Research Quality Evaluation tests - historical Case Review."""

from __future__ import annotations

from datetime import date

from src.investment_research.models.research_quality import (
    RESEARCH_QUALITY_VERSION,
    CaseReviewInputs,
    QualityDimension,
    ResearchQualityConfig,
    ReviewVerdict,
    evaluate_research_quality,
)


def _case(**overrides) -> CaseReviewInputs:
    values = {
        "case_id": "20240205-panic-core-v1",
        "as_of_date": date(2024, 2, 5),
        "data_gaps": [],
        "estimated_field_count": 0,
        "materialized_unflagged_risks": [],
        "reasoning_issues": [],
    }
    values.update(overrides)
    return CaseReviewInputs(**values)


class TestDimensionVerdicts:
    def test_clean_case_is_sound(self) -> None:
        review = evaluate_research_quality(_case())
        assert review.overall is ReviewVerdict.ADEQUATE
        verdicts = {f.dimension: f.verdict for f in review.dimensions}
        assert verdicts[QualityDimension.DATA_SUFFICIENCY] is ReviewVerdict.SOUND
        assert verdicts[QualityDimension.RISK_COVERAGE] is ReviewVerdict.ADEQUATE
        assert verdicts[QualityDimension.REASONING] is ReviewVerdict.SOUND

    def test_data_gap_bands(self) -> None:
        assert evaluate_research_quality(
            _case(data_gaps=["a", "b"])
        ).dimensions[0].verdict is ReviewVerdict.PARTIAL
        assert evaluate_research_quality(
            _case(data_gaps=["a", "b", "c", "d"])
        ).dimensions[0].verdict is ReviewVerdict.INSUFFICIENT

    def test_missed_risk_bands(self) -> None:
        review = evaluate_research_quality(
            _case(materialized_unflagged_risks=["欺诈退市"])
        )
        coverage = next(
            f for f in review.dimensions if f.dimension is QualityDimension.RISK_COVERAGE
        )
        assert coverage.verdict is ReviewVerdict.PARTIAL
        assert coverage.evidence == ["欺诈退市"]
        assert evaluate_research_quality(
            _case(materialized_unflagged_risks=["a", "b"])
        ).overall is ReviewVerdict.INSUFFICIENT

    def test_reasoning_issue_bands(self) -> None:
        review = evaluate_research_quality(_case(reasoning_issues=["理由未成立"]))
        reasoning = next(
            f for f in review.dimensions if f.dimension is QualityDimension.REASONING
        )
        assert reasoning.verdict is ReviewVerdict.PARTIAL
        assert evaluate_research_quality(
            _case(reasoning_issues=["a", "b"])
        ).overall is ReviewVerdict.REVIEW_NEEDED

    def test_estimated_inputs_are_visible_in_evidence(self) -> None:
        review = evaluate_research_quality(_case(estimated_field_count=2))
        sufficiency = next(
            f for f in review.dimensions if f.dimension is QualityDimension.DATA_SUFFICIENCY
        )
        assert any("估计" in item for item in sufficiency.evidence)


class TestContractShape:
    def test_overall_is_worst_dimension(self) -> None:
        review = evaluate_research_quality(_case(data_gaps=["a", "b"]))
        assert review.overall is ReviewVerdict.PARTIAL

    def test_case_review_is_not_prediction_accuracy(self) -> None:
        review = evaluate_research_quality(_case())
        assert any("预测胜率" in line or "不能证明" in line for line in review.summary)

    def test_never_emits_trading_or_rating_directives(self) -> None:
        serialized = evaluate_research_quality(_case()).model_dump()
        for key in ("action", "signal", "recommendation", "order", "buy", "sell", "rating", "win_rate"):
            assert key not in serialized

    def test_deterministic_for_same_inputs(self) -> None:
        case = _case(data_gaps=["a"], materialized_unflagged_risks=["b"])
        assert evaluate_research_quality(case).model_dump() == evaluate_research_quality(case).model_dump()

    def test_version_and_benchmarks_are_frozen(self) -> None:
        config = ResearchQualityConfig()
        assert config.version == RESEARCH_QUALITY_VERSION
        assert config.sufficiency_gap_partial == 2
        assert config.sufficiency_gap_insufficient == 4
        assert config.risk_coverage_insufficient == 2
        assert config.reasoning_review_needed == 2
