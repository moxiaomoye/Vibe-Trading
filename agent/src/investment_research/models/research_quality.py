"""Research Quality Evaluation (Phase 6) - historical Case Review contract.

A post-hoc (never point-in-time) review of a past research case: was the
reasoning sound, were risks missed, was the data sufficient? It is a case
review, explicitly not a prediction-accuracy measure: a single outcome proves
nothing about research capability, and the contract says so.

Review inputs are collected after the fact (materialized risks, reasoning
issues, data gaps of the artifact), so this module must never run inside the
PIT research pipeline itself — the frozen research report stays PIT-pure.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

RESEARCH_QUALITY_VERSION = "research-quality-v1"


class ReviewVerdict(StrEnum):
    """Per-dimension case review verdict."""

    SOUND = "SOUND"
    ADEQUATE = "ADEQUATE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class QualityDimension(StrEnum):
    """One reviewed dimension of a past research case."""

    REASONING = "reasoning"
    """判断合理性：事后复核研究理由是否成立/是否站得住."""
    RISK_COVERAGE = "risk_coverage"
    """风险遗漏：事后实际发生的风险是否在案发时被识别."""
    DATA_SUFFICIENCY = "data_sufficiency"
    """数据充分性：案发时研究输入的数据缺口是否过大."""


class QualityFinding(BaseModel):
    """Verdict and evidence for one reviewed dimension."""

    dimension: QualityDimension
    verdict: ReviewVerdict
    evidence: list[str] = Field(default_factory=list)
    note: str | None = None


class CaseReviewInputs(BaseModel):
    """Post-hoc inputs collected from a past research case and its outcomes."""

    case_id: str
    as_of_date: date
    data_gaps: list[str] = Field(default_factory=list)
    """Data gaps listed by the artifact's DataQualityReport at the time."""
    estimated_field_count: int = 0
    """Fields that were explicitly labelled estimates (never market stats)."""
    materialized_unflagged_risks: list[str] = Field(default_factory=list)
    """Risks that materialized after as_of but were not flagged at the time."""
    reasoning_issues: list[str] = Field(default_factory=list)
    """Reasoning problems found during the review of the case's claims."""


class ResearchQualityConfig(BaseModel):
    """Frozen review benchmarks (versioned, auditable)."""

    version: str = RESEARCH_QUALITY_VERSION
    sufficiency_gap_partial: int = 2
    sufficiency_gap_insufficient: int = 4
    risk_coverage_partial: int = 1
    risk_coverage_insufficient: int = 2
    reasoning_partial: int = 1
    reasoning_review_needed: int = 2


class ResearchQualityReview(BaseModel):
    """The typed case review result (post-hoc only)."""

    version: str = RESEARCH_QUALITY_VERSION
    case_id: str
    as_of_date: str
    overall: ReviewVerdict
    dimensions: list[QualityFinding] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)


def _verdict(grade: int, partial_at: int, insufficient_at: int,
             partial_label: ReviewVerdict, insufficient_label: ReviewVerdict,
             sound_label: ReviewVerdict) -> ReviewVerdict:
    if grade >= insufficient_at:
        return insufficient_label
    if grade >= partial_at:
        return partial_label
    return sound_label


def evaluate_research_quality(
    inputs: CaseReviewInputs,
    config: ResearchQualityConfig | None = None,
) -> ResearchQualityReview:
    """Review one historical case (pure, no I/O).

    Verdicts are per-dimension with a worst-of overall. The output explicitly
    warns that a single case proves nothing about predictive skill.
    """
    config = config or ResearchQualityConfig()
    findings: list[QualityFinding] = []
    summary: list[str] = []

    gap_grade = len(inputs.data_gaps)
    sufficiency = _verdict(
        gap_grade,
        config.sufficiency_gap_partial,
        config.sufficiency_gap_insufficient,
        ReviewVerdict.PARTIAL,
        ReviewVerdict.INSUFFICIENT,
        ReviewVerdict.SOUND,
    )
    sufficiency_evidence = list(inputs.data_gaps[:6])
    if inputs.estimated_field_count:
        sufficiency_evidence.append(
            f"{inputs.estimated_field_count}个输入为显式估计（非市场统计）"
        )
    findings.append(QualityFinding(
        dimension=QualityDimension.DATA_SUFFICIENCY,
        verdict=sufficiency,
        evidence=sufficiency_evidence,
        note="案发时数据缺口评估（DataQuality 口径）",
    ))
    if gap_grade:
        summary.append(f"数据充分性：案发时数据缺口{gap_grade}项 → {sufficiency.value}")

    missed_grade = len(inputs.materialized_unflagged_risks)
    coverage = _verdict(
        missed_grade,
        config.risk_coverage_partial,
        config.risk_coverage_insufficient,
        ReviewVerdict.PARTIAL,
        ReviewVerdict.INSUFFICIENT,
        ReviewVerdict.ADEQUATE,
    )
    findings.append(QualityFinding(
        dimension=QualityDimension.RISK_COVERAGE,
        verdict=coverage,
        evidence=list(inputs.materialized_unflagged_risks[:6]),
        note="事后已实现但案发时未标记的风险",
    ))
    if missed_grade:
        summary.append(
            f"风险覆盖：{missed_grade}项已实现风险案发时未标记 → {coverage.value}"
        )

    reasoning_grade = len(inputs.reasoning_issues)
    reasoning = _verdict(
        reasoning_grade,
        config.reasoning_partial,
        config.reasoning_review_needed,
        ReviewVerdict.PARTIAL,
        ReviewVerdict.REVIEW_NEEDED,
        ReviewVerdict.SOUND,
    )
    findings.append(QualityFinding(
        dimension=QualityDimension.REASONING,
        verdict=reasoning,
        evidence=list(inputs.reasoning_issues[:6]),
        note="复盘复核研究理由的成立性",
    ))
    if reasoning_grade:
        summary.append(f"判断合理性：{reasoning_grade}项理由问题 → {reasoning.value}")

    verdict_order = (
        ReviewVerdict.SOUND,
        ReviewVerdict.ADEQUATE,
        ReviewVerdict.PARTIAL,
        ReviewVerdict.INSUFFICIENT,
        ReviewVerdict.REVIEW_NEEDED,
    )
    overall = max((finding.verdict for finding in findings), key=verdict_order.index)
    summary.append(f"复盘结论：{overall.value}")
    summary.append(
        "重要边界：这是单次案例复盘（合理性/风险遗漏/数据充分），"
        "不是预测胜率——单次结果不能证明研究能力"
    )
    return ResearchQualityReview(
        version=config.version,
        case_id=inputs.case_id,
        as_of_date=inputs.as_of_date.isoformat(),
        overall=overall,
        dimensions=findings,
        summary=summary,
    )
