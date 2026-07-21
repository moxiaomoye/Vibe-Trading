"""Parse a strict JSON Thesis-initialization manifest into validated domain objects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..contracts import EvidenceDirection, ThesisStatus
from ..evidence.associations import EvidenceAssociation, EvidenceSubjectType
from ..evidence.models import Evidence, EvidenceSet
from .initialization import ThesisInitializationProposal


_MANIFEST_FIELDS = {
    "manifest_version", "thesis_id", "information_cutoff", "initialized_at",
    "evidence", "associations", "proposal",
}
_EVIDENCE_FIELDS = {
    "evidence_id", "provider", "source_locator", "title", "summary",
    "published_at", "available_at", "observed_at", "content_hash", "quality_warnings",
}
_EVIDENCE_REQUIRED_FIELDS = _EVIDENCE_FIELDS - {"content_hash", "quality_warnings"}
_PROPOSAL_FIELDS = {
    "status", "core_claim", "confidence", "supporting_evidence_ids", "counter_evidence_ids",
    "catalysts", "kill_criteria", "change_summary", "next_review_at", "initializer",
    "approval_reference",
    "evidence_set_review_id",
}
_ASSOCIATION_FIELDS = {
    "association_id", "evidence_id", "direction", "assessed_at", "assessor", "rationale",
}


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _validate_fields(
    payload: dict[str, Any], allowed: set[str], required: set[str], field_name: str,
) -> None:
    missing = required - set(payload)
    if missing:
        raise ValueError(f"{field_name} missing fields: {sorted(missing)}")
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{field_name} contains unknown fields: {sorted(unknown)}")


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty array")
    result = tuple(_required_text(item, field_name) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must contain unique values")
    return result


def _aware(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed


@dataclass(frozen=True, slots=True)
class ThesisInitializationManifest:
    thesis_id: str
    evidence_set: EvidenceSet
    evidence: tuple[Evidence, ...]
    associations: tuple[EvidenceAssociation, ...]
    proposal: ThesisInitializationProposal
    initialized_at: datetime

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ThesisInitializationManifest":
        payload = _require_mapping(payload, "initialization manifest")
        _validate_fields(payload, _MANIFEST_FIELDS, _MANIFEST_FIELDS, "initialization manifest")
        if payload["manifest_version"] != 3:
            raise ValueError("manifest_version must be 3")
        thesis_id = _required_text(payload["thesis_id"], "thesis_id")
        cutoff = _aware(payload["information_cutoff"], "information_cutoff")
        initialized_at = _aware(payload["initialized_at"], "initialized_at")
        if not isinstance(payload["evidence"], list) or not payload["evidence"]:
            raise ValueError("initialization manifest requires evidence")
        evidence = tuple(cls._evidence(item) for item in payload["evidence"])
        evidence_ids = tuple(sorted(item.evidence_id for item in evidence))
        set_key = json.dumps(
            {"thesis_id": thesis_id, "cutoff": cutoff.isoformat(), "evidence_ids": evidence_ids},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        evidence_set = EvidenceSet(
            str(uuid5(NAMESPACE_URL, f"thesis-evidence-set:{set_key}")), thesis_id, cutoff,
            evidence_ids, initialized_at,
        )
        proposal_payload = _require_mapping(payload["proposal"], "proposal")
        _validate_fields(proposal_payload, _PROPOSAL_FIELDS, _PROPOSAL_FIELDS, "proposal")
        status = ThesisStatus(proposal_payload["status"])
        if status not in {ThesisStatus.ACTIVE, ThesisStatus.WEAKENING}:
            raise ValueError("proposal status must be active or weakening")
        proposal = ThesisInitializationProposal(
            status=status,
            core_claim=_required_text(proposal_payload["core_claim"], "core_claim"),
            confidence=float(proposal_payload["confidence"]),
            supporting_evidence_ids=_string_tuple(
                proposal_payload["supporting_evidence_ids"], "supporting_evidence_ids"
            ),
            counter_evidence_ids=_string_tuple(
                proposal_payload["counter_evidence_ids"], "counter_evidence_ids"
            ),
            catalysts=_string_tuple(proposal_payload["catalysts"], "catalysts"),
            kill_criteria=_string_tuple(proposal_payload["kill_criteria"], "kill_criteria"),
            change_summary=_required_text(proposal_payload["change_summary"], "change_summary"),
            next_review_at=_aware(proposal_payload["next_review_at"], "next_review_at"),
            initializer=_required_text(proposal_payload["initializer"], "initializer"),
            approval_reference=_required_text(proposal_payload["approval_reference"], "approval_reference"),
            evidence_set_review_id=_required_text(
                proposal_payload["evidence_set_review_id"], "evidence_set_review_id"
            ),
        )
        if not isinstance(payload["associations"], list) or not payload["associations"]:
            raise ValueError("initialization manifest requires contextual evidence associations")
        associations = tuple(
            cls._association(item, thesis_id) for item in payload["associations"]
        )
        association_by_evidence = {item.evidence_id: item for item in associations}
        if len(association_by_evidence) != len(associations):
            raise ValueError("initialization manifest requires one association per evidence item")
        unknown_associations = set(association_by_evidence) - set(evidence_ids)
        if unknown_associations:
            raise ValueError(f"associations reference unknown evidence: {sorted(unknown_associations)}")
        referenced = set(proposal.supporting_evidence_ids) | set(proposal.counter_evidence_ids)
        missing_associations = referenced - set(association_by_evidence)
        if missing_associations:
            raise ValueError(f"proposal evidence lacks contextual associations: {sorted(missing_associations)}")
        for evidence_id in proposal.supporting_evidence_ids:
            if association_by_evidence[evidence_id].direction != EvidenceDirection.SUPPORTING:
                raise ValueError("supporting proposal evidence must have a supporting association")
        for evidence_id in proposal.counter_evidence_ids:
            if association_by_evidence[evidence_id].direction != EvidenceDirection.COUNTER:
                raise ValueError("counter proposal evidence must have a counter association")
        if any(item.assessed_at > cutoff for item in associations):
            raise ValueError("evidence associations cannot be assessed after the information cutoff")
        evidence_set.validate_point_in_time(evidence)
        return cls(thesis_id, evidence_set, evidence, associations, proposal, initialized_at)

    @classmethod
    def load(cls, path: Path) -> "ThesisInitializationManifest":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _evidence(payload: dict[str, Any]) -> Evidence:
        payload = _require_mapping(payload, "evidence item")
        _validate_fields(payload, _EVIDENCE_FIELDS, _EVIDENCE_REQUIRED_FIELDS, "evidence item")
        summary = _required_text(payload["summary"], "summary")
        provider = _required_text(payload["provider"], "provider")
        if provider == "example-only":
            raise ValueError("example-only evidence must be replaced before Thesis initialization")
        content_hash = str(payload.get("content_hash") or hashlib.sha256(summary.encode("utf-8")).hexdigest())
        return Evidence(
            evidence_id=_required_text(payload["evidence_id"], "evidence_id"),
            provider=provider,
            source_locator=_required_text(payload["source_locator"], "source_locator"),
            title=_required_text(payload["title"], "title"),
            summary=summary,
            direction=EvidenceDirection.NEUTRAL,
            published_at=_aware(payload["published_at"], "published_at"),
            available_at=_aware(payload["available_at"], "available_at"),
            observed_at=_aware(payload["observed_at"], "observed_at"),
            content_hash=content_hash,
            quality_warnings=tuple(
                _required_text(item, "quality_warnings")
                for item in payload.get("quality_warnings", [])
            ),
        )

    @staticmethod
    def _association(payload: dict[str, Any], thesis_id: str) -> EvidenceAssociation:
        payload = _require_mapping(payload, "evidence association")
        _validate_fields(payload, _ASSOCIATION_FIELDS, _ASSOCIATION_FIELDS, "evidence association")
        association = EvidenceAssociation.create(
            _required_text(payload["evidence_id"], "association evidence_id"),
            EvidenceSubjectType.THESIS,
            thesis_id,
            EvidenceDirection(payload["direction"]),
            _aware(payload["assessed_at"], "assessed_at"),
            _required_text(payload["assessor"], "assessor"),
            _required_text(payload["rationale"], "rationale"),
        )
        association_id = _required_text(payload["association_id"], "association_id")
        if association.association_id != association_id:
            raise ValueError("association_id does not match the contextual association content")
        return association
