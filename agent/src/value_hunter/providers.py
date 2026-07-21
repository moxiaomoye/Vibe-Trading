"""Market-data providers.

Demo data is deterministic and supports full offline verification.  The live
provider intentionally returns missing fundamentals as missing instead of
inventing values; users can supply a point-in-time watchlist CSV to enrich it.
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .models import CandidateObservation, IndexObservation, MarketObservation


class ValueHunterProvider(ABC):
    name = "base"

    @abstractmethod
    def load_market(self) -> MarketObservation: ...

    @abstractmethod
    def load_candidates(self) -> list[CandidateObservation]: ...


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
            ),
            CandidateObservation(
                "300001.SZ", "示例光模块成长", "通信设备", "光模块", 1700, 3, True,
                15.1, 0.92, 39.0, 7.0, 0.33, 0.40, 42.0, 55.0, -31.0, -9.0, 0.91,
                source_fields=["point_in_time_financials", "daily_basic", "price_history"],
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


class AkshareProvider(ValueHunterProvider):
    name = "akshare"

    _INDEX_MAP = {
        "sh000300": "沪深300", "sh000905": "中证500", "sh000852": "中证1000",
        "sz399006": "创业板指", "sh000001": "上证指数",
    }

    def __init__(self, watchlist_path: Path | None = None, cache_dir: Path | None = None):
        self.watchlist_path = watchlist_path
        self.cache_dir = cache_dir

    def _cache_path(self, kind: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"akshare-{kind}-{date.today().isoformat()}.json"

    def _read_market_cache(self) -> MarketObservation | None:
        path = self._cache_path("market")
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["indices"] = [IndexObservation(**item) for item in data["indices"]]
        data["warnings"] = list(data.get("warnings", [])) + ["使用当日缓存行情"]
        return MarketObservation(**data)

    def _read_candidate_cache(self) -> list[CandidateObservation] | None:
        path = self._cache_path("candidates")
        if path is None or not path.exists():
            return None
        return [CandidateObservation(**item) for item in json.loads(path.read_text(encoding="utf-8"))]

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
        for symbol, name in self._INDEX_MAP.items():
            try:
                try:
                    frame = ak.stock_zh_index_daily_em(symbol=symbol)
                except Exception:
                    # Eastmoney occasionally resets TLS connections from
                    # Docker networks; Tencent provides the same OHLC history.
                    frame = ak.stock_zh_index_daily_tx(symbol=symbol)
                    warnings.append(f"{name}使用腾讯备用行情")
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
        try:
            try:
                spot = ak.stock_zh_a_spot_em()
            except Exception:
                # Sina's paginated endpoint is slower but independent of the
                # Eastmoney route and supplies the breadth fields we need.
                spot = ak.stock_zh_a_spot()
                warnings.append("市场宽度使用新浪备用行情（读取较慢）")
            changes = spot["涨跌幅"].astype(float)
            advancer_ratio = float((changes > 0).sum() / max(len(changes), 1))
            # Approximation handles main board and 20% boards without claiming exact exchange stats.
            limit_down_count = int((changes <= -9.8).sum())
        except Exception as exc:
            warnings.append(f"市场宽度读取失败: {type(exc).__name__}")

        result = MarketObservation(
            as_of=date.today().isoformat(), indices=observations,
            advancer_ratio=advancer_ratio, above_ma60_ratio=None,
            limit_down_count=limit_down_count, turnover_zscore=None,
            source="AKShare/Eastmoney", coverage=["indices", "spot_breadth"], warnings=warnings,
        )
        self._write_cache("market", result)
        return result

    def _base_watchlist(self) -> list[CandidateObservation]:
        if self.watchlist_path and self.watchlist_path.exists():
            return load_watchlist_csv(self.watchlist_path)
        return [CandidateObservation(code, name, sector, theme) for code, name, sector, theme in _DEFAULT_TECH_WATCHLIST]

    def load_candidates(self) -> list[CandidateObservation]:
        cached = self._read_candidate_cache()
        if cached is not None:
            return cached
        ak = self._ak()
        candidates = self._base_watchlist()
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
