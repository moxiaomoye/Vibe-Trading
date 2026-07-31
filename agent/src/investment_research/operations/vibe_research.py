"""Bounded coordination for optional Vibe deep-research attempts.

The coordinator deliberately does not interpret or promote research output.
It only records the lifecycle of a core SessionService attempt so the daily
research pipeline can distinguish accepted work from completed work.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TERMINAL_ATTEMPT_STATES = {"completed", "failed", "cancelled"}
_ACTIVE_COORDINATOR_STATES = {"accepted", "running"}


class VibeResearchCoordinator:
    """Track one optional Vibe attempt without blocking the daily report."""

    def __init__(
        self,
        state_path: Path,
        *,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.state_path = state_path
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._tasks: set[asyncio.Task[None]] = set()
        self._state = self._load_state()
        if self._state.get("status") in _ACTIVE_COORDINATOR_STATES:
            self._state = {
                **self._state,
                "status": "interrupted",
                "completed_at": _utc_now(),
                "error": "process_restarted_before_attempt_reached_a_terminal_state",
            }
            self._save_state()

    async def dispatch(
        self,
        service: Any,
        *,
        report_date: str,
        prompt: str,
        title: str,
    ) -> dict[str, Any]:
        """Submit one core Vibe session attempt and start a bounded watcher."""
        if not prompt.strip():
            return self._public_state(
                {
                    "status": "not_dispatched",
                    "report_date": report_date,
                    "error": "empty_research_prompt",
                }
            )
        if (
            self._state.get("report_date") == report_date
            and self._state.get("status") in _ACTIVE_COORDINATOR_STATES
        ):
            return self.status()

        session = service.create_session(
            title=title,
            config={"include_shell_tools": False, "research_mode": "supporting_only"},
        )
        accepted = await service.send_message(
            session.session_id,
            prompt,
            include_shell_tools=False,
        )
        attempt_id = str(accepted.get("attempt_id") or "")
        if not attempt_id:
            self._state = {
                "status": "failed",
                "report_date": report_date,
                "session_id": session.session_id,
                "attempt_id": None,
                "accepted_at": _utc_now(),
                "completed_at": _utc_now(),
                "error": "session_service_returned_no_attempt_id",
                "result_available": False,
            }
            self._save_state()
            return self.status()

        self._state = {
            "status": "accepted",
            "report_date": report_date,
            "session_id": session.session_id,
            "attempt_id": attempt_id,
            "accepted_at": _utc_now(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result_available": False,
            "result_policy": (
                "Vibe analysis is supporting research and cannot independently "
                "promote a final Research Candidate."
            ),
        }
        self._save_state()
        task = asyncio.create_task(
            self._watch(service, session.session_id, attempt_id),
            name=f"vibe-research-{attempt_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return self.status()

    def status(self) -> dict[str, Any]:
        """Return JSON-safe state without prompts, credentials, or output text."""
        if not self._state:
            return {
                "status": "not_started",
                "session_id": None,
                "attempt_id": None,
                "result_available": False,
            }
        return self._public_state(self._state)

    async def _watch(self, service: Any, session_id: str, attempt_id: str) -> None:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            while asyncio.get_running_loop().time() < deadline:
                attempt = service.store.get_attempt(session_id, attempt_id)
                if attempt is None:
                    self._finish("failed", error="attempt_record_unavailable")
                    return
                attempt_status = _status_value(attempt.status)
                if attempt_status == "running" and self._state.get("status") != "running":
                    self._state = {
                        **self._state,
                        "status": "running",
                        "started_at": getattr(attempt, "created_at", None) or _utc_now(),
                    }
                    self._save_state()
                if attempt_status in _TERMINAL_ATTEMPT_STATES:
                    self._finish(
                        attempt_status,
                        error=getattr(attempt, "error", None),
                        result_available=bool(getattr(attempt, "summary", None)),
                    )
                    return
                await asyncio.sleep(self.poll_interval_seconds)

            service.cancel_current(session_id)
            self._finish(
                "timed_out",
                error=f"deep_research_exceeded_{int(self.timeout_seconds)}_seconds",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._finish("failed", error=type(exc).__name__)

    def _finish(
        self,
        status: str,
        *,
        error: str | None = None,
        result_available: bool = False,
    ) -> None:
        self._state = {
            **self._state,
            "status": status,
            "completed_at": _utc_now(),
            "error": error,
            "result_available": result_available,
        }
        self._save_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _public_state(state: dict[str, Any]) -> dict[str, Any]:
        allowed = (
            "status",
            "report_date",
            "session_id",
            "attempt_id",
            "accepted_at",
            "started_at",
            "completed_at",
            "error",
            "result_available",
            "result_policy",
        )
        return {key: state.get(key) for key in allowed if key in state}


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
