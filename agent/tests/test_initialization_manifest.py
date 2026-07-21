from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from src.investment_research.application.initialization_manifest import ThesisInitializationManifest
from src.investment_research.contracts import EvidenceDirection, ThesisStatus
from src.investment_research.evidence.associations import EvidenceAssociation, EvidenceSubjectType


def _payload() -> dict:
    payload = {
        "manifest_version": 3,
        "thesis_id": "thesis-ai-infrastructure",
        "information_cutoff": "2026-07-21T09:30:00+00:00",
        "initialized_at": "2026-07-21T10:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "support-1",
                "provider": "fixture",
                "source_locator": "fixture://support-1",
                "title": "Supporting evidence",
                "summary": "Capital expenditure remains durable.",
                "published_at": "2026-07-20T08:00:00+00:00",
                "available_at": "2026-07-20T09:00:00+00:00",
                "observed_at": "2026-07-21T08:00:00+00:00",
            },
            {
                "evidence_id": "counter-1",
                "provider": "fixture",
                "source_locator": "fixture://counter-1",
                "title": "Counter evidence",
                "summary": "Supply constraints could delay deployment.",
                "published_at": "2026-07-20T08:00:00+00:00",
                "available_at": "2026-07-20T09:00:00+00:00",
                "observed_at": "2026-07-21T08:00:00+00:00",
                "quality_warnings": ["fixture only"],
            },
        ],
        "associations": [
            {
                "evidence_id": "support-1",
                "direction": "supporting",
                "assessed_at": "2026-07-21T09:30:00+00:00",
                "assessor": "analyst-1",
                "rationale": "CapEx evidence supports this Thesis.",
            },
            {
                "evidence_id": "counter-1",
                "direction": "counter",
                "assessed_at": "2026-07-21T09:30:00+00:00",
                "assessor": "analyst-1",
                "rationale": "Supply constraints oppose this Thesis.",
            },
        ],
        "proposal": {
            "status": "active",
            "core_claim": "AI infrastructure demand is supported by durable capital expenditure.",
            "confidence": 0.76,
            "supporting_evidence_ids": ["support-1"],
            "counter_evidence_ids": ["counter-1"],
            "catalysts": ["capital expenditure acceleration"],
            "kill_criteria": ["multi-quarter capital expenditure contraction"],
            "change_summary": "Initial evidence-backed Thesis version.",
            "next_review_at": "2026-08-20T10:00:00+00:00",
            "initializer": "research-committee-v2",
            "approval_reference": "approval://fixture/initialization-1",
            "evidence_set_review_id": "evidence-set-review-1",
        },
    }
    for item in payload["associations"]:
        association = EvidenceAssociation.create(
            item["evidence_id"],
            EvidenceSubjectType.THESIS,
            payload["thesis_id"],
            EvidenceDirection(item["direction"]),
            datetime.fromisoformat(item["assessed_at"]),
            item["assessor"],
            item["rationale"],
        )
        item["association_id"] = association.association_id
    return payload


def _change_support_to_counter(payload: dict) -> None:
    item = payload["associations"][0]
    item["direction"] = "counter"
    item["association_id"] = EvidenceAssociation.create(
        item["evidence_id"], EvidenceSubjectType.THESIS, payload["thesis_id"],
        EvidenceDirection.COUNTER, datetime.fromisoformat(item["assessed_at"]),
        item["assessor"], item["rationale"],
    ).association_id


def test_manifest_parses_valid_point_in_time_research_contract() -> None:
    manifest = ThesisInitializationManifest.from_dict(_payload())

    assert manifest.thesis_id == "thesis-ai-infrastructure"
    assert manifest.proposal.status == ThesisStatus.ACTIVE
    assert manifest.evidence[0].direction == EvidenceDirection.NEUTRAL
    assert manifest.associations[0].direction == EvidenceDirection.SUPPORTING
    assert len(manifest.evidence[0].content_hash) == 64


def test_evidence_set_identity_is_stable_when_manifest_order_changes() -> None:
    original = ThesisInitializationManifest.from_dict(_payload())
    reordered_payload = _payload()
    reordered_payload["evidence"].reverse()
    reordered = ThesisInitializationManifest.from_dict(reordered_payload)

    assert reordered.evidence_set.evidence_set_id == original.evidence_set.evidence_set_id
    assert reordered.evidence_set.evidence_ids == ("counter-1", "support-1")


def test_manifest_loads_utf8_json_file(tmp_path: Path) -> None:
    path = tmp_path / "initialization.json"
    path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
    assert ThesisInitializationManifest.load(path).proposal.confidence == 0.76


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("thesis_id"), "missing fields"),
        (lambda value: value.update({"unexpected": True}), "unknown fields"),
        (lambda value: value.update({"manifest_version": 2}), "manifest_version must be 3"),
        (lambda value: value.update({"information_cutoff": "2026-07-21T09:00:00"}), "timezone"),
        (lambda value: value.update({"evidence": []}), "requires evidence"),
        (lambda value: value["evidence"][0].update({"unexpected": True}), "unknown fields"),
        (
            lambda value: value["evidence"][0].update(
                {
                    "available_at": "2026-07-22T09:00:00+00:00",
                    "observed_at": "2026-07-22T10:00:00+00:00",
                }
            ),
            "unavailable",
        ),
        (lambda value: value["proposal"].update({"status": "draft"}), "active or weakening"),
        (lambda value: value.update({"associations": []}), "requires contextual"),
        (_change_support_to_counter, "supporting association"),
        (lambda value: value["associations"][0].update({"evidence_id": "missing"}), "association_id"),
        (lambda value: value["associations"][0].update({"association_id": "wrong"}), "association_id"),
        (lambda value: value["proposal"].update({"catalysts": "not-an-array"}), "non-empty array"),
        (lambda value: value["proposal"].update({"supporting_evidence_ids": ["support-1", "support-1"]}), "unique"),
    ],
)
def test_manifest_rejects_non_strict_or_point_in_time_invalid_payload(mutation, message: str) -> None:
    payload = deepcopy(_payload())
    mutation(payload)
    with pytest.raises((ValueError, KeyError), match=message):
        ThesisInitializationManifest.from_dict(payload)


def test_schema_is_valid_json_and_has_no_open_top_level_fields() -> None:
    schema_path = Path(__file__).parents[1] / "schemas" / "thesis_initialization.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["evidence"]["items"]["additionalProperties"] is False
    assert schema["properties"]["associations"]["items"]["additionalProperties"] is False


def test_example_manifest_is_a_non_executable_template() -> None:
    example_path = Path(__file__).parents[1] / "schemas" / "thesis_initialization.example.json"
    with pytest.raises(ValueError, match="example-only evidence"):
        ThesisInitializationManifest.load(example_path)
