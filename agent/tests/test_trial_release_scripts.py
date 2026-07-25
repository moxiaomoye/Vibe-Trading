"""Safety contracts for the one-command Trial Release scripts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_start_script_reuses_compose_image_and_keeps_side_effects_disabled() -> None:
    source = _script("start_market_shadow.ps1")

    assert "pip install" not in source
    assert "docker compose" in source
    assert "--no-build" in source
    assert 'INVESTMENT_RESEARCH_ROUTES_ENABLED: "true"' in source
    assert 'PANIC_SHADOW_REPORT_API_ENABLED: "true"' in source
    assert 'VIBE_TRADING_ENABLE_SCHEDULER: "false"' in source
    assert 'VIBE_TRADING_CHANNELS_AUTO_START: "false"' in source
    assert 'VIBE_RESEARCH_DELIVERY_MODE: "disabled"' in source
    assert "http://127.0.0.1:8899/investment-research" in source
    assert ".State.Health" in source
    assert '@("healthy", "ok")' in source


def test_stop_script_preserves_containers_volumes_images_and_reports() -> None:
    source = _script("stop_market_shadow.ps1").lower()

    assert " compose " in source
    assert " stop " in source
    assert "down" not in source
    assert "volume rm" not in source
    assert "docker rm" not in source
    assert "remove-item" not in source


def test_diagnostics_is_read_only_and_does_not_dump_container_environment() -> None:
    source = _script("collect_shadow_diagnostics.ps1").lower()

    assert "docker inspect" in source
    assert "down" not in source
    assert " stop " not in source
    assert "volume rm" not in source
    assert "docker rm" not in source
    assert "{{json .config.env}}" not in source
    assert ".env" not in source
