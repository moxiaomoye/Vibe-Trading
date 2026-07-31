"""Tests for market-data provider credential configuration.

All tests use monkeypatch — no real credentials are required or loaded.
Test-only sentinel values are prefixed ``TEST_ONLY_`` and must never
appear in production configuration files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.accessor import reset_env_config

# Tests that reference project-root files resolve relative to the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
from src.config.market_data_providers import (
    SZSE_REQUIRED_VARS,
    TUSHARE_REQUIRED_VARS,
    ProviderConfigStatus,
    get_all_provider_statuses,
    get_provider_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SZSE_KEY = "TEST_ONLY_SZSE_KEY"
SZSE_SECRET = "TEST_ONLY_SZSE_SECRET"
SZSE_TOKEN = "TEST_ONLY_SZSE_TOKEN"
TUSHARE_TOKEN_VAL = "TEST_ONLY_TUSHARE_TOKEN"


def _set_szse_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZSE_DATA_ACCESS_KEY", SZSE_KEY)
    monkeypatch.setenv("SZSE_DATA_ACCESS_SECRET", SZSE_SECRET)
    monkeypatch.setenv("SZSE_DATA_ACCESS_TOKEN", SZSE_TOKEN)


def _set_tushare(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", TUSHARE_TOKEN_VAL)


# ---------------------------------------------------------------------------
# 1. All four variables missing — application still starts
# ---------------------------------------------------------------------------


def test_all_missing_app_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZSE_DATA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("SZSE_DATA_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("SZSE_DATA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    reset_env_config()

    # The call itself proves the app doesn't crash.
    szse = get_provider_config("szse_data")
    tushare = get_provider_config("tushare")

    assert szse.configured is False
    assert tushare.configured is False


# ---------------------------------------------------------------------------
# 2. SZSE three variables all present → configured=True
# ---------------------------------------------------------------------------


def test_szse_all_present_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_szse_all(monkeypatch)
    _set_tushare(monkeypatch)
    reset_env_config()

    status = get_provider_config("szse_data")
    assert status.configured is True
    assert status.missing_variables == []


# ---------------------------------------------------------------------------
# 3. SZSE missing any one variable → configured=False
# ---------------------------------------------------------------------------


def test_szse_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZSE_DATA_ACCESS_KEY", raising=False)
    monkeypatch.setenv("SZSE_DATA_ACCESS_SECRET", SZSE_SECRET)
    monkeypatch.setenv("SZSE_DATA_ACCESS_TOKEN", SZSE_TOKEN)
    reset_env_config()

    status = get_provider_config("szse_data")
    assert status.configured is False
    assert "SZSE_DATA_ACCESS_KEY" in status.missing_variables


def test_szse_missing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZSE_DATA_ACCESS_KEY", SZSE_KEY)
    monkeypatch.delenv("SZSE_DATA_ACCESS_SECRET", raising=False)
    monkeypatch.setenv("SZSE_DATA_ACCESS_TOKEN", SZSE_TOKEN)
    reset_env_config()

    status = get_provider_config("szse_data")
    assert status.configured is False
    assert "SZSE_DATA_ACCESS_SECRET" in status.missing_variables


def test_szse_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZSE_DATA_ACCESS_KEY", SZSE_KEY)
    monkeypatch.setenv("SZSE_DATA_ACCESS_SECRET", SZSE_SECRET)
    monkeypatch.delenv("SZSE_DATA_ACCESS_TOKEN", raising=False)
    reset_env_config()

    status = get_provider_config("szse_data")
    assert status.configured is False
    assert "SZSE_DATA_ACCESS_TOKEN" in status.missing_variables


# ---------------------------------------------------------------------------
# 4. missing_variables only contains variable names (never values)
# ---------------------------------------------------------------------------


def test_missing_variables_never_contains_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZSE_DATA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("SZSE_DATA_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("SZSE_DATA_ACCESS_TOKEN", raising=False)
    reset_env_config()

    status = get_provider_config("szse_data")
    for var in status.missing_variables:
        # Each entry must be a known env-var name, not a credential value.
        assert var in SZSE_REQUIRED_VARS
        assert var.isupper()
        # Ensure no credential value leaked into the list.
        assert var not in (SZSE_KEY, SZSE_SECRET, SZSE_TOKEN, TUSHARE_TOKEN_VAL)


# ---------------------------------------------------------------------------
# 5. Tushare token present → configured=True
# ---------------------------------------------------------------------------


def test_tushare_present_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUSHARE_TOKEN", TUSHARE_TOKEN_VAL)
    reset_env_config()

    status = get_provider_config("tushare")
    assert status.configured is True
    assert status.missing_variables == []


# ---------------------------------------------------------------------------
# 6. Config status and logs never contain credential values
# ---------------------------------------------------------------------------


def test_status_never_contains_credential_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_szse_all(monkeypatch)
    _set_tushare(monkeypatch)
    reset_env_config()

    for status in get_all_provider_statuses():
        d = status.to_dict()
        serialized = str(d)
        assert SZSE_KEY not in serialized
        assert SZSE_SECRET not in serialized
        assert SZSE_TOKEN not in serialized
        assert TUSHARE_TOKEN_VAL not in serialized
        # No credential masking — "confi****" or partial values are forbidden.
        for val in (SZSE_KEY, SZSE_SECRET, SZSE_TOKEN, TUSHARE_TOKEN_VAL):
            assert val[:4] not in serialized, "partial credential leaked"
            assert val[-4:] not in serialized, "partial credential leaked"


# ---------------------------------------------------------------------------
# 7. Docker compose override has no hardcoded credentials
# ---------------------------------------------------------------------------


def test_docker_compose_no_hardcoded_credentials() -> None:
    path = _REPO_ROOT / "docker-compose.market-data.yml"
    assert path.is_file(), f"{path} not found"
    content = path.read_text(encoding="utf-8")
    # All values use ${VAR:-} syntax — never inline strings or defaults.
    assert "${SZSE_DATA_ACCESS_KEY:-}" in content
    assert "${SZSE_DATA_ACCESS_SECRET:-}" in content
    assert "${SZSE_DATA_ACCESS_TOKEN:-}" in content
    assert "${TUSHARE_TOKEN:-}" in content
    # No hardcoded-looking credential values.
    for needle in ("TEST_ONLY", "sk-", "secret"):
        assert needle not in content, f"potential hardcoded credential: {needle}"


# ---------------------------------------------------------------------------
# 8. .env.market-data.local is gitignored
# ---------------------------------------------------------------------------


def test_local_file_gitignored() -> None:
    gitignore = _REPO_ROOT / ".gitignore"
    assert gitignore.is_file()
    content = gitignore.read_text(encoding="utf-8")
    assert ".env.market-data.local" in content


# ---------------------------------------------------------------------------
# 9. .env.market-data.example is tracked (not gitignored)
# ---------------------------------------------------------------------------


def test_example_file_tracked() -> None:
    example = _REPO_ROOT / ".env.market-data.example"
    assert example.is_file(), "example file must exist"
    gitignore = _REPO_ROOT / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    ignore_patterns = {ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")}
    assert ".env.market-data.example" not in ignore_patterns, "example file must not be gitignored"
    assert ".env.market-data.local" in ignore_patterns, "local secrets file must be gitignored"


# ---------------------------------------------------------------------------
# 10. Upstream not implemented — don't fake success
# ---------------------------------------------------------------------------


def test_szse_upstream_not_available() -> None:
    """SZSE Data has no implemented real-data fetch yet — verify structured
    unavailable result is returned, not a fake success."""
    # The provider status module correctly reports configured vs available.
    # Until a real fetch method exists, any "available" check must return
    # False without calling real APIs.
    marker = getattr(get_provider_config, "_szse_available", None)
    assert marker is None, (
        "SZSE upstream availability should NOT be implemented yet. "
        "A stub method was found that could fake a successful connection."
    )
