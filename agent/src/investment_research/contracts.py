"""Shared, dependency-free contracts for the investment research domain."""

from __future__ import annotations

from enum import StrEnum


class EvidenceDirection(StrEnum):
    SUPPORTING = "supporting"
    COUNTER = "counter"
    NEUTRAL = "neutral"


class ConfidenceBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ThesisStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    WEAKENING = "weakening"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


class ThesisScope(StrEnum):
    MACRO = "macro"
    THEME = "theme"
    INDUSTRY = "industry"
    VALUE_CHAIN = "value_chain"
    COMPANY = "company"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"
    SECTOR = "sector"


class AttributionCategory(StrEnum):
    FUNDAMENTALS = "fundamentals"
    EXPECTATIONS = "expectations"
    VALUATION = "valuation"
    PASSIVE_FLOW = "passive_flow"
    ACTIVE_FLOW = "active_flow"
    LIQUIDITY = "liquidity"
    MACRO_RATES = "macro_rates"
    POLICY = "policy"
    EVENT = "event"
    TECHNICAL = "technical"
    UNKNOWN = "unknown"


class AttributionRole(StrEnum):
    TRIGGER = "trigger"
    AMPLIFIER = "amplifier"
    BACKGROUND = "background"


class Permanence(StrEnum):
    TEMPORARY = "temporary"
    STRUCTURAL = "structural"
    UNCERTAIN = "uncertain"


class OpportunityStatus(StrEnum):
    HYPOTHESIS = "hypothesis"
    OPEN = "open"
    STRENGTHENING = "strengthening"
    WEAKENING = "weakening"
    CLOSED = "closed"
    INVALIDATED = "invalidated"


class ResearchPriority(StrEnum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ActionLevel(StrEnum):
    WATCH = "watch"
    RESEARCH = "research"
    PREPARE = "prepare"
    ACTION_CANDIDATE = "action_candidate"


class AssessmentVerdict(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    UNKNOWN = "unknown"


class MarketRegime(StrEnum):
    NORMAL = "normal"
    CORRECTION = "correction"
    SYSTEMIC_STRESS = "systemic_stress"
    PANIC = "panic"
    UNKNOWN = "unknown"


class ExperimentSplit(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
    FORWARD = "forward"


class ProcessQuality(StrEnum):
    SOUND = "sound"
    FLAWED = "flawed"
    UNDETERMINED = "undetermined"


class OutcomeDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class ProcessOutcomeClass(StrEnum):
    HIGH_QUALITY_SUCCESS = "high_quality_success"
    REASONABLE_FAILURE = "reasonable_failure"
    LUCKY_GAIN = "lucky_gain"
    TYPICAL_ERROR = "typical_error"
    UNRESOLVED = "unresolved"


class ResearchErrorType(StrEnum):
    THESIS_ALREADY_BROKEN = "thesis_already_broken"
    STRUCTURAL_AS_TEMPORARY = "structural_as_temporary"
    MARKET_VIEW_MISREAD = "market_view_misread"
    EXPOSURE_NOT_PROVEN = "exposure_not_proven"
    EVIDENCE_QUALITY_OVERSTATED = "evidence_quality_overstated"
    CHEAP_NOT_MISPRICED = "cheap_not_mispriced"
    NARRATIVE_OVERREACH = "narrative_overreach"
    POINT_IN_TIME_CONTAMINATION = "point_in_time_contamination"


def confidence_band(confidence: float) -> ConfidenceBand:
    """Convert a normalized confidence value into a stable display band."""
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if confidence >= 0.85:
        return ConfidenceBand.VERY_HIGH
    if confidence >= 0.7:
        return ConfidenceBand.HIGH
    if confidence >= 0.5:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW
