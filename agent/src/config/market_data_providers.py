"""Market-data provider configuration status.

Provides a structured view of whether each external data provider has the
necessary credentials configured.  Credential values are never exposed —
only ``configured`` / ``missing`` status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.config.accessor import get_env_config


@dataclass
class ProviderConfigStatus:
    """Read-only status of one external data provider's credential setup.

    Attributes:
        provider: Machine-readable provider identifier (e.g. ``"szse_data"``).
        configured: ``True`` when all required credential env vars are present.
        missing_variables: Names of the env vars that are still empty.
    """
    provider: str
    configured: bool
    missing_variables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "missing_variables": list(self.missing_variables),
        }


SZSE_REQUIRED_VARS = ["SZSE_DATA_ACCESS_KEY", "SZSE_DATA_ACCESS_SECRET", "SZSE_DATA_ACCESS_TOKEN"]
TUSHARE_REQUIRED_VARS = ["TUSHARE_TOKEN"]


def get_provider_config(provider: str) -> ProviderConfigStatus:
    """Return the credential-configuration status for *provider*.

    Args:
        provider: One of ``"szse_data"`` or ``"tushare"``.

    Returns:
        A ``ProviderConfigStatus`` with ``configured`` and
        ``missing_variables`` populated.  Credential values are never
        included in the result.
    """
    cfg = get_env_config()

    if provider == "szse_data":
        key = cfg.data.szse_data_access_key
        secret = cfg.data.szse_data_access_secret
        token = cfg.data.szse_data_access_token
        missing = []
        if not key:
            missing.append("SZSE_DATA_ACCESS_KEY")
        if not secret:
            missing.append("SZSE_DATA_ACCESS_SECRET")
        if not token:
            missing.append("SZSE_DATA_ACCESS_TOKEN")
        return ProviderConfigStatus(
            provider="szse_data",
            configured=bool(key and secret and token),
            missing_variables=missing,
        )

    if provider == "tushare":
        token = cfg.data.tushare_token
        missing = []
        if not token:
            missing.append("TUSHARE_TOKEN")
        return ProviderConfigStatus(
            provider="tushare",
            configured=bool(token),
            missing_variables=missing,
        )

    raise ValueError(f"Unknown market-data provider: {provider!r}")


def get_all_provider_statuses() -> list[ProviderConfigStatus]:
    """Return configuration status for all known market-data providers."""
    return [
        get_provider_config("szse_data"),
        get_provider_config("tushare"),
    ]
