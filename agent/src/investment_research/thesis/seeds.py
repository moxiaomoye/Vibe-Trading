"""Load and validate owner-reviewable thesis blueprints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..contracts import ThesisScope
from .models import Thesis


@dataclass(frozen=True, slots=True)
class ThesisBlueprint:
    thesis_id: str
    name: str
    parent_thesis_id: str | None
    scope: ThesisScope
    research_question: str
    proposed_core_claim: str
    causal_chain: tuple[str, ...]
    key_assumptions: tuple[str, ...]
    strongest_counter_questions: tuple[str, ...]
    draft_kill_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThesisBlueprintManifest:
    manifest_id: str
    version: int
    blueprints: tuple[ThesisBlueprint, ...]


def default_ai_infrastructure_manifest_path() -> Path:
    return Path(__file__).with_name("seeds") / "ai_infrastructure_v1.json"


def load_blueprint_manifest(path: Path | None = None) -> ThesisBlueprintManifest:
    source = path or default_ai_infrastructure_manifest_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    blueprints = tuple(
        ThesisBlueprint(
            thesis_id=item["thesis_id"],
            name=item["name"],
            parent_thesis_id=item.get("parent_thesis_id"),
            scope=ThesisScope(item["scope"]),
            research_question=item["research_question"],
            proposed_core_claim=item["proposed_core_claim"],
            causal_chain=tuple(item["causal_chain"]),
            key_assumptions=tuple(item["key_assumptions"]),
            strongest_counter_questions=tuple(item["strongest_counter_questions"]),
            draft_kill_criteria=tuple(item["draft_kill_criteria"]),
        )
        for item in payload["blueprints"]
    )
    manifest = ThesisBlueprintManifest(payload["manifest_id"], int(payload["version"]), blueprints)
    validate_blueprint_manifest(manifest)
    return manifest


def validate_blueprint_manifest(manifest: ThesisBlueprintManifest) -> None:
    if not manifest.manifest_id or manifest.version < 1:
        raise ValueError("manifest id and positive version are required")
    if not 5 <= len(manifest.blueprints) <= 8:
        raise ValueError("the initial thesis tree must contain 5 to 8 nodes")
    by_id = {item.thesis_id: item for item in manifest.blueprints}
    if len(by_id) != len(manifest.blueprints):
        raise ValueError("thesis blueprint ids must be unique")
    roots = [item for item in manifest.blueprints if item.parent_thesis_id is None]
    if len(roots) != 1:
        raise ValueError("the initial thesis tree must have exactly one root")
    for item in manifest.blueprints:
        if item.parent_thesis_id is not None and item.parent_thesis_id not in by_id:
            raise ValueError(f"unknown parent thesis: {item.parent_thesis_id}")
        if not item.causal_chain or not item.key_assumptions or not item.strongest_counter_questions:
            raise ValueError(f"blueprint {item.thesis_id} lacks a balanced research frame")
        if not item.draft_kill_criteria:
            raise ValueError(f"blueprint {item.thesis_id} lacks draft kill criteria")

    for item in manifest.blueprints:
        seen: set[str] = set()
        current: ThesisBlueprint | None = item
        while current is not None:
            if current.thesis_id in seen:
                raise ValueError("thesis blueprint tree contains a cycle")
            seen.add(current.thesis_id)
            current = by_id.get(current.parent_thesis_id) if current.parent_thesis_id else None


class ThesisIdentityRepository(Protocol):
    def save_thesis(self, thesis: Thesis) -> None: ...

    def get_thesis(self, thesis_id: str) -> Thesis: ...


def import_thesis_identities(
    repository: ThesisIdentityRepository,
    manifest: ThesisBlueprintManifest,
    created_at: datetime,
) -> tuple[Thesis, ...]:
    """Idempotently import identities; blueprints remain unverified until evidence review."""
    imported: list[Thesis] = []
    for blueprint in manifest.blueprints:
        thesis = Thesis(
            thesis_id=blueprint.thesis_id,
            name=blueprint.name,
            parent_thesis_id=blueprint.parent_thesis_id,
            created_at=created_at,
            scope=blueprint.scope,
        )
        try:
            existing = repository.get_thesis(thesis.thesis_id)
        except KeyError:
            repository.save_thesis(thesis)
            imported.append(thesis)
            continue
        if existing.name != thesis.name or existing.parent_thesis_id != thesis.parent_thesis_id or existing.scope != thesis.scope:
            raise ValueError(f"existing thesis identity conflicts with blueprint: {thesis.thesis_id}")
    return tuple(imported)

