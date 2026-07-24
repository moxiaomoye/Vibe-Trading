"""Check real connectivity for configured market-data providers.

Runs inside the container where env vars are already injected.
Outputs only: provider, configured, connected, upstream_unavailable,
permission_denied.  Never outputs credential values.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Any

from src.config.accessor import get_env_config
from src.config.market_data_providers import get_provider_config

logger = logging.getLogger(__name__)


@dataclass
class ConnectivityStatus:
    provider: str
    configured: bool
    connected: bool = False
    upstream_unavailable: bool = False
    permission_denied: bool = False
    blocked_by_api_documentation: bool = False
    error: str | None = None
    details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "provider": self.provider,
            "configured": self.configured,
            "connected": self.connected,
        }
        if self.upstream_unavailable:
            d["upstream_unavailable"] = True
        if self.permission_denied:
            d["permission_denied"] = True
        if self.blocked_by_api_documentation:
            d["blocked_by_api_documentation"] = True
        if self.error:
            d["error"] = self.error
        if self.details:
            d["details"] = self.details
        return d


# Minimum-cost Tushare endpoints to try in order
_TUSHARE_PROBES = [
    ("trade_cal", {"exchange": "SSE", "start_date": "20260101", "end_date": "20260105"}),
    ("daily", {"ts_code": "000001.SZ", "start_date": "20260720", "end_date": "20260722"}),
    ("daily_basic", {"ts_code": "000001.SZ", "start_date": "20260720", "end_date": "20260722"}),
    ("stock_basic", {}),
]


def check_tushare() -> ConnectivityStatus:
    cfg = get_provider_config("tushare")
    status = ConnectivityStatus(provider="tushare", configured=cfg.configured)

    if not cfg.configured:
        return status

    try:
        import tushare as ts

        pro = ts.pro_api(get_env_config().data.tushare_token)

        last_error = None
        for api_name, params in _TUSHARE_PROBES:
            try:
                api_fn = getattr(pro, api_name)
                df = api_fn(**params)
                if df is not None and not df.empty:
                    status.connected = True
                    status.details = f"{api_name} returned {len(df)} rows"
                    return status
            except Exception as e:
                last_error = e
                continue

        # All probes failed — classify last error
        import traceback
        tb = "".join(traceback.format_exception_only(type(last_error), last_error)).strip()
        msg = str(last_error)
        if "permission" in msg.lower() or " denied" in msg.lower() or "无权限" in msg or "没有接口" in msg or "积分" in msg:
            status.permission_denied = True
        else:
            status.upstream_unavailable = True
        # Redact anything that looks like a credential before exposing details
        import re as _re
        tb_redacted = _re.sub(r"([A-Za-z0-9+/=_-]{40,})", "<REDACTED>", tb)
        tb_redacted = _re.sub(r"(sk-[A-Za-z0-9][A-Za-z0-9-]{19,})", "<API-KEY-REDACTED>", tb_redacted)
        status.details = tb_redacted[:200]

    except Exception as exc:
        msg = str(exc)
        if "token" in msg.lower() and ("invalid" in msg.lower() or "error" in msg.lower()):
            status.permission_denied = True
            status.details = "token rejected"
        else:
            status.upstream_unavailable = True
            status.details = msg.split("。")[0] if "。" in msg else msg.split(".")[0] if "." in msg else msg[:120]

    return status


def check_szse_data() -> ConnectivityStatus:
    cfg = get_provider_config("szse_data")
    status = ConnectivityStatus(provider="szse_data", configured=cfg.configured)

    if not cfg.configured:
        return status

    status.blocked_by_api_documentation = True
    status.details = (
        "Missing: base URL, request paths, signature algorithm, "
        "header names, timestamp/nonce rules, response fields"
    )
    return status


def main() -> None:
    results = []
    for provider_name in ("tushare", "szse_data"):
        if provider_name == "tushare":
            r = check_tushare()
        else:
            r = check_szse_data()
        results.append(r.to_dict())

    import json

    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    for r in results:
        if r.get("configured") and not r.get("connected"):
            if not r.get("blocked_by_api_documentation"):
                sys.exit(1)


if __name__ == "__main__":
    main()
