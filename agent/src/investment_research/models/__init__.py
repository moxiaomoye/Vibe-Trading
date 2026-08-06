"""Contract alignment models for the research core (Phase 0.5).

Pure Pydantic data objects only: no API calls, no database access, no
network requests. These models type the existing research payloads without
introducing a second context.
"""

from .artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactMetadata,
    compute_content_hash,
    compute_data_snapshot_id,
    make_research_id,
    make_research_run_id,
    provider_version_for,
)
from .data_quality import (
    DataQualityIssue,
    DataQualityReport,
    DataQualityStatus,
    classify_data_quality,
)
from .market_intelligence import (
    MARKET_INTELLIGENCE_VERSION,
    MarketDimension,
    MarketDimensionVerdict,
    MarketIntelligence,
    MarketIntelligenceConfig,
    MarketState,
    evaluate_market_intelligence,
)
from .research_context import (
    IndexSnapshotModel,
    MarketSnapshotModel,
    ResearchContext,
    ValuationSnapshotModel,
    attach_contract_metadata,
)
from .rules_version import RULES_VERSION, current_rules_version, rules_fingerprint

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ArtifactMetadata",
    "DataQualityIssue",
    "DataQualityReport",
    "DataQualityStatus",
    "IndexSnapshotModel",
    "MARKET_INTELLIGENCE_VERSION",
    "MarketDimension",
    "MarketDimensionVerdict",
    "MarketIntelligence",
    "MarketIntelligenceConfig",
    "MarketSnapshotModel",
    "MarketState",
    "RULES_VERSION",
    "ResearchContext",
    "ValuationSnapshotModel",
    "attach_contract_metadata",
    "classify_data_quality",
    "compute_content_hash",
    "compute_data_snapshot_id",
    "current_rules_version",
    "evaluate_market_intelligence",
    "make_research_id",
    "make_research_run_id",
    "provider_version_for",
    "rules_fingerprint",
]
