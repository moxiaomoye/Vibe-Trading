"""Vibe-Trading Autonomous Development Loop — supervisor state machine.

Reads ``tasks/roadmap.yaml`` (the task queue), tracks per-task status, and
prints a dispatch brief for the next highest-priority task. It does not
develop anything itself; it keeps the loop resumable across sessions so a
fresh ``opencode`` session can always answer "what is next?".

Usage:
    python automation/long_runner.py status
    python automation/long_runner.py next          # mark in_progress + print brief
    python automation/long_runner.py done <id>     # mark done
    python automation/long_runner.py blocked <id> <reason>
    python automation/long_runner.py check         # health snapshot

Local-only: this tool never touches git remotes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "tasks" / "roadmap.yaml"
STATE_DOC = ROOT / "docs" / "status" / "current_state.md"

STATUSES = ("pending", "in_progress", "done", "blocked")


def _load() -> dict[str, Any]:
    return yaml.safe_load(ROADMAP.read_text(encoding="utf-8")) or {}


def _save(data: dict[str, Any]) -> None:
    ROADMAP.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _queue(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.get("queue", [])


def _find(queue: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    return next((item for item in queue if item.get("id") == task_id), None)


def _next_task(queue: list[dict[str, Any]]) -> dict[str, Any] | None:
    order = sorted(queue, key=lambda item: (item.get("priority", 99)))
    for item in order:
        if item.get("status") == "pending":
            return item
    return None


def cmd_status(data: dict[str, Any]) -> int:
    print(f"roadmap schema: {data.get('schema_version')}")
    for item in _queue(data):
        marker = {"pending": "   ", "in_progress": ">> ", "done": "ok ", "blocked": "XX "}[
            item.get("status", "pending")
        ]
        print(
            f"{marker} P{item.get('priority', 99)} {item.get('id')}: "
            f"{item.get('title')} [{item.get('status')}]"
        )
    return 0


def cmd_next(data: dict[str, Any]) -> int:
    task = _next_task(_queue(data))
    if task is None:
        print("queue empty: no pending tasks. All milestones done.")
        return 0
    task["status"] = "in_progress"
    _save(data)
    print(f"=== NEXT TASK: {task['id']} ===")
    print(f"phase:   {task.get('phase')}")
    print(f"title:   {task.get('title')}")
    print(f"goal:    {task.get('goal')}")
    for line in task.get("constraints", []):
        print(f"constraint: {line}")
    print("acceptance:")
    for line in task.get("acceptance", []):
        print(f"  - {line}")
    print("=== discipline: investigate -> design -> implement -> test -> "
          "regression -> git diff --check -> local commit -> update current_state.md")
    return 0


def cmd_done(data: dict[str, Any], task_id: str) -> int:
    task = _find(_queue(data), task_id)
    if task is None:
        print(f"unknown task id: {task_id}")
        return 1
    task["status"] = "done"
    _save(data)
    print(f"{task_id}: done")
    return 0


def cmd_blocked(data: dict[str, Any], task_id: str, reason: str) -> int:
    task = _find(_queue(data), task_id)
    if task is None:
        print(f"unknown task id: {task_id}")
        return 1
    task["status"] = "blocked"
    task["block_reason"] = reason
    _save(data)
    print(f"{task_id}: blocked ({reason})")
    return 0


def cmd_check(data: dict[str, Any]) -> int:
    import subprocess

    status = subprocess.run(
        ["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    print("git working tree:" + (" clean" if not status else f"\n{status}"))
    print(f"roadmap file: {ROADMAP} ({'exists' if ROADMAP.exists() else 'MISSING'})")
    print(f"current_state: {STATE_DOC} ({'exists' if STATE_DOC.exists() else 'MISSING'})")
    queue = _queue(data)
    print(f"queue: {len(queue)} tasks, "
          f"{sum(1 for t in queue if t.get('status') == 'done')} done, "
          f"{sum(1 for t in queue if t.get('status') == 'pending')} pending")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show queue")
    sub.add_parser("next", help="mark next pending task in_progress and print brief")
    sub.add_parser("check", help="health snapshot")
    p_done = sub.add_parser("done", help="mark a task done")
    p_done.add_argument("task_id")
    p_blocked = sub.add_parser("blocked", help="mark a task blocked")
    p_blocked.add_argument("task_id")
    p_blocked.add_argument("reason")
    args = parser.parse_args(argv)

    data = _load()
    if args.command == "status":
        return cmd_status(data)
    if args.command == "next":
        return cmd_next(data)
    if args.command == "done":
        return cmd_done(data, args.task_id)
    if args.command == "blocked":
        return cmd_blocked(data, args.task_id, args.reason)
    if args.command == "check":
        return cmd_check(data)
    return 1


if __name__ == "__main__":
    sys.exit(main())
