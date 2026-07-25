"""观察池 YAML 配置加载器。无网络，仅有文件 I/O。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class WatchlistConfig:
    version: str
    name: str
    symbols: tuple[str, ...]
    content_hash: str


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_WATCHLIST_PATH = _PROJECT_ROOT / "config/research/a_share_watchlist.yaml"


def _compute_hash(data: dict) -> str:
    raw = yaml.dump(data, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_watchlist(path: Optional[Path] = None) -> WatchlistConfig:
    """从 YAML 文件加载观察池配置。

    返回冻结的 WatchlistConfig，包含内容哈希用于跟踪配置版本变化。
    """
    resolved = path or DEFAULT_WATCHLIST_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"观察池配置文件不存在: {resolved}")
    raw = resolved.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or "watchlist" not in data:
        raise ValueError("观察池配置文件格式错误：缺少 watchlist 键")
    wl = data["watchlist"]
    symbols = tuple(wl.get("symbols", []))
    return WatchlistConfig(
        version=data.get("version", "0.0.0"),
        name=wl.get("name", "unnamed"),
        symbols=symbols,
        content_hash=_compute_hash(data),
    )


def load_watchlist_symbols(path: Optional[Path] = None) -> list[str]:
    """便捷函数：仅返回观察池股票代码列表。"""
    cfg = load_watchlist(path)
    return list(cfg.symbols)
