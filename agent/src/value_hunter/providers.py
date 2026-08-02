"""Market-data providers.

Demo data is deterministic and supports full offline verification.  The live
provider intentionally returns missing fundamentals as missing instead of
inventing values; users can supply a point-in-time watchlist CSV to enrich it.
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError, as_completed
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Callable
from zoneinfo import ZoneInfo

from backtest.loaders._symbol_utils import _is_etf_listed
from backtest.loaders.registry import get_loader_cls_exact
from src.market_data import fetch_market_data

from .models import CandidateObservation, IndexObservation, MarketObservation


MarketFetcher = Callable[..., dict[str, Any]]

RESEARCH_MARKET_DATA_FALLBACK_CHAIN: tuple[str, ...] = (
    "tushare",
    "akshare",
    "tencent",
    "mootdx",
    "eastmoney",
    "baostock",
    "local",
)
MAX_STALE_COMPLETED_WEEKDAYS = 1

ETF_TRACKED_INDEX: dict[str, tuple[str, str]] = {
    "588060": ("000688", "上证科创板50成份指数"),
    "588170": ("950125", "上证科创板半导体材料设备主题指数"),
    "588200": ("000685", "上证科创板芯片指数"),
    "159516": ("931743", "中证半导体材料设备主题指数"),
    "159941": ("NDX", "纳斯达克100指数"),
}


def _call_with_timeout(call: Callable[[], Any], seconds: float) -> Any:
    """Bound a public SDK call so one upstream cannot block the UI forever."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="market-provider-timeout")
    future = pool.submit(call)
    try:
        return future.result(timeout=seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"public market data call exceeded {seconds:g}s") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


class ValueHunterProvider(ABC):
    name = "base"

    @abstractmethod
    def load_market(self) -> MarketObservation: ...

    @abstractmethod
    def load_candidates(self) -> list[CandidateObservation]: ...


def _latest_complete_weekday(now: datetime | None = None) -> date:
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    resolved = current.date()
    if current.weekday() < 5 and current.time() < time(15, 5):
        resolved -= timedelta(days=1)
    while resolved.weekday() >= 5:
        resolved -= timedelta(days=1)
    return resolved


def _completed_weekdays_between(older: date, newer: date) -> int:
    """Count completed weekdays after ``older`` through ``newer``.

    This is deliberately a conservative freshness guard rather than a trading
    calendar. Public-provider holidays may therefore trigger a refresh, which
    is preferable to silently presenting an old close as current.
    """
    if older >= newer:
        return 0
    cursor = older + timedelta(days=1)
    count = 0
    while cursor <= newer:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


class DemoProvider(ValueHunterProvider):
    name = "demo"

    def load_market(self) -> MarketObservation:
        return MarketObservation(
            as_of="2024-02-05",
            indices=[
                IndexObservation("000300.SH", "沪深300", 3210, -2.1, -22.0, True, True),
                IndexObservation("000905.SH", "中证500", 4520, -4.0, -34.0, True, True),
                IndexObservation("000852.SH", "中证1000", 4310, -6.2, -42.0, True, True),
                IndexObservation("399006.SZ", "创业板指", 1560, -3.4, -38.0, True, True),
                IndexObservation("000001.SH", "上证指数", 2702, -1.0, -21.0, True, True),
            ],
            advancer_ratio=0.08,
            above_ma60_ratio=0.12,
            limit_down_count=170,
            turnover_zscore=1.8,
            source="demo-point-in-time",
            coverage=["indices", "breadth", "limit_down", "turnover"],
        )

    def load_candidates(self) -> list[CandidateObservation]:
        return [
            CandidateObservation(
                "688001.SH", "示例芯片龙头", "半导体", "国产芯片", 2200, 2, True,
                17.2, 1.12, 28.0, 3.2, 0.14, 0.22, 25.0, 31.0, -43.0, -18.0, 0.86,
                source_fields=["point_in_time_financials", "daily_basic", "price_history"],
                daily_return_pct=-4.5, return_20d_pct=-18.0, return_60d_pct=-28.0,
                relative_to_market_pct=6.0,
                catalyst_evidence=["产能利用率改善待验证", "下一期财报利润率待验证"],
            ),
            CandidateObservation(
                "300001.SZ", "示例光模块成长", "通信设备", "光模块", 1700, 3, True,
                15.1, 0.92, 39.0, 7.0, 0.33, 0.40, 42.0, 55.0, -31.0, -9.0, 0.91,
                source_fields=["point_in_time_financials", "daily_basic", "price_history"],
                daily_return_pct=-3.0, return_20d_pct=-12.0, return_60d_pct=-20.0,
                relative_to_market_pct=4.0,
                catalyst_evidence=["订单增长待下一期报告验证"],
            ),
            CandidateObservation(
                "002001.SZ", "示例情绪标的", "软件", "AI应用", 530, 5, False,
                6.0, 0.32, 96.0, 12.0, 0.88, 0.91, 4.0, -12.0, -48.0, -22.0, 0.98,
                risk_flags=["profit_decline"],
                source_fields=["point_in_time_financials", "daily_basic", "price_history"],
            ),
            CandidateObservation(
                "688999.SH", "示例风险公司", "半导体", "芯片设计", 180, 18, False,
                -3.0, -0.4, -25.0, 18.0, 0.08, 0.15, -20.0, -120.0, -66.0, -30.0, 0.99,
                risk_flags=["investigation"],
                source_fields=["point_in_time_financials", "daily_basic", "price_history"],
            ),
        ]


