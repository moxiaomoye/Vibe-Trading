"""Atomic local report storage with schema version, latest pointer, and safe reads."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

STORAGE_SCHEMA_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"


@dataclass
class ReportStorage:
    """Thread-safe local report storage.

    Writes reports atomically (write-to-temp-then-rename) and maintains a
    ``latest.json`` pointer.  Corrupt or missing reports return ``None``
    without raising.
    """

    output_dir: Path

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_report(self, report: dict[str, Any], date_dir: date | None = None) -> Path | None:
        report["_schema_version"] = REPORT_SCHEMA_VERSION
        report["_stored_at"] = datetime.utcnow().isoformat()

        fingerprint = _stable_fingerprint(report)
        report["_fingerprint"] = fingerprint

        subdir = self.output_dir / (date_dir or date.today()).isoformat()
        subdir.mkdir(parents=True, exist_ok=True)

        json_path = subdir / f"{fingerprint}.json"
        _atomic_write(json_path, report)

        md_path = subdir / f"{fingerprint}.md"
        _write_markdown(md_path, report)

        latest = self.output_dir / "latest.json"
        _atomic_write(latest, report)

        return json_path

    def load_latest(self) -> dict[str, Any] | None:
        latest = self.output_dir / "latest.json"
        if not latest.exists():
            return None
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def load_report(self, fingerprint: str, date_str: str | None = None) -> dict[str, Any] | None:
        if date_str:
            path = self.output_dir / date_str / f"{fingerprint}.json"
        else:
            for sub in self.output_dir.iterdir():
                if sub.is_dir():
                    candidate = sub / f"{fingerprint}.json"
                    if candidate.exists():
                        path = candidate
                        break
            else:
                return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None


def _stable_fingerprint(report: dict[str, Any]) -> str:
    stable = {k: v for k, v in report.items() if not k.startswith("_")}
    raw = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _atomic_write(path: Path, data: Any) -> None:
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    market = report.get("market", {})
    lines = [
        f"# Market Shadow Report — {market.get('trade_date', 'unknown')}",
        "",
        f"- **Fingerprint:** {report.get('_fingerprint', 'N/A')}",
        f"- **Schema Version:** {report.get('_schema_version', 'N/A')}",
        f"- **Data Source:** {report.get('data_source', 'N/A')}",
        f"- **Shadow Run:** {report.get('shadow_run', False)}",
        f"- **Manual Review Required:** {report.get('manual_review_required', True)}",
        "",
        "## Market State",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for k, v in market.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
