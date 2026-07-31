"""Professional daily research report for the user's focused A-share watchlist.

The service composes existing Vibe-Trading read-only capabilities instead of
creating a second research stack:

* the shared market loader supplies point-in-time OHLCV;
* Value Hunter supplies the official current-day limit-down pool;
* existing Vibe tools supply financials, margin data, fund flow, sectors and
  news;
* Investment Research's atomic report store persists the JSON-safe report.

It never schedules work, sends notifications, or places orders.  The output is
an evidence-backed research posture, not a trade instruction.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from src.config.paths import get_runtime_root
from src.market_data import fetch_market_data
from src.value_hunter.models import MarketObservation
from src.value_hunter.providers import AkshareProvider

from .daily_candidate_bridge import evaluate_daily_candidate
from .report_storage import ReportStorage
from .reviewed_context import ReviewedResearchContextResolution


REPORT_VERSION = "2.0"
TRADING_DAYS = 60
ASSET_PANIC_RETURN_PCT = -30.0
MARKET_PANIC_POINT_CHANGE = -200.0
LIMIT_DOWN_PANIC_COUNT = 1000
SHANGHAI_INDEX = "000001.SH"
BANK_STYLE_PROXY = "512800.SH"

WATCHLIST = (
    {
        "symbol": "600522.SH",
        "name": "中天科技",
        "asset_type": "stock",
        "thesis_id": "thesis:600522.SH",
        "valuation": {"bear_pe": 15.0, "base_pe": 22.0, "bull_pe": 30.0},
    },
    {
        "symbol": "588000.SH",
        "name": "科创50ETF",
        "asset_type": "etf",
        "thesis_id": "thesis:588000.SH",
        "valuation": None,
    },
)

MarketFetcher = Callable[..., dict[str, Any]]
MarketContextLoader = Callable[[], MarketObservation]
ResearchEnricher = Callable[[str], dict[str, Any]]
ResearchContextLoader = Callable[..., ReviewedResearchContextResolution]


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    dates: tuple[str, ...]
    closes: tuple[float, ...]

    @property
    def latest_date(self) -> str:
        return self.dates[-1]

    @property
    def latest_close(self) -> float:
        return self.closes[-1]

    def return_pct(self, days: int) -> float | None:
        if len(self.closes) <= days or self.closes[-(days + 1)] == 0:
            return None
        return (self.closes[-1] / self.closes[-(days + 1)] - 1.0) * 100.0

    def point_change(self, days: int) -> float | None:
        if len(self.closes) <= days:
            return None
        return self.closes[-1] - self.closes[-(days + 1)]

    def moving_average(self, days: int) -> float | None:
        if len(self.closes) < days:
            return None
        return statistics.fmean(self.closes[-days:])

    def rsi(self, days: int = 14) -> float | None:
        if len(self.closes) <= days:
            return None
        changes = [
            self.closes[index] - self.closes[index - 1]
            for index in range(len(self.closes) - days, len(self.closes))
        ]
        average_gain = statistics.fmean(max(value, 0.0) for value in changes)
        average_loss = statistics.fmean(max(-value, 0.0) for value in changes)
        if average_loss == 0:
            return 100.0
        relative_strength = average_gain / average_loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    def annualized_volatility(self, days: int = 20) -> float | None:
        if len(self.closes) <= days:
            return None
        returns = [
            self.closes[index] / self.closes[index - 1] - 1.0
            for index in range(len(self.closes) - days, len(self.closes))
            if self.closes[index - 1] > 0
        ]
        if len(returns) < 2:
            return None
        return statistics.stdev(returns) * math.sqrt(252.0) * 100.0

    def history_position(self, days: int = 252) -> dict[str, float | None]:
        window = self.closes[-min(days, len(self.closes)) :]
        high = max(window)
        low = min(window)
        percentile = None if high == low else (self.latest_close - low) / (high - low) * 100.0
        return {
            "high": high,
            "low": low,
            "drawdown_from_high_pct": (self.latest_close / high - 1.0) * 100.0,
            "price_percentile": percentile,
        }


class VibeResearchEnricher:
    """Call existing Vibe read-only tools and normalize their evidence."""

    def __call__(self, symbol: str) -> dict[str, Any]:
        from src.tools.financial_statements_tool import FinancialStatementsTool
        from src.tools.fund_flow_tool import FundFlowTool
        from src.tools.margin_trading_tool import MarginTradingTool
        from src.tools.sector_tool import SectorInfoTool
        from src.tools.stock_news_tool import StockNewsTool

        calls = {
            "financials": lambda: FinancialStatementsTool().execute(
                code=symbol, statement="indicators", period="annual"
            ),
            "margin": lambda: MarginTradingTool().execute(code=symbol, days=30),
            "fund_flow": lambda: FundFlowTool().execute(
                codes=[symbol], period="daily", days=20
            ),
            "sectors": lambda: SectorInfoTool().execute(
                code=symbol, mode="membership"
            ),
            "news": lambda: StockNewsTool().execute(
                code=symbol, scope="stock", limit=8
            ),
        }
        payloads: dict[str, dict[str, Any]] = {}
        gaps: list[str] = []
        with ThreadPoolExecutor(max_workers=len(calls)) as executor:
            futures = {executor.submit(callback): name for name, callback in calls.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    decoded = json.loads(future.result())
                    if isinstance(decoded, dict):
                        payloads[name] = decoded
                    else:
                        gaps.append(f"{name}: Vibe工具返回了非对象数据")
                except Exception as exc:  # one upstream must not discard the report
                    gaps.append(f"{name}: {type(exc).__name__}")

        return {
            "financials": _financial_snapshot(payloads.get("financials"), symbol),
            "margin": _margin_snapshot(payloads.get("margin")),
            "fund_flow": _fund_flow_snapshot(payloads.get("fund_flow"), symbol),
            "sectors": _sector_snapshot(payloads.get("sectors")),
            "news": _news_snapshot(payloads.get("news")),
            "data_gaps": [
                *gaps,
                *_payload_gaps(payloads, ("financials", "margin", "fund_flow", "sectors", "news")),
            ],
            "sources": {
                key: str(value.get("source", "unavailable"))
                for key, value in payloads.items()
            },
        }


class DailyOpportunityReportService:
    """Generate and atomically persist the professional daily report."""

    def __init__(
        self,
        *,
        market_fetcher: MarketFetcher = fetch_market_data,
        market_context_loader: MarketContextLoader | None = None,
        research_enricher: ResearchEnricher | None = None,
        research_context_loader: ResearchContextLoader | None = None,
        storage: ReportStorage | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._market_fetcher = market_fetcher
        self._market_context_loader = market_context_loader or self._default_market_context
        self._research_enricher = research_enricher or VibeResearchEnricher()
        self._research_context_loader = research_context_loader
        self._storage = storage or ReportStorage(
            get_runtime_root() / "investment-research" / "daily-opportunity-reports"
        )
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "read_only": True,
            "watchlist": [
                {
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "asset_type": item["asset_type"],
                }
                for item in WATCHLIST
            ],
            "rules": {
                "lookback_trading_days": TRADING_DAYS,
                "asset_return_pct_lte": ASSET_PANIC_RETURN_PCT,
                "shanghai_point_change_lte": MARKET_PANIC_POINT_CHANGE,
                "limit_down_count_gte": LIMIT_DOWN_PANIC_COUNT,
                "match": "any",
            },
            "capabilities": [
                "Vibe行情与多源降级",
                "历史价格位置与技术面",
                "财务与静态估值情景",
                "融资融券与资金流",
                "行业风格与新闻证据",
                "Vibe Agent深度研判",
            ],
            "notifications": False,
            "scheduler": False,
            "trading": False,
        }

    def run(self, *, as_of: date | None = None) -> dict[str, Any]:
        report_date = as_of or self._today()
        start_date = report_date - timedelta(days=400)
        requested_symbols = [
            *(item["symbol"] for item in WATCHLIST),
            SHANGHAI_INDEX,
            BANK_STYLE_PROXY,
        ]
        raw: dict[str, Any] = {}
        unresolved: set[str] = set()
        for symbol in requested_symbols:
            component = self._market_fetcher(
                codes=[symbol],
                start_date=start_date.isoformat(),
                end_date=(report_date + timedelta(days=1)).isoformat(),
                source="auto",
                interval="1D",
                max_rows=0,
                max_fallback_attempts=5,
            )
            if isinstance(component, dict) and symbol in component:
                raw[symbol] = component[symbol]
            else:
                unresolved.add(symbol)

        series: dict[str, PriceSeries] = {}
        data_gaps: list[str] = []
        for symbol in requested_symbols:
            parsed = _parse_price_series(symbol, raw.get(symbol), report_date)
            if parsed is None:
                data_gaps.append(f"{symbol}: 至少需要61个有效交易日收盘价")
                unresolved.add(symbol)
            else:
                series[symbol] = parsed

        is_current_report = report_date == self._today()
        market_context: MarketObservation | None = None
        if is_current_report:
            try:
                market_context = self._market_context_loader()
            except Exception as exc:
                data_gaps.append(f"全市场跌停数量不可用: {type(exc).__name__}")
        else:
            data_gaps.append("历史报告不使用当前涨跌停池，避免未来数据穿越")

        limit_down_count = market_context.limit_down_count if market_context else None
        market_source = market_context.source if market_context else "unavailable"
        market_warnings = list(market_context.warnings) if market_context else []
        if limit_down_count is None:
            data_gaps.append("全市场跌停数量缺失，千股跌停条件未参与判断")

        shanghai = series.get(SHANGHAI_INDEX)
        bank = series.get(BANK_STYLE_PROXY)
        technology = series.get("588000.SH")
        shanghai_change = shanghai.point_change(TRADING_DAYS) if shanghai else None
        market_triggers = _market_triggers(shanghai_change, limit_down_count)
        style_rotation = _style_rotation(bank, technology)
        market_report = {
            "panic": bool(market_triggers),
            "regime": _market_regime(shanghai, market_triggers),
            "panic_triggers": market_triggers,
            "shanghai_symbol": SHANGHAI_INDEX,
            "shanghai_effective_trade_date": shanghai.latest_date if shanghai else None,
            "shanghai_close": _round(shanghai.latest_close if shanghai else None, 4),
            "shanghai_5d_return_pct": _series_return(shanghai, 5),
            "shanghai_20d_return_pct": _series_return(shanghai, 20),
            "shanghai_60d_return_pct": _series_return(shanghai, 60),
            "shanghai_60d_point_change": _round(shanghai_change, 2),
            "limit_down_count": limit_down_count,
            "limit_down_count_quality": (
                "official_pool"
                if limit_down_count is not None and "official limit-down pool" in market_source
                else "cached_or_approximate"
                if limit_down_count is not None
                else "unavailable"
            ),
            "market_context_source": market_source,
            "style_rotation": style_rotation,
        }

        enrichments: dict[str, dict[str, Any]] = {}
        if is_current_report:
            stock_symbols = [
                item["symbol"] for item in WATCHLIST if item["asset_type"] == "stock"
            ]
            with ThreadPoolExecutor(max_workers=len(stock_symbols) or 1) as executor:
                futures = {
                    executor.submit(self._research_enricher, symbol): symbol
                    for symbol in stock_symbols
                }
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        enrichments[symbol] = future.result()
                    except Exception as exc:
                        data_gaps.append(f"{symbol}: Vibe研究工具失败 {type(exc).__name__}")
        else:
            data_gaps.append("历史报告跳过当前财务、新闻和资金工具，避免数据穿越")

        assets: list[dict[str, Any]] = []
        for definition in WATCHLIST:
            symbol = definition["symbol"]
            item = series.get(symbol)
            enrichment = enrichments.get(symbol, {})
            if enrichment:
                data_gaps.extend(
                    f"{symbol}: {gap}" for gap in enrichment.get("data_gaps", [])
                )
            asset_report = _build_asset_report(
                definition=definition,
                item=item,
                shanghai=shanghai,
                market_triggers=market_triggers,
                market_panic=bool(market_triggers),
                enrichment=enrichment,
            )
            formal = evaluate_daily_candidate(
                definition=definition,
                asset_report=asset_report,
                market_report=market_report,
                report_date=report_date,
                reviewed_context=(
                    self._research_context_loader(
                        thesis_id=str(definition["thesis_id"]),
                        information_cutoff=datetime.combine(
                            report_date, time(8), timezone.utc
                        ),
                    )
                    if self._research_context_loader is not None
                    else ReviewedResearchContextResolution(
                        None, ("reviewed research context loader is not configured",)
                    )
                ),
            )
            assets.append(_apply_formal_candidate_decision(asset_report, formal))

        report = {
            "report_version": REPORT_VERSION,
            "report_date": report_date.isoformat(),
            "generated_at": self._now().isoformat(),
            "read_only": True,
            "shadow_run": True,
            "market": market_report,
            "assets": assets,
            "data_sources": {
                "prices": "Vibe market loader auto fallback chain",
                "market_context": market_source,
                "deep_research": "Vibe existing read-only tools",
            },
            "data_gaps": list(dict.fromkeys([*data_gaps, *market_warnings])),
            "unresolved_symbols": sorted(unresolved),
            "conclusion": _conclusion(assets, style_rotation),
            "research_workflow": _research_workflow(assets),
            "agent_prompt": _agent_prompt(assets, style_rotation, report_date),
            "notifications_sent": False,
            "scheduler_started": False,
            "trading_executed": False,
        }
        self._storage.save_report(report, report_date)
        return report

    def latest(self) -> dict[str, Any] | None:
        return self._storage.load_latest()

    @staticmethod
    def _default_market_context() -> MarketObservation:
        provider = AkshareProvider(
            cache_dir=get_runtime_root() / "value-hunter" / "cache"
        )
        return provider.load_limit_down_context()


def _build_asset_report(
    *,
    definition: dict[str, Any],
    item: PriceSeries | None,
    shanghai: PriceSeries | None,
    market_triggers: list[dict[str, Any]],
    market_panic: bool,
    enrichment: dict[str, Any],
) -> dict[str, Any]:
    symbol = str(definition["symbol"])
    name = str(definition["name"])
    triggers = list(market_triggers)
    support = [trigger["label"] for trigger in market_triggers]
    counter: list[str] = []
    technical = _technical_snapshot(item)
    financials = enrichment.get("financials")
    valuation = _valuation_snapshot(
        item.latest_close if item else None,
        financials,
        definition.get("valuation"),
    )

    asset_return = item.return_pct(60) if item else None
    if asset_return is not None and asset_return <= ASSET_PANIC_RETURN_PCT:
        trigger = {
            "code": "ASSET_PANIC",
            "label": f"{name}60个交易日跌幅超过30%",
            "observed": round(asset_return, 2),
            "threshold": ASSET_PANIC_RETURN_PCT,
        }
        triggers.insert(0, trigger)
        support.insert(0, trigger["label"])
    elif asset_return is not None:
        counter.append(f"标的60日跌幅为{asset_return:.2f}%，尚未达到30%")
    else:
        counter.append("行情覆盖不足，暂不升级行动等级")

    entry = _entry_framework(
        definition=definition,
        item=item,
        technical=technical,
        valuation=valuation,
        market_panic=market_panic,
    )
    action_level = {
        "wait": "watch",
        "observe": "research",
        "prepare": "prepare",
        "research_zone": "action_candidate",
    }[entry["status"]]
    history = item.history_position() if item else {
        "high": None,
        "low": None,
        "drawdown_from_high_pct": None,
        "price_percentile": None,
    }
    return {
        "symbol": symbol,
        "name": name,
        "asset_type": definition["asset_type"],
        "effective_trade_date": item.latest_date if item else None,
        "latest_close": _round(item.latest_close if item else None, 4),
        "return_5d_pct": _series_return(item, 5),
        "return_20d_pct": _series_return(item, 20),
        "return_60d_pct": _round(asset_return, 2),
        "relative_to_shanghai_20d_pct": _relative_return(item, shanghai, 20),
        "history_position": {
            key: _round(value, 2) for key, value in history.items()
        },
        "technical": technical,
        "fundamentals": financials,
        "valuation": valuation,
        "margin": enrichment.get("margin"),
        "fund_flow": enrichment.get("fund_flow"),
        "sectors": enrichment.get("sectors", []),
        "news": enrichment.get("news", []),
        "panic": bool(triggers),
        "panic_triggers": triggers,
        "action_level": action_level,
        "action_label": _action_label(action_level),
        "entry_framework": entry,
        "supporting_evidence": support or ["当前未触发既定恐慌条件"],
        "counter_evidence": counter,
        "next_condition": entry["next_review_condition"],
        "data_source": "vibe_market_loader_auto",
        "research_sources": enrichment.get("sources", {}),
        "data_quality": "provider_acquired_unverified",
    }


def _apply_formal_candidate_decision(
    asset_report: dict[str, Any],
    formal: dict[str, Any],
) -> dict[str, Any]:
    """Make the canonical Candidate pipeline the sole Action Level authority."""
    action_level = str(formal["action_level"])
    entry_status = {
        "watch": "wait",
        "research": "observe",
        "prepare": "prepare",
        "action_candidate": "research_zone",
    }[action_level]
    entry = dict(asset_report["entry_framework"])
    entry.update(
        {
            "status": entry_status,
            "label": _action_label(action_level),
            "summary": (
                "Action Level comes from the canonical Research Candidate pipeline. "
                "Price zones remain research references only; automatic evidence does "
                "not initialize a Thesis or prove a mispricing."
            ),
            "conditions": list(
                dict.fromkeys(
                    [
                        *entry.get("conditions", ()),
                        *(f"formal gate: {item}" for item in formal["blocked_reasons"]),
                    ]
                )
            ),
            "next_review_condition": formal["first_rejection_question"],
        }
    )
    valuation = dict(asset_report["valuation"])
    valuation.update(
        {
            "formal_status": formal["valuation_status"],
            "decision_source": formal["decision_source"],
            "provisional": formal["valuation_status"] != "configured",
        }
    )
    return {
        **asset_report,
        "action_level": action_level,
        "action_label": _action_label(action_level),
        "entry_framework": entry,
        "valuation": valuation,
        "next_condition": formal["first_rejection_question"],
        "formal_research": formal,
    }


def _technical_snapshot(item: PriceSeries | None) -> dict[str, Any]:
    if item is None:
        return {
            "ma20": None, "ma60": None, "ma120": None, "rsi14": None,
            "volatility20_annualized_pct": None, "trend": "数据不足",
            "stabilization": False,
        }
    ma20 = item.moving_average(20)
    ma60 = item.moving_average(60)
    ma120 = item.moving_average(120)
    rsi = item.rsi(14)
    return {
        "ma20": _round(ma20, 4),
        "ma60": _round(ma60, 4),
        "ma120": _round(ma120, 4),
        "distance_to_ma20_pct": _round(
            (item.latest_close / ma20 - 1.0) * 100.0 if ma20 else None, 2
        ),
        "rsi14": _round(rsi, 1),
        "volatility20_annualized_pct": _round(item.annualized_volatility(), 1),
        "trend": _trend_label(item.latest_close, ma20, ma60, ma120),
        "stabilization": bool(
            ma20
            and item.latest_close >= ma20
            and (item.return_pct(5) or 0.0) > 0.0
        ),
    }


def _valuation_snapshot(
    price: float | None,
    financials: dict[str, Any] | None,
    assumptions: dict[str, float] | None,
) -> dict[str, Any]:
    if not assumptions:
        return {
            "available": False,
            "method": "ETF需要指数层估值数据，当前不使用个股PE替代",
        }
    eps = _number((financials or {}).get("eps"))
    if price is None or eps is None or eps <= 0:
        return {
            "available": False,
            "method": "最近年度EPS静态PE情景",
            "reason": "有效EPS或价格缺失",
        }
    bear = eps * assumptions["bear_pe"]
    base = eps * assumptions["base_pe"]
    bull = eps * assumptions["bull_pe"]
    current_pe = price / eps
    return {
        "available": True,
        "method": "最近年度EPS静态PE情景（非DCF、非目标价）",
        "eps": _round(eps, 4),
        "eps_period": (financials or {}).get("period_end"),
        "current_pe": _round(current_pe, 2),
        "bear": {"pe": assumptions["bear_pe"], "price": _round(bear, 2)},
        "base": {"pe": assumptions["base_pe"], "price": _round(base, 2)},
        "bull": {"pe": assumptions["bull_pe"], "price": _round(bull, 2)},
        "premium_to_base_pct": _round((price / base - 1.0) * 100.0, 2),
        "assessment": (
            "进入基础情景以下"
            if price <= base
            else "介于基础与乐观情景"
            if price <= bull
            else "高于乐观情景"
        ),
    }


def _entry_framework(
    *,
    definition: dict[str, Any],
    item: PriceSeries | None,
    technical: dict[str, Any],
    valuation: dict[str, Any],
    market_panic: bool,
) -> dict[str, Any]:
    if item is None:
        return {
            "status": "wait",
            "label": "等待数据",
            "summary": "价格序列不足，暂不判断研究区间。",
            "reasons": [],
            "conditions": ["补齐至少61个交易日行情"],
            "reference_zones": [],
            "next_review_condition": "行情数据完整后重新评估",
        }

    history = item.history_position()
    drawdown = _number(history["drawdown_from_high_pct"])
    stabilization = bool(technical.get("stabilization"))
    reasons: list[str] = []
    conditions: list[str] = []
    zones: list[dict[str, Any]] = []

    if market_panic:
        reasons.append("大盘已触发恐慌条件，存在系统性错杀研究价值")
    if drawdown is not None and drawdown <= -30:
        reasons.append(f"较近一年高点回撤{drawdown:.1f}%")
    if technical.get("rsi14") is not None and technical["rsi14"] <= 35:
        reasons.append(f"RSI14为{technical['rsi14']:.1f}，处于偏弱/超卖区域")
    if stabilization:
        reasons.append("收盘重新站上MA20且5日收益转正，出现初步止跌信号")
    else:
        conditions.append("等待收盘重新站上MA20且5日收益转正")

    if valuation.get("available"):
        base_price = valuation["base"]["price"]
        bear_price = valuation["bear"]["price"]
        bull_price = valuation["bull"]["price"]
        zones = [
            {"name": "深度研究区", "low": bear_price, "high": base_price, "basis": "15–22倍静态PE"},
            {"name": "谨慎观察区", "low": base_price, "high": bull_price, "basis": "22–30倍静态PE"},
        ]
        if item.latest_close <= base_price:
            reasons.append("价格已进入基础情景估值以下")
        else:
            conditions.append(f"价格进入基础情景附近（约{base_price:.2f}）")
        if item.latest_close <= base_price and stabilization and (drawdown or 0) <= -30:
            status, label = "research_zone", "分批建仓研究区"
        elif item.latest_close <= base_price and (drawdown or 0) <= -20:
            status, label = "prepare", "准备区"
        elif market_panic or (drawdown or 0) <= -20:
            status, label = "observe", "重点观察"
        else:
            status, label = "wait", "继续等待"
    else:
        ma60 = technical.get("ma60")
        low = history.get("low")
        if low is not None and ma60 is not None:
            zones = [
                {
                    "name": "技术观察区",
                    "low": _round(low, 4),
                    "high": _round(ma60, 4),
                    "basis": "近一年低点至MA60，仅用于技术观察",
                }
            ]
        if stabilization and (drawdown or 0) <= -20:
            status, label = "prepare", "准备区"
        elif market_panic or (technical.get("rsi14") or 100) <= 35:
            status, label = "observe", "重点观察"
        else:
            status, label = "wait", "继续等待"
        conditions.append("补充科创50指数PE/PB历史分位后再判断低估")

    if definition["asset_type"] == "stock":
        conditions.append("确认最新财报毛利率、现金流与净利润没有结构性恶化")
        conditions.append("观察融资余额去化是否趋稳，避免把强平过程误判为底部")

    return {
        "status": status,
        "label": label,
        "summary": (
            f"当前属于“{label}”。满足条件越多，研究优先级越高；"
            "本结论不是买入指令，也不预测精确最低点。"
        ),
        "reasons": reasons,
        "conditions": list(dict.fromkeys(conditions)),
        "reference_zones": zones,
        "next_review_condition": conditions[0] if conditions else "下一交易日更新证据",
    }


def _market_triggers(
    shanghai_change: float | None, limit_down_count: int | None
) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    if shanghai_change is not None and shanghai_change <= MARKET_PANIC_POINT_CHANGE:
        triggers.append({
            "code": "MARKET_DRAWDOWN",
            "label": "上证指数60个交易日下跌超过200点",
            "observed": round(shanghai_change, 2),
            "threshold": MARKET_PANIC_POINT_CHANGE,
        })
    if limit_down_count is not None and limit_down_count >= LIMIT_DOWN_PANIC_COUNT:
        triggers.append({
            "code": "MARKET_CRASH",
            "label": "全市场出现千股跌停",
            "observed": limit_down_count,
            "threshold": LIMIT_DOWN_PANIC_COUNT,
        })
    return triggers


def _style_rotation(
    bank: PriceSeries | None, technology: PriceSeries | None
) -> dict[str, Any]:
    bank_5d = _series_return(bank, 5)
    bank_20d = _series_return(bank, 20)
    tech_5d = _series_return(technology, 5)
    tech_20d = _series_return(technology, 20)
    spread = (
        bank_20d - tech_20d
        if bank_20d is not None and tech_20d is not None
        else None
    )
    if spread is None:
        interpretation = "银行与科技风格代理数据不足"
    elif spread >= 5:
        interpretation = "银行显著跑赢科技，市场偏防守/权重风格"
    elif spread <= -5:
        interpretation = "科技显著跑赢银行，市场偏成长风格"
    else:
        interpretation = "银行与科技差异有限，暂无极端风格偏离"
    return {
        "bank_proxy": BANK_STYLE_PROXY,
        "technology_proxy": "588000.SH",
        "bank_5d_return_pct": bank_5d,
        "bank_20d_return_pct": bank_20d,
        "technology_5d_return_pct": tech_5d,
        "technology_20d_return_pct": tech_20d,
        "bank_minus_technology_20d_pct": _round(spread, 2),
        "interpretation": interpretation,
        "state_support_inference": (
            "行情相对强弱只能识别权重风格，不能单独证明国家队护盘；"
            "确认主体需要ETF申赎、中央汇金公告或其他可追溯证据。"
        ),
    }


def _market_regime(
    shanghai: PriceSeries | None, triggers: list[dict[str, Any]]
) -> str:
    if triggers:
        return "恐慌/系统性回撤"
    return_20d = shanghai.return_pct(20) if shanghai else None
    if return_20d is None:
        return "数据不足"
    if return_20d <= -5:
        return "调整"
    if return_20d >= 5:
        return "上行"
    return "震荡"


def _financial_snapshot(
    payload: dict[str, Any] | None, symbol: str
) -> dict[str, Any] | None:
    if not payload or not payload.get("ok"):
        return None
    value = (payload.get("data") or {}).get(symbol)
    periods = value.get("periods") if isinstance(value, dict) else None
    if not isinstance(periods, list) or not periods:
        return None
    row = periods[0]
    return {
        "period_end": str(row.get("REPORT_DATE", ""))[:10] or None,
        "notice_date": str(row.get("NOTICE_DATE", ""))[:10] or None,
        "eps": _number(row.get("EPSJB")),
        "revenue_cny": _number(row.get("TOTALOPERATEREVE")),
        "revenue_yoy_pct": _number(row.get("TOTALOPERATEREVETZ")),
        "net_profit_cny": _number(row.get("PARENTNETPROFIT")),
        "net_profit_yoy_pct": _number(row.get("PARENTNETPROFITTZ")),
        "roe_pct": _number(row.get("ROEJQ")),
        "gross_margin_pct": _number(row.get("XSMLL")),
        "net_margin_pct": _number(row.get("XSJLL")),
        "operating_cashflow_to_revenue_pct": _number(row.get("JYXJLYYSR")),
        "debt_ratio_pct": _number(row.get("ZCFZL")),
        "source": payload.get("source"),
    }


def _margin_snapshot(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload or not payload.get("ok"):
        return None
    rows = (payload.get("data") or {}).get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    latest = rows[0]
    oldest = rows[-1]
    latest_balance = _number(latest.get("financing_balance"))
    oldest_balance = _number(oldest.get("financing_balance"))
    change = (
        (latest_balance / oldest_balance - 1.0) * 100.0
        if latest_balance is not None and oldest_balance
        else None
    )
    return {
        "latest_date": latest.get("trade_date"),
        "financing_balance_cny": latest_balance,
        "short_balance_cny": _number(latest.get("short_balance")),
        "period_change_pct": _round(change, 2),
        "period_days": len(rows),
        "interpretation": (
            "融资余额明显去化，杠杆出清仍是价格波动的重要变量"
            if change is not None and change <= -15
            else "融资余额变化相对温和"
            if change is not None
            else "融资余额变化暂不可用"
        ),
        "source": payload.get("source"),
    }


def _fund_flow_snapshot(
    payload: dict[str, Any] | None, symbol: str
) -> dict[str, Any] | None:
    if not payload or not payload.get("ok"):
        return None
    value = (payload.get("data") or {}).get(symbol)
    if not isinstance(value, dict) or value.get("error"):
        return None
    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    main_values = [_number(row.get("main")) for row in rows]
    valid = [value for value in main_values if value is not None]
    if not valid:
        return None
    return {
        "latest_date": rows[-1].get("timestamp"),
        "main_net_inflow_5d_cny": sum(valid[-5:]),
        "main_net_inflow_20d_cny": sum(valid[-20:]),
        "source": payload.get("source"),
    }


def _sector_snapshot(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload or not payload.get("ok"):
        return []
    boards = (payload.get("data") or {}).get("boards")
    if not isinstance(boards, list):
        return []
    return [
        {
            "code": row.get("board_code"),
            "name": row.get("board_name"),
            "change_pct": _number(row.get("change_pct")),
        }
        for row in boards[:10]
        if isinstance(row, dict) and row.get("board_name")
    ]


def _news_snapshot(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload or not payload.get("ok"):
        return []
    articles = (payload.get("data") or {}).get("articles")
    if not isinstance(articles, list):
        return []
    return [
        {
            "title": _plain_text(row.get("title")),
            "url": row.get("url"),
            "source": row.get("source"),
            "published": row.get("published"),
            "snippet": _plain_text(row.get("snippet")),
        }
        for row in articles[:6]
        if isinstance(row, dict) and row.get("title")
    ]


def _payload_gaps(
    payloads: dict[str, dict[str, Any]], expected: tuple[str, ...]
) -> list[str]:
    gaps: list[str] = []
    for name in expected:
        payload = payloads.get(name)
        if payload is None:
            gaps.append(f"{name}: 未返回")
        elif payload.get("ok") is False:
            gaps.append(f"{name}: 上游工具返回失败")
        elif name == "fund_flow":
            data = payload.get("data") or {}
            if any(isinstance(value, dict) and value.get("error") for value in data.values()):
                gaps.append("fund_flow: 上游暂时不可用")
    return gaps


def _parse_price_series(
    symbol: str, value: Any, cutoff: date
) -> PriceSeries | None:
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        value = value["data"]
    if not isinstance(value, list):
        return None
    rows: list[tuple[str, float]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        raw_date = next(
            (
                row.get(key)
                for key in ("trade_date", "date", "datetime", "time", "index")
                if row.get(key) is not None
            ),
            None,
        )
        raw_close = next(
            (
                row.get(key)
                for key in ("close", "Close", "收盘")
                if row.get(key) is not None
            ),
            None,
        )
        try:
            parsed_date = date.fromisoformat(str(raw_date)[:10])
            parsed_close = float(raw_close)
        except (TypeError, ValueError):
            continue
        if parsed_date <= cutoff and parsed_close > 0:
            rows.append((parsed_date.isoformat(), parsed_close))
    ordered = sorted(dict(rows).items())
    if len(ordered) <= TRADING_DAYS:
        return None
    return PriceSeries(
        symbol=symbol,
        dates=tuple(item[0] for item in ordered),
        closes=tuple(item[1] for item in ordered),
    )


def _trend_label(
    price: float, ma20: float | None, ma60: float | None, ma120: float | None
) -> str:
    if ma20 is None or ma60 is None:
        return "数据不足"
    if price >= ma20 >= ma60 and (ma120 is None or ma60 >= ma120):
        return "多头趋势"
    if price < ma20 < ma60 and (ma120 is None or ma60 < ma120):
        return "空头趋势"
    if price >= ma20:
        return "短线修复"
    return "弱势震荡"


def _action_label(level: str) -> str:
    return {
        "watch": "继续观察",
        "research": "恐慌观察",
        "prepare": "准备研究与资金",
        "action_candidate": "分批建仓观察区",
    }[level]


def _conclusion(
    assets: list[dict[str, Any]], style_rotation: dict[str, Any]
) -> str:
    order = {"watch": 0, "research": 1, "prepare": 2, "action_candidate": 3}
    highest = max(assets, key=lambda item: order[item["action_level"]])
    if highest["action_level"] == "watch":
        return "今天没有标的触发既定恐慌条件，继续观察。"
    entry = highest["entry_framework"]
    return (
        f"当前研究优先级最高的是{highest['name']}：{entry['label']}。"
        f"{style_rotation['interpretation']}。"
        "系统给出的是条件式研究区间，不是精确底部预测或交易指令。"
    )


def _agent_prompt(
    assets: list[dict[str, Any]],
    style_rotation: dict[str, Any],
    report_date: date,
) -> str:
    compact = [
        {
            "symbol": item["symbol"],
            "name": item["name"],
            "close": item["latest_close"],
            "returns": {
                "5d": item["return_5d_pct"],
                "20d": item["return_20d_pct"],
                "60d": item["return_60d_pct"],
            },
            "technical": item["technical"],
            "valuation": item["valuation"],
            "margin": item["margin"],
            "entry_framework": item["entry_framework"],
            "news": item["news"][:4],
        }
        for item in assets
    ]
    return (
        f"请启动一次Vibe-Trading“全面投研复核”，使用现有市场、财务、新闻、"
        f"资金流、行业、会话记忆、价值投资委员会与投资委员会能力，对以下"
        f"{report_date.isoformat()}盘后研究快照做深度复核：\n"
        f"{json.dumps({'assets': compact, 'style_rotation': style_rotation}, ensure_ascii=False)}\n\n"
        "请按以下流程工作：\n"
        "1. 搜索历史会话和持久化记忆，找出既有投资逻辑与旧判断；\n"
        "2. 用价值投资委员会（巴菲特/芒格/段永平/李录视角）审查生意、现金流、"
        "管理层、护城河和估值；\n"
        "3. 用投资委员会进行多头、空头、风险审查和最终研究优先级辩论；\n"
        "4. 对公司使用精确PE/PB/ROE验算和三情景估值；对ETF使用指数估值、"
        "成分与风格暴露，缺数据时明确阻断；\n"
        "5. 检查技术面、融资去杠杆、市场风格、消息面和可能的独立利空；\n"
        "6. 形成可证伪Thesis：支持证据、反方证据、催化剂、失效条件、复核时间；\n"
        "7. 给出Wait/Research/Prepare/Action Candidate行动等级，以及条件式研究区、"
        "加仓前提、减仓/退出条件；\n"
        "8. 若达到Action Candidate，生成只读影子计划和T+20/T+60跟踪方案，"
        "不创建真实订单。\n\n"
        "请重点回答：当前下跌主要是基本面、估值、杠杆还是市场风格；是否存在"
        "错误定价；哪些条件满足后才值得考虑分批行动；什么证据出现后必须放弃。"
        "不要把银行相对强势直接等同于国家队护盘；若缺乏可追溯证据请明确说明。"
        "不要为了显得全面而调用与标的不相关的期权或300股因子模型；说明跳过原因。"
        "输出研究报告与影子观察方案，不输出自动交易指令。"
    )


def _research_workflow(assets: list[dict[str, Any]]) -> dict[str, Any]:
    action_candidate = any(
        item.get("action_level") == "action_candidate" for item in assets
    )
    return {
        "mode": "vibe_comprehensive_research",
        "stages": [
            {"name": "市场与风格", "status": "ready", "capabilities": ["多源行情", "大盘联动", "银行/科技风格"]},
            {"name": "公司与ETF研究", "status": "ready", "capabilities": ["财务", "估值", "资金", "新闻", "行业"]},
            {"name": "价值投资委员会", "status": "on_demand", "capabilities": ["四大师视角", "反方审查"]},
            {"name": "投资委员会", "status": "on_demand", "capabilities": ["多头", "空头", "风险", "研究决策"]},
            {"name": "Thesis与记忆", "status": "on_demand", "capabilities": ["会话搜索", "持久化记忆", "证据/反证", "失效条件"]},
            {
                "name": "影子验证",
                "status": "eligible" if action_candidate else "gated",
                "capabilities": ["只读影子计划", "T+20/T+60复核", "无真实订单"],
            },
        ],
        "skipped_by_default": [
            "300只股票IC因子合成：当前只有两个自选标的，样本不匹配",
            "期权希腊字母：当前标的不是期权合约",
            "多市场组合优化：需要用户提供完整组合与约束后再运行",
        ],
    }


def _series_return(item: PriceSeries | None, days: int) -> float | None:
    return _round(item.return_pct(days) if item else None, 2)


def _relative_return(
    asset: PriceSeries | None, benchmark: PriceSeries | None, days: int
) -> float | None:
    asset_return = asset.return_pct(days) if asset else None
    benchmark_return = benchmark.return_pct(days) if benchmark else None
    if asset_return is None or benchmark_return is None:
        return None
    return _round(asset_return - benchmark_return, 2)


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _plain_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()