_DEFAULT_TECH_WATCHLIST = (
    ("688981", "中芯国际", "半导体制造", "国产芯片"),
    ("688041", "海光信息", "半导体设计", "国产算力"),
    ("688256", "寒武纪", "半导体设计", "AI芯片"),
    ("300308", "中际旭创", "通信设备", "光模块"),
    ("300502", "新易盛", "通信设备", "光模块"),
    ("601138", "工业富联", "电子制造", "AI服务器"),
    ("002371", "北方华创", "半导体设备", "国产设备"),
    ("688012", "中微公司", "半导体设备", "国产设备"),
    ("002463", "沪电股份", "电子元件", "PCB"),
    ("300476", "胜宏科技", "电子元件", "PCB"),
    ("688111", "金山办公", "软件", "国产软件"),
    ("002230", "科大讯飞", "软件", "AI应用"),
    ("688777", "中控技术", "自动化", "工业AI"),
    ("002920", "德赛西威", "汽车电子", "自动驾驶"),
)


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() in {"", "-", "None", "nan"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def normalize_ashare_symbol(symbol: str) -> str:
    """Return the loader-registry symbol for an exchange-listed A-share asset."""
    value = symbol.strip().upper()
    if value.endswith((".SH", ".SZ", ".BJ")):
        return value
    if len(value) != 6 or not value.isdigit():
        return value
    if value.startswith(("4", "8")):
        return f"{value}.BJ"
    if value.startswith(("5", "6", "9")):
        return f"{value}.SH"
    return f"{value}.SZ"


def security_type_for_symbol(symbol: str) -> str:
    normalized = normalize_ashare_symbol(symbol)
    return "etf" if _is_etf_listed(normalized) else "stock"


def _market_rows(raw: Any, *, through: date) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        raw = raw["data"]
    if not isinstance(raw, list):
        return []
    dated: list[tuple[date, dict[str, Any]]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        row_date: date | None = None
        for key in ("trade_date", "date", "datetime", "index", "Date"):
            value = row.get(key)
            if value is None:
                continue
            try:
                row_date = date.fromisoformat(str(value)[:10])
                break
            except ValueError:
                continue
        if row_date is not None and row_date <= through:
            dated.append((row_date, row))
    return [row for _, row in sorted(dated, key=lambda item: item[0])]


def _frame_on_or_before(frame: Any, through: date) -> tuple[Any, date | None]:
    """Return chronologically ordered rows through a confirmed market date."""
    date_values: list[Any] | None = None
    for column in ("date", "trade_date", "日期"):
        if column in frame.columns:
            date_values = list(frame[column])
            break
    if date_values is None:
        date_values = list(frame.index)

    dated_positions: list[tuple[date, int]] = []
    for position, value in enumerate(date_values):
        try:
            row_date = date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            continue
        if row_date <= through:
            dated_positions.append((row_date, position))
    if not dated_positions:
        return frame.iloc[0:0], None
    dated_positions.sort(key=lambda item: item[0])
    return frame.iloc[[position for _, position in dated_positions]], dated_positions[-1][0]


def _series_number(row: dict[str, Any], key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def _period_return(closes: list[float], sessions: int) -> float | None:
    if len(closes) <= sessions or closes[-(sessions + 1)] <= 0:
        return None
    return round((closes[-1] / closes[-(sessions + 1)] - 1.0) * 100.0, 4)


def _normalize_etf_split_history(closes: list[float]) -> tuple[list[float], int]:
    """Put pre-split ETF prices onto the latest share basis.

    A-share ETF daily moves beyond 30% are treated as unit splits/mergers for
    this screen. The adjustment is explicit in the valuation payload so the
    result is never confused with exchange-provided adjusted history.
    """
    adjusted = list(closes)
    split_count = 0
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        if previous <= 0:
            continue
        ratio = closes[index] / previous
        if ratio < 0.70 or ratio > (1 / 0.70):
            for prior in range(index):
                adjusted[prior] *= ratio
            split_count += 1
    return adjusted, split_count


def _percentile(values: list[float], percentile: float) -> float | None:
    ordered = sorted(value for value in values if value > 0)
    if not ordered:
        return None
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _etf_price_bands(closes: list[float]) -> dict[str, Any]:
    """Create screen-grade research bands from a trailing 252-session history."""
    window = closes[-252:]
    if len(window) < 60:
        return {}
    current = window[-1]
    p10 = _percentile(window, 0.10)
    p25 = _percentile(window, 0.25)
    p35 = _percentile(window, 0.35)
    p65 = _percentile(window, 0.65)
    if None in {p10, p25, p35, p65}:
        return {}
    rank = sum(value <= current for value in window) / len(window)
    if current <= p10:
        state = "深度低估研究区"
    elif current <= p25:
        state = "低估关注区"
    elif p35 <= current <= p65:
        state = "历史合理区间"
    elif current > p65:
        state = "高于历史合理区间"
    else:
        state = "合理区间下沿"
    return {
        "reasonable_price_low": round(float(p35), 4),
        "reasonable_price_high": round(float(p65), 4),
        "bargain_price_low": round(float(p10), 4),
        "bargain_price_high": round(float(p25), 4),
        "deep_value_below": round(float(p10), 4),
        "historical_price_percentile": round(rank, 4),
        "valuation_state": state,
        "history_sessions": len(window),
        "valuation_method": "近252个交易日市场价格分位（研究筛选口径）",
        "confidence": "screen_grade",
    }


def load_watchlist_csv(path: Path) -> list[CandidateObservation]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: list[CandidateObservation] = []
    for row in rows:
        result.append(CandidateObservation(
            symbol=row.get("symbol", "").strip(), name=row.get("name", "").strip(),
            sector=row.get("sector", "科技").strip(), theme=row.get("theme", "科技").strip(),
            market_cap_billion=_number(row.get("market_cap_billion")),
            industry_market_cap_rank=int(_number(row.get("industry_market_cap_rank"))) if _number(row.get("industry_market_cap_rank")) is not None else None,
            important_index_member=_bool_value(row.get("important_index_member")),
            roe_5y_median_pct=_number(row.get("roe_5y_median_pct")),
            operating_cashflow_to_profit=_number(row.get("operating_cashflow_to_profit")),
            pe_ttm=_number(row.get("pe_ttm")), pb=_number(row.get("pb")),
            pe_history_percentile=_number(row.get("pe_history_percentile")),
            pe_industry_percentile=_number(row.get("pe_industry_percentile")),
            revenue_growth_pct=_number(row.get("revenue_growth_pct")),
            profit_growth_pct=_number(row.get("profit_growth_pct")),
            drawdown_252_pct=_number(row.get("drawdown_252_pct")),
            relative_to_sector_pct=_number(row.get("relative_to_sector_pct")),
            turnover_percentile=_number(row.get("turnover_percentile")),
            risk_flags=[x.strip() for x in row.get("risk_flags", "").split("|") if x.strip()],
            risk_evidence=[x.strip() for x in row.get("risk_evidence", "").split("|") if x.strip()],
            source_fields=["watchlist_csv"],
        ))
    return result


def load_watchlist(path: Path) -> list[CandidateObservation]:
    """Load the existing research universe from CSV or the concise YAML form."""
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return load_watchlist_csv(path)
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("scope", "watchlist") != "watchlist":
        raise ValueError("Only the single watchlist research scope is supported")
    rows = [*(raw.get("stocks") or []), *(raw.get("etfs") or [])]
    result: list[CandidateObservation] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol", "")).strip()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        result.append(CandidateObservation(
            symbol=symbol,
            name=str(row.get("name", symbol)).strip(),
            sector=str(row.get("sector", "Data Gap")).strip(),
            theme=str(row.get("theme", "Data Gap")).strip(),
            security_type=security_type_for_symbol(symbol),
            source_fields=["watchlist_yaml"],
        ))
    return result


class AkshareProvider(ValueHunterProvider):
    name = "akshare"

    _INDEX_MAP = {
        "sh000300": "沪深300", "sh000905": "中证500", "sh000852": "中证1000",
        "sz399006": "创业板指", "sh000001": "上证指数",
    }

    def __init__(
        self,
        watchlist_path: Path | None = None,
        cache_dir: Path | None = None,
        market_fetcher: MarketFetcher = fetch_market_data,
    ):
        self.watchlist_path = watchlist_path
        self.cache_dir = cache_dir
        self.market_fetcher = market_fetcher

    def _cache_path(self, kind: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"akshare-{kind}-{date.today().isoformat()}.json"

    def _read_market_cache(self) -> MarketObservation | None:
        path = self._cache_path("market")
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        required_summary = (
            "advancer_count", "decliner_count", "limit_up_count",
            "limit_down_count", "advancer_ratio", "turnover_amount",
        )
        if any(field not in data for field in required_summary):
            return None
        cached_date = date.fromisoformat(data["as_of"])
        if _completed_weekdays_between(cached_date, _latest_complete_weekday()) > MAX_STALE_COMPLETED_WEEKDAYS:
            return None
        if cached_date.weekday() >= 5:
            data["as_of"] = _latest_complete_weekday().isoformat()
        data["indices"] = [IndexObservation(**item) for item in data["indices"]]
        data["warnings"] = list(data.get("warnings", [])) + ["使用当日缓存行情"]
        return MarketObservation(**data)

    def _read_candidate_cache(self) -> list[CandidateObservation] | None:
        path = self._cache_path("candidates")
        if path is None:
            return None
        stale_date: str | None = None
        if not path.exists():
            available = sorted(path.parent.glob("akshare-candidates-*.json"), reverse=True)
            if not available:
                return None
            path = available[0]
            stale_date = path.stem.removeprefix("akshare-candidates-")
            try:
                cached_on = date.fromisoformat(stale_date)
            except ValueError:
                return None
            if (
                _completed_weekdays_between(cached_on, _latest_complete_weekday())
                > MAX_STALE_COMPLETED_WEEKDAYS
            ):
                return None
        candidates = [CandidateObservation(**item) for item in json.loads(path.read_text(encoding="utf-8"))]
        if self.watchlist_path and self.watchlist_path.exists():
            expected_symbols = {
                candidate.symbol for candidate in load_watchlist(self.watchlist_path)
            }
            cached_symbols = {candidate.symbol for candidate in candidates}
            if cached_symbols != expected_symbols or any(
                candidate.market_data_as_of is None for candidate in candidates
            ):
                return None
        if stale_date:
            for candidate in candidates:
                candidate.warnings.append(
                    f"候选缓存数据截至{stale_date}，不是当前交易日数据；当前价格与溢价判断属于 Data Gap。"
                )
        return candidates

    def _write_cache(self, kind: str, value: Any) -> None:
        path = self._cache_path(kind)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(value) if kind == "market" else [asdict(item) for item in value]
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _ak():
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare未安装，无法使用实时数据模式") from exc
        return ak

    def load_market(self) -> MarketObservation:
        cached = self._read_market_cache()
        if cached is not None:
            return cached
        ak = self._ak()
        observations: list[IndexObservation] = []
        warnings: list[str] = []
        market_as_of: date | None = None
        latest_candidate = _latest_complete_weekday()
        for symbol, name in self._INDEX_MAP.items():
            try:
                try:
                    frame = ak.stock_zh_index_daily_em(symbol=symbol)
                except Exception:
                    # Eastmoney occasionally resets TLS connections from
                    # Docker networks; Tencent provides the same OHLC history.
                    frame = ak.stock_zh_index_daily_tx(symbol=symbol)
                    warnings.append(f"{name}使用腾讯备用行情")
                frame, index_as_of = _frame_on_or_before(
                    frame, market_as_of or latest_candidate
                )
                if index_as_of is None:
                    warnings.append(f"{name}缺少可确认交易日期的行情")
                    continue
                if market_as_of is None:
                    market_as_of = index_as_of
                elif index_as_of != market_as_of:
                    warnings.append(
                        f"{name}行情日期{index_as_of.isoformat()}与市场日期"
                        f"{market_as_of.isoformat()}不一致"
                    )
                    continue
                closes = frame["close"].astype(float).tail(300)
                close = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                observations.append(IndexObservation(
                    symbol=symbol, name=name, close=close,
                    daily_return_pct=(close / prev - 1) * 100,
                    drawdown_252_pct=(close / float(closes.tail(252).max()) - 1) * 100,
                    below_ma250=close < float(closes.tail(250).mean()),
                    below_120d_low=close <= float(closes.iloc[:-1].tail(120).min()),
                ))
            except Exception as exc:  # provider failures must remain visible
                warnings.append(f"{name}读取失败: {type(exc).__name__}")
        if not observations:
            raise RuntimeError("主要指数均读取失败")

        advancer_ratio = None
        limit_down_count = None
        advancer_count = None
        decliner_count = None
        limit_up_count = None
        turnover_amount = None
        try:
            current = datetime.now(ZoneInfo("Asia/Shanghai"))
            if current.weekday() < 5 and current.time() < time(15, 5):
                raise RuntimeError("current A-share session is not complete")
            try:
                spot = _call_with_timeout(ak.stock_zh_a_spot_em, 30)
            except Exception:
                # Sina's paginated endpoint is slower but independent of the
                # Eastmoney route and supplies the breadth fields we need.
                spot = _call_with_timeout(ak.stock_zh_a_spot, 60)
                warnings.append("市场宽度使用新浪备用行情（读取较慢）")
            changes = spot["涨跌幅"].astype(float)
            advancer_count = int((changes > 0).sum())
            decliner_count = int((changes < 0).sum())
            advancer_ratio = float(advancer_count / max(len(changes), 1))
            # Approximation handles main board and 20% boards without claiming exact exchange stats.
            limit_up_count = int((changes >= 9.8).sum())
            limit_down_count = int((changes <= -9.8).sum())
            turnover_column = next(
                (column for column in ("成交额", "amount") if column in spot.columns),
                None,
            )
            if turnover_column is not None:
                amounts = [_number(value) for value in spot[turnover_column]]
                valid_amounts = [value for value in amounts if value is not None]
                if valid_amounts:
                    turnover_amount = float(sum(valid_amounts))
        except Exception as exc:
            warnings.append(f"市场宽度读取失败: {type(exc).__name__}")

        result = MarketObservation(
            as_of=(market_as_of or latest_candidate).isoformat(), indices=observations,
            advancer_ratio=advancer_ratio, above_ma60_ratio=None,
            limit_down_count=limit_down_count, turnover_zscore=None,
            source="AKShare/Eastmoney", coverage=["indices", "spot_breadth"], warnings=warnings,
            advancer_count=advancer_count, decliner_count=decliner_count,
            limit_up_count=limit_up_count, turnover_amount=turnover_amount,
        )
        self._write_cache("market", result)
        return result

    def _base_watchlist(self) -> list[CandidateObservation]:
        if self.watchlist_path and self.watchlist_path.exists():
            return load_watchlist(self.watchlist_path)
        return [CandidateObservation(code, name, sector, theme) for code, name, sector, theme in _DEFAULT_TECH_WATCHLIST]

    def load_candidates(self) -> list[CandidateObservation]:
        cached = self._read_candidate_cache()
        if cached is not None:
            stale_etfs = [
                item for item in cached
                if item.security_type == "etf"
                and (item.etf_valuation or {}).get("calculation_version") != 3
            ]
            if stale_etfs:
                ak = self._ak()
                self._enrich_market_history(stale_etfs)
                self._enrich_etf_nav(ak, stale_etfs)
                self._enrich_etf_index_valuation(ak, stale_etfs)
                self._write_cache("candidates", cached)
            return cached
        ak = self._ak()
        candidates = self._base_watchlist()
        self._enrich_market_history(candidates)
        self._enrich_etf_nav(ak, candidates)
        self._enrich_etf_index_valuation(ak, candidates)
        # Financial and historical-valuation endpoints are per issuer. Four
        # workers keep a normal scan practical while avoiding a burst of
        # dozens of simultaneous public-data requests.
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="value-hunter-data") as pool:
            futures = {pool.submit(self._enrich_candidate, ak, item): item for item in candidates}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    future.result()
                except Exception as exc:
                    item.warnings.append(f"候选数据补充失败: {type(exc).__name__}: {exc}")
        self._enrich_announcements(ak, candidates)
        self._write_cache("candidates", candidates)
        return candidates

    def _enrich_market_history(self, candidates: list[CandidateObservation]) -> None:
        """Populate point-in-time OHLCV metrics through the shared loader registry."""
        through = _latest_complete_weekday()
        start = through - timedelta(days=400)
        normalized = {item.symbol: normalize_ashare_symbol(item.symbol) for item in candidates}
        benchmark_symbol = "000300.SH"
        codes = list(dict.fromkeys([*normalized.values(), benchmark_symbol]))
        try:
            payload = self.market_fetcher(
                codes=codes,
                start_date=start.isoformat(),
                end_date=through.isoformat(),
                source="tushare",
                interval="1D",
                max_rows=0,
                loader_resolver=get_loader_cls_exact,
                fallback_chain_provider=lambda _: list(RESEARCH_MARKET_DATA_FALLBACK_CHAIN),
                max_fallback_attempts=len(RESEARCH_MARKET_DATA_FALLBACK_CHAIN),
                include_metadata=True,
            )
        except Exception as exc:  # noqa: BLE001 - provider gaps belong on observations
            for candidate in candidates:
                candidate.security_type = security_type_for_symbol(candidate.symbol)
                candidate.warnings.append(
                    f"market_data_registry unavailable: {type(exc).__name__}: {exc}"
                )
            return

        benchmark_rows = _market_rows(payload.get(benchmark_symbol), through=through)
        source_by_symbol = (payload.get("_metadata") or {}).get("source_by_symbol") or {}
        benchmark_closes = [
            close for row in benchmark_rows if (close := _series_number(row, "close")) is not None
        ]
        benchmark_return_20d = _period_return(benchmark_closes, 20)

        for candidate in candidates:
            candidate.security_type = security_type_for_symbol(candidate.symbol)
            provider_symbol = normalized[candidate.symbol]
            rows = _market_rows(payload.get(provider_symbol), through=through)
            closes = [close for row in rows if (close := _series_number(row, "close")) is not None]
            if not closes:
                candidate.warnings.append(f"market_data.{provider_symbol}.price_history")
                continue

            split_adjustments = 0
            if candidate.security_type == "etf":
                closes, split_adjustments = _normalize_etf_split_history(closes)
                if split_adjustments:
                    candidate.warnings.append(
                        f"ETF历史价格检测到{split_adjustments}次份额拆分跳变，已归一到当前份额口径"
                    )
            candidate.current_price = closes[-1]
            candidate.daily_return_pct = _period_return(closes, 1)
            candidate.return_20d_pct = _period_return(closes, 20)
            candidate.return_60d_pct = _period_return(closes, 60)
            recent = closes[-252:]
            if recent and max(recent) > 0:
                candidate.drawdown_252_pct = (recent[-1] / max(recent) - 1.0) * 100.0

            volumes = [volume for row in rows if (volume := _series_number(row, "volume")) is not None]
            if len(volumes) >= 21:
                prior_average = sum(volumes[-21:-1]) / 20.0
                if prior_average > 0:
                    candidate.volume_ratio_20d = volumes[-1] / prior_average

            if candidate.return_20d_pct is not None and benchmark_return_20d is not None:
                candidate.relative_to_market_pct = candidate.return_20d_pct - benchmark_return_20d
            candidate.market_data_as_of = through.isoformat()
            candidate.market_data_source = source_by_symbol.get(provider_symbol)
            if candidate.security_type == "etf":
                candidate.etf_valuation.update(_etf_price_bands(closes))
                candidate.etf_valuation.update({
                    "price_as_of": through.isoformat(),
                    "price_source": candidate.market_data_source,
                    "underlying_valuation_premium_pct": None,
                    "split_adjustments": split_adjustments,
                    "calculation_version": 3,
                })
            if "market_data_registry_ohlcv" not in candidate.source_fields:
                candidate.source_fields.append("market_data_registry_ohlcv")

    @staticmethod
    def _enrich_etf_nav(ak: Any, candidates: list[CandidateObservation]) -> None:
        etfs = [item for item in candidates if item.security_type == "etf"]
        if not etfs:
            return
        try:
            frame = _call_with_timeout(ak.fund_etf_fund_daily_em, 25)
        except Exception as exc:
            for candidate in etfs:
                candidate.warnings.append(
                    f"ETF单位净值读取失败: {type(exc).__name__}"
                )
                candidate.etf_valuation.setdefault("latest_nav", None)
                candidate.etf_valuation.setdefault("nav_premium_pct", None)
            return

        if "基金代码" not in frame.columns:
            for candidate in etfs:
                candidate.warnings.append("ETF单位净值数据缺少基金代码")
            return
        rows = {str(row["基金代码"]).zfill(6): row for _, row in frame.iterrows()}
        nav_columns = [
            column for column in frame.columns
            if isinstance(column, str) and column.endswith("-单位净值")
        ]
        for candidate in etfs:
            row = rows.get(candidate.symbol[:6])
            if row is None:
                candidate.warnings.append("ETF单位净值快照缺失")
                continue
            latest_nav = None
            nav_as_of = None
            for column in nav_columns:
                value = _number(row.get(column))
                if value is not None and value > 0:
                    latest_nav = value
                    nav_as_of = column.removesuffix("-单位净值")
                    break
            market_price = _number(row.get("市价")) or candidate.current_price
            premium = (
                (market_price / latest_nav - 1.0) * 100.0
                if market_price is not None and latest_nav is not None
                else None
            )
            candidate.etf_valuation.update({
                "latest_nav": round(latest_nav, 4) if latest_nav is not None else None,
                "nav_as_of": nav_as_of,
                "nav_market_price": round(market_price, 4) if market_price is not None else None,
                "nav_premium_pct": round(premium, 3) if premium is not None else None,
                "nav_source": "AKShare/Eastmoney fund_etf_fund_daily_em",
                "premium_reliability": (
                    "limited_qdii_stale_nav"
                    if candidate.symbol[:6] == "159941"
                    else "latest_available_nav"
                ),
            })
            candidate.source_fields.append("eastmoney_etf_nav_snapshot")
            if candidate.symbol[:6] == "159941":
                candidate.warnings.append(
                    "QDII ETF净值存在海外时差、汇率与披露滞后，溢价仅作研究筛选"
                )

    @staticmethod
    def _enrich_etf_index_valuation(ak: Any, candidates: list[CandidateObservation]) -> None:
        etfs = [item for item in candidates if item.security_type == "etf"]
        domestic: dict[str, list[CandidateObservation]] = {}
        for candidate in etfs:
            code, name = ETF_TRACKED_INDEX.get(candidate.symbol[:6], ("", ""))
            candidate.etf_valuation.update({
                "underlying_index_code": code or None,
                "underlying_index_name": name or None,
            })
            if code == "NDX":
                candidate.etf_valuation.setdefault("underlying_valuation_premium_pct", None)
                candidate.warnings.append("纳斯达克100历史估值数据源尚未接入，底层指数估值为 Data Gap")
            elif code:
                domestic.setdefault(code, []).append(candidate)

        def fetch_index(code: str) -> Any:
            return _call_with_timeout(
                lambda: ak.stock_zh_index_value_csindex(symbol=code),
                25,
            )

        frames: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(domestic) or 1), thread_name_prefix="etf-index-value") as pool:
            futures = {pool.submit(fetch_index, code): code for code in domestic}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    frames[code] = future.result()
                except Exception as exc:
                    for candidate in domestic[code]:
                        candidate.warnings.append(
                            f"底层指数{code}估值读取失败: {type(exc).__name__}"
                        )

        for code, grouped_candidates in domestic.items():
            frame = frames.get(code)
            rows: list[tuple[str, float, float | None]] = []
            if frame is not None and not frame.empty:
                for _, row in frame.iterrows():
                    pe = _number(row.get("市盈率1"))
                    if pe is None or pe <= 0:
                        continue
                    rows.append((
                        str(row.get("日期", ""))[:10],
                        pe,
                        _number(row.get("股息率1")),
                    ))
            rows.sort(key=lambda item: item[0])
            if not rows:
                for candidate in grouped_candidates:
                    candidate.warnings.append(f"底层指数{code}估值历史为空")
                continue
            latest_date, latest_pe, latest_dividend = rows[-1]
            pe_values = [row[1] for row in rows]
            pe_median = median(pe_values)
            premium = (latest_pe / pe_median - 1.0) * 100.0 if pe_median > 0 else None
            percentile = sum(value <= latest_pe for value in pe_values) / len(pe_values)
            state = (
                "近期低估" if percentile <= 0.25
                else "近期合理" if percentile <= 0.75
                else "近期偏贵"
            )
            for candidate in grouped_candidates:
                candidate.etf_valuation.update({
                    "underlying_pe": round(latest_pe, 3),
                    "underlying_dividend_yield_pct": round(latest_dividend, 3) if latest_dividend is not None else None,
                    "underlying_valuation_as_of": latest_date,
                    "underlying_valuation_percentile": round(percentile, 4),
                    "underlying_valuation_premium_pct": round(premium, 3) if premium is not None else None,
                    "underlying_valuation_state": state,
                    "underlying_valuation_method": "中证指数PE相对当前可得历史中位数（screen_grade）",
                    "underlying_history_sessions": len(pe_values),
                    "underlying_valuation_source": "AKShare/中证指数 stock_zh_index_value_csindex",
                })
                candidate.source_fields.append("csindex_underlying_valuation")

    @staticmethod
    def _classify_announcement(title: str) -> str | None:
        rules = (
            (("立案告知书", "立案调查", "证监会立案"), "investigation"),
            (("非标准审计意见", "无法表示意见", "保留意见"), "qualified_audit"),
            (("财务造假", "虚假记载"), "fraud"),
            (("终止上市", "退市风险警示"), "delisting"),
            (("净资产为负", "资不抵债"), "negative_equity"),
            (("减持计划",), "shareholder_reduction"),
            (("业绩预亏", "预计亏损", "业绩下修"), "profit_decline"),
            (("问询函",), "inquiry"),
        )
        for keywords, flag in rules:
            if any(keyword in title for keyword in keywords):
                return flag
        return None

    def _enrich_announcements(self, ak: Any, candidates: list[CandidateObservation]) -> None:
        by_code = {item.symbol[:6]: item for item in candidates}
        days = [(date.today() - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(7)]
        frames: list[Any] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="value-hunter-notices") as pool:
            futures = {
                pool.submit(ak.stock_notice_report, symbol="全部", date=day): day
                for day in days
            }
            for future in as_completed(futures):
                try:
                    frames.append(future.result())
                except Exception as exc:
                    errors.append(f"{futures[future]}:{type(exc).__name__}")
        for frame in frames:
            if "代码" not in frame or "公告标题" not in frame:
                continue
            for _, row in frame.iterrows():
                candidate = by_code.get(str(row["代码"]).zfill(6))
                if candidate is None:
                    continue
                title = str(row["公告标题"])
                flag = self._classify_announcement(title)
                if flag and flag not in candidate.risk_flags:
                    candidate.risk_flags.append(flag)
                if flag and title not in candidate.risk_evidence:
                    candidate.risk_evidence.append(title[:160])
        for candidate in candidates:
            candidate.source_fields.append("eastmoney_7d_announcement_titles")
            if errors:
                candidate.warnings.append("部分公告日期读取失败: " + ", ".join(errors[:3]))

    @staticmethod
    def _enrich_candidate(ak: Any, candidate: CandidateObservation) -> None:
        candidate.security_type = security_type_for_symbol(candidate.symbol)
        if candidate.security_type == "etf":
            candidate.warnings.append(
                "ETF不适用发行人ROE、PE与公司财务接口；相关字段保留Data Gap"
            )
            return
        code = candidate.symbol[:6]
        try:
            values = ak.stock_value_em(symbol=code)
            pe = values["PE(TTM)"].astype(float)
            pe = pe[pe > 0].tail(1250)
            if not pe.empty:
                current_pe = float(pe.iloc[-1])
                candidate.pe_ttm = current_pe
                candidate.pe_history_percentile = float((pe <= current_pe).sum() / len(pe))
            closes = values["当日收盘价"].astype(float).tail(252)
            if not closes.empty:
                candidate.current_price = float(closes.iloc[-1])
                candidate.drawdown_252_pct = (float(closes.iloc[-1]) / float(closes.max()) - 1) * 100
            candidate.pb = _number(values["市净率"].iloc[-1])
            market_cap = _number(values["总市值"].iloc[-1])
            candidate.market_cap_billion = market_cap / 1e9 if market_cap is not None else None
            candidate.source_fields.extend(["eastmoney_value_history", "eastmoney_price_history"])
        except Exception as exc:
            candidate.warnings.append(f"历史估值读取失败: {type(exc).__name__}")

        try:
            start_year = str(max(2000, date.today().year - 6))
            frame = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year).copy()
            frame["日期"] = frame["日期"].astype(str)
            frame = frame.sort_values("日期")
            annual = frame[frame["日期"].str.endswith("12-31")].tail(5)
            roe = annual["净资产收益率(%)"].dropna().astype(float)
            if not roe.empty:
                candidate.roe_5y_median_pct = float(roe.median())
            latest = frame.iloc[-1]
            cash_ratio = _number(latest.get("经营现金净流量与净利润的比率(%)"))
            candidate.operating_cashflow_to_profit = cash_ratio / 100 if cash_ratio is not None else None
            candidate.revenue_growth_pct = _number(latest.get("主营业务收入增长率(%)"))
            candidate.profit_growth_pct = _number(latest.get("净利润增长率(%)"))
            candidate.source_fields.append("sina_point_in_time_financial_indicators")
        except Exception as exc:
            candidate.warnings.append(f"财务指标读取失败: {type(exc).__name__}")


def build_provider(
    name: str,
    watchlist_path: Path | None = None,
    cache_dir: Path | None = None,
) -> ValueHunterProvider:
    if name == "demo":
        return DemoProvider()
    if name == "akshare":
        return AkshareProvider(watchlist_path, cache_dir)
    raise ValueError(f"未知Value Hunter数据源: {name}")
