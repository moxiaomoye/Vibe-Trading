from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.investment_research.operations.vibe_research import VibeResearchCoordinator


class _Store:
    def __init__(self, states):
        self.states = list(states)
        self.index = 0

    def get_attempt(self, _session_id, _attempt_id):
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return SimpleNamespace(
            status=state,
            created_at="2026-07-30T10:00:00+00:00",
            summary="completed research" if state == "completed" else None,
            error="upstream failed" if state == "failed" else None,
        )


class _Service:
    def __init__(self, states):
        self.store = _Store(states)
        self.cancelled = False

    def create_session(self, **_kwargs):
        return SimpleNamespace(session_id="session-1")

    async def send_message(self, *_args, **_kwargs):
        return {"attempt_id": "attempt-1"}

    def cancel_current(self, _session_id):
        self.cancelled = True
        return True


def test_coordinator_records_completed_attempt_without_storing_prompt(tmp_path):
    async def run():
        coordinator = VibeResearchCoordinator(
            tmp_path / "state.json",
            timeout_seconds=1,
            poll_interval_seconds=0.001,
        )
        result = await coordinator.dispatch(
            _Service(["pending", "running", "completed"]),
            report_date="2026-07-30",
            prompt="sensitive research prompt",
            title="Daily research",
        )
        assert result["status"] == "accepted"
        for _ in range(100):
            status = coordinator.status()
            if status["status"] == "completed":
                break
            await asyncio.sleep(0.005)
        assert status["status"] == "completed"
        assert status["result_available"] is True
        assert "prompt" not in status
        assert "sensitive" not in (tmp_path / "state.json").read_text(encoding="utf-8")

    asyncio.run(run())


def test_coordinator_times_out_and_requests_cancellation(tmp_path):
    async def run():
        service = _Service(["running"])
        coordinator = VibeResearchCoordinator(
            tmp_path / "state.json",
            timeout_seconds=0.01,
            poll_interval_seconds=0.001,
        )
        await coordinator.dispatch(
            service,
            report_date="2026-07-30",
            prompt="research",
            title="Daily research",
        )
        # Windows' default asyncio clock can advance in relatively coarse
        # steps, so allow enough wall-clock time for the deliberately tiny
        # coordinator timeout to elapse.
        for _ in range(1000):
            if coordinator.status()["status"] == "timed_out":
                break
            await asyncio.sleep(0.005)
        assert coordinator.status()["status"] == "timed_out"
        assert service.cancelled is True

    asyncio.run(run())


def test_coordinator_marks_persisted_active_attempt_interrupted(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        '{"status":"running","session_id":"s1","attempt_id":"a1"}',
        encoding="utf-8",
    )

    coordinator = VibeResearchCoordinator(path)

    assert coordinator.status()["status"] == "interrupted"
    assert coordinator.status()["error"] == (
        "process_restarted_before_attempt_reached_a_terminal_state"
    )
