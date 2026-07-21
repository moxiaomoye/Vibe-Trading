"""Import the owner-reviewable AI infrastructure Thesis blueprint identities."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.config.accessor import get_env_config
from src.config.paths import get_data_dir
from src.investment_research.repositories.sqlite import SQLiteResearchRepository
from src.investment_research.thesis.seeds import import_thesis_identities, load_blueprint_manifest


def main() -> int:
    configured = get_env_config().paths.vibe_investment_research_db_path.strip()
    database_path = Path(configured).expanduser() if configured else get_data_dir() / "investment_research_v2.sqlite3"
    repository = SQLiteResearchRepository(database_path)
    imported = import_thesis_identities(
        repository,
        load_blueprint_manifest(),
        datetime.now(timezone.utc),
    )
    print(f"Investment Research V2 database: {database_path}")
    print(f"Imported thesis identities: {len(imported)}")
    print(f"Total thesis identities: {len(repository.list_theses())}")
    print("Blueprints remain uninitialized until evidence-backed owner review creates ThesisVersion 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
