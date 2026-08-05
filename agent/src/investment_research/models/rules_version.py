"""Rules version tracking (Task 3).

Adds a stable version identifier to research outputs so historical results
stay explainable after rule changes. This module does NOT change any scoring
rule or financial threshold — it only fingerprints the resolved panic profile
so that a threshold change is detectable in the artifact metadata.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

RULES_VERSION = "panic-core-v1"


def current_rules_version() -> str:
    """The current rules identity shared by all artifacts in this build."""
    return RULES_VERSION


_FINGERPRINT_KEYS = (
    "value",
    "label",
    "index_daily_return_pct",
    "max_advancer_ratio",
    "min_limit_down_count",
    "required_confirmations",
    "config_version",
)


def rules_fingerprint(profile: Mapping[str, Any] | None) -> str | None:
    """Content fingerprint of the resolved panic sensitivity profile.

    The fingerprint is derived from the auditable thresholds (index daily
    return, advancer ratio, limit-down count, required confirmations), so a
    threshold change yields a different fingerprint while the stable
    ``RULES_VERSION`` identity stays comparable across time. Only the
    canonical keys are hashed, so live, stored-snapshot, and rebuild paths
    produce the same fingerprint for the same thresholds.
    """
    if profile is None:
        return None
    canonical = json.dumps(
        {key: profile[key] for key in _FINGERPRINT_KEYS if key in profile},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
