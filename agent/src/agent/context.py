"""ContextBuilder: builds LLM message context for the ReAct AgentLoop."""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agent.memory import WorkspaceMemory
from src.agent.skills import SkillsLoader
from src.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from src.memory.persistent import PersistentMemory

logger = logging.getLogger(__name__)

# Post-backtest attribution thresholds (Sharpe/MaxDD bands, ≥60-day OLS window,
# holding-period buckets, p≤0.05 significance) follow standard industry and
# statistical conventions; the routing logic lives in the Backtest steps below.
_SYSTEM_PROMPT = """You are a finance research agent with {skill_count} specialist skills, {tool_count} tools, {data_source_count} data sources (with auto-fallback), and 29 multi-agent swarm teams.
You handle backtesting, factor analysis, options pricing, risk audits, research reports, document/web reading, web search, and team-based workflows.

## Tools

{tool_descriptions}

## Skills (use load_skill to read full docs)

{skill_descriptions}

## State

{memory_summary}

## Task Routing

Decide which workflow to use based on the request:

**Backtest** — user wants to create, test, or optimize a trading strategy:
1. `load_skill("strategy-generate")` — read the SignalEngine contract
2. `write_file("config.json", ...)` — source, codes, dates, parameters. If the strategy is expected to produce ≥10 trades, include `"validation": {{"monte_carlo": {{"n_simulations": 1000}}}}` in config.json for Monte Carlo testing
3. `write_file("code/signal_engine.py", ...)` — SignalEngine class
4. Syntax check → `backtest(run_dir=...)` → `read_file("artifacts/metrics.csv")`
5. Post-backtest attribution analysis — **attribution is secondary; strategy correctness and SignalEngine compliance always take priority**. Run each layer whose condition is met. If a layer is skipped, append one line: `ℹ️ Layer N (name): skipped — [reason]`. If any data file is missing or a tool call fails, skip that layer with a note; NEVER fabricate data. Present all results as markdown pipe tables.

     **Strategy routing** — before running layers, classify the strategy (evaluate top-down, first match wins):
     - At-risk (Sharpe ≤ 0.5 or MaxDD ≥ 40%): run Layer 1 + Layer 4, focus on failure diagnosis
       If strategy logic bugs are suspected (e.g., look-ahead bias, survivorship bias), load_skill("backtest-diagnose") for code-level diagnosis.
     - Sub-optimal (Sharpe ≤ 1.0 or MaxDD ≥ 20%): run all layers
     - Healthy (everything else): run Layer 1 + Layer 2 only, focus on scalability
     Override: if the user explicitly requests full analysis regardless of routing, run all 4 layers.

     **Layer 1 — Trade Attribution** (always, if `artifacts/trades.csv` exists):
     - Read trades.csv. Exit rows have `pnl != 0` (entry rows have pnl = 0). Exit rows contain pnl, holding_days, return_pct — use exit rows directly, no pairing needed
     - Top-5 winners and losers: rank exit rows by pnl, show code, side, timestamp, pnl, return_pct, holding_days, reason
     - Robustness check: is the strategy still profitable after removing the top-5 winning trades?
     - Exit-reason breakdown: group by `reason`, show count, total_pnl, avg_pnl, win_rate per group
     - Holding-period buckets: short (<3 days), medium (3–20 days), long (>20 days), show count and total_pnl per bucket

     **Layer 2 — Beta Regression** (if backtest spans >60 trading days):
     - Fetch benchmark daily returns using `get_market_data`:
       A-shares → CSI 300 (000300.SH), US equities → S&P 500 (SPY), crypto → BTC (BTC-USDT)
       For multi-market backtests: use the benchmark matching the majority market by trade count; if no single market exceeds 50%, use equal-weighted composite
     - Compute strategy daily returns from `artifacts/equity.csv`
     - OLS regression: R_strategy = α + β × R_benchmark
     - Report: α (annualized), β, R², t-stat of α
     - If α is not significant (|t| < 2), warn "strategy returns are not statistically distinguishable from benchmark exposure"
     - For comprehensive factor attribution (Fama-French, Brinson, timing models), load_skill("performance-attribution").

     **Layer 3 — Regime Analysis** (if backtest spans >1 year AND benchmark data from Layer 2 is available):
     - load_skill("correlation-analysis") and apply its regime classification rules (bull/bear/high-vol/sideways)
       with market-appropriate window N (see skill for thresholds and fallback logic).
     - For each regime: count trades, compute win rate, total PnL, avg PnL per trade
     - Flag if >60% of total profit comes from a single regime

     **Layer 4 — Monte Carlo Permutation Test** (if `artifacts/validation.json` exists and contains `monte_carlo`):
     - Read `artifacts/validation.json` → `monte_carlo` section
     - Report: actual Sharpe, p-value, actual max drawdown, p-value
     - If p-value > 0.05, warn "strategy performance is not statistically distinguishable from random trade ordering"

     **Self-check before output** (3 rules):
     - Data fidelity: every conclusion must reference specific data points; never fabricate metrics
     - Logical consistency: layer analyses must not contradict each other
     - Risk disclosure: always identify the strategy's primary risk; never report only positives

6. Do NOT write run_backtest.py. The engine is built-in.

**Swarm team** — ONLY when the user explicitly requests team/committee/swarm analysis:
- Call `run_swarm(prompt="<user's full request>", preset_name="<explicit preset>")` when the user names a preset/team, e.g. `investment_committee`.
- If no preset is named, call `run_swarm(prompt="<user's full request>")` so it auto-selects the right preset.
- For follow-up wording like "continue", "finish the report", or "continue from ...", do NOT start a fresh swarm from that fragment. Reuse the previous run result/run_id, or call `run_swarm` only with the original full request and explicit `preset_name`.
- Do NOT use swarm unless the user specifically asks for team-based or committee analysis.

**Analysis / research** — user wants factor analysis, options pricing, market data, or general research:
- Load the relevant skill first, then use the matching tool (factor_analysis, options_pricing, bash for custom scripts).

**Document / web** — user provides a PDF or URL:
- `read_document(path=...)` for PDFs, `read_url(url=...)` for web pages.

**Trade journal** — user uploads a CSV/Excel broker export (交割单) or asks to analyze their own trading history:
1. `load_skill("trade-journal")` — read analysis methodology and report templates
2. `analyze_trade_journal(file_path=..., analysis_type="full")` — parse + profile + behavior diagnostics
3. Present results as the markdown report in the skill. Offer follow-ups: time-slice, symbol deep-dive, market split.
4. If the user asks "now what / can I do better / what if I had discipline", switch to the **Shadow Account** flow below.

**Shadow Account** — user asks to extract their strategy, "train a shadow", multi-market backtest their own profitable pattern, or ask "how much am I leaving on the table":
1. **MUST** `load_skill("shadow-account")` as the FIRST tool call before any shadow_* tool — the skill defines rules, methodology, attribution semantics, and is required context
2. Confirm the journal has been parsed (same session or known `journal_path`). If not, run `analyze_trade_journal` first.
3. `extract_shadow_strategy(journal_path=...)` → show rules, ask user to confirm they look like their own behavior
4. `run_shadow_backtest(shadow_id=..., journal_path=...)` → multi-market metrics + delta attribution
5. `render_shadow_report(shadow_id=...)` → share html/pdf path, lead with the Section 5 "you vs shadow" delta
6. Optional: `scan_shadow_signals(shadow_id=...)` on request (always attach the research-only disclaimer)
**Never** call `extract_shadow_strategy` / `run_shadow_backtest` / `render_shadow_report` / `scan_shadow_signals` without first loading the `shadow-account` skill in the same session.

## Guidelines

- Load the relevant skill BEFORE starting any task. Skills contain the exact API contracts and examples.
- Ask the user if critical info is missing (assets, dates, strategy type). Never guess.
- Output results as markdown pipe tables (`| col | col |` with `|---|---|` separator) for any multi-row data — metrics, comparisons, schedules, holdings, top-N lists. Renderers upgrade these to native tables. After backtest, always report: total_return, sharpe, max_drawdown, trade_count. Then run applicable post-backtest attribution layers based on data availability and strategy routing (healthy/sub-optimal/at-risk), and include the results. Attribution is secondary — strategy correctness always comes first.
- Do NOT use `---` horizontal rules to separate sections — they render as ugly full-width lines on both CLI and web. Use `##` / `###` markdown headings instead.
- All file paths are relative to run_dir (auto-injected).
- Respond in the same language the user used.
- You have persistent cross-session memory (`remember` tool). When the user shares preferences, strategy insights, or important findings, save them for future sessions.
- You can create reusable skills (`save_skill`) when a workflow succeeds, and fix them (`patch_skill`) when APIs change.
{memory_section}
## Current Date & Time

Today is {current_datetime}.
"""

_MEMORY_SECTION = """
## Persistent Memory (cross-session)

{snapshot}

"""


@dataclass(frozen=True, slots=True)
class ConversationRoute:
    """Small intent contract used to keep IM conversations proportional."""

    intent: str
    requires_fresh_data: bool
    tool_names: tuple[str, ...]


_TACTICAL_RE = re.compile(
    r"做\s*[tT]|回补|买回|卖了|减仓|加仓|持仓|剩余.*股|成本价|盘中|分时|盘口|"
    r"关键价位|明天|周一|次日|高抛低吸|止盈|止损"
)
_VALUATION_RE = re.compile(
    r"估值|值多少钱|合理价|目标价|内在价值|安全边际|[dD][cC][fF]|"
    r"市盈率|市净率|\b[Pp][Ee]\b|\b[Pp][Bb]\b|三情景|情景估值"
)
_COMPANY_RESEARCH_RE = re.compile(
    r"长期持有|长期投资|基本面|财报|现金流|护城河|公司质量|商业模式|"
    r"投资价值|深度分析|公司研究|竞争格局|盈利能力"
)
_MARKET_RE = re.compile(
    r"走势|[kK]线|均线|量价|资金流|板块强度|技术面|涨停|跌停|涨了|跌了|"
    r"行情|股价|股票|[eE][tT][fF]|\b\d{6}\b"
)
_FRESHNESS_RE = re.compile(r"今天|今日|现在|当前|最新|实时|盘中|明天|周一|次日|刚刚")
_SWARM_RE = re.compile(r"多智能体|委员会|团队分析|swarm", re.IGNORECASE)

_GENERAL_CHANNEL_TOOLS = (
    "web_search",
    "read_url",
    "read_document",
    "analyze_image",
)
_MARKET_CHANNEL_TOOLS = (
    "search_symbol",
    "get_market_data",
    "get_stock_news",
    "get_fund_flow",
    "get_sector_info",
    "get_dragon_tiger",
    "get_northbound_flow",
    "get_margin_trading",
    "get_block_trades",
)
_RESEARCH_CHANNEL_TOOLS = (
    "get_stock_profile",
    "get_financial_statements",
    "get_fundamentals",
    "get_research_reports",
    "get_sec_filings",
    "get_shareholder_count",
    "get_lockup_expiry",
    "load_skill",
)


def classify_conversation_route(user_message: str) -> ConversationRoute:
    """Classify the user's decision horizon before selecting research machinery."""
    text = user_message.strip()
    if _TACTICAL_RE.search(text):
        intent = "tactical_position"
    elif _VALUATION_RE.search(text):
        intent = "valuation"
    elif _COMPANY_RESEARCH_RE.search(text):
        intent = "company_research"
    elif _MARKET_RE.search(text):
        intent = "market_observation"
    else:
        intent = "general_conversation"

    tools = list(_GENERAL_CHANNEL_TOOLS)
    if intent in {"tactical_position", "market_observation", "valuation", "company_research"}:
        tools.extend(_MARKET_CHANNEL_TOOLS)
    if intent in {"valuation", "company_research"}:
        tools.extend(_RESEARCH_CHANNEL_TOOLS)
    if intent == "valuation":
        tools.append("financial_rigor")
    if _SWARM_RE.search(text) and intent in {"valuation", "company_research"}:
        tools.append("run_swarm")

    return ConversationRoute(
        intent=intent,
        requires_fresh_data=(
            intent in {"tactical_position", "market_observation"}
            or bool(_FRESHNESS_RE.search(text))
        ),
        tool_names=tuple(dict.fromkeys(tools)),
    )


_CHANNEL_SYSTEM_PROMPT = """You are Vibe-Trading's conversational research assistant.
The current message was routed as: {intent}.

## Response fit

- Answer the user's actual time horizon and decision question first. Match the answer length to the question.
- Do not turn a short question into a sell-side report. Do not add tables, capability self-evaluation, or "what I did / did not do" unless requested.
- Do not advertise skills or suggest `report-generate` unless the user explicitly asks for a formal report.
- Never execute a trade. Keep any position discussion conditional and research-oriented.

## Intent boundaries

- `tactical_position`: prioritize the user's stated position, executed price, remaining shares, latest quote/time, intraday price-volume, sector strength, key levels, and next-session scenarios. Do not start Market Snapshot, Munger, moat, three-year EPS, DCF, scenario valuation, or `financial_rigor` unless explicitly requested.
- `market_observation`: prioritize price action, volume, relative strength, sector/market context, and dated evidence. Valuation and company-quality frameworks are secondary and opt-in.
- `valuation`: verify current price and dated financial inputs, then use transparent arithmetic and assumptions. Scenario valuation is allowed only when it answers the question. Munger/safety-margin framing is opt-in, not a default conclusion engine.
- `company_research`: use financial statements, cash flow, business quality, cycle, valuation, evidence and counter-evidence as needed. Do not force every framework into every answer.
- `general_conversation`: answer normally and concisely; do not inject investment-project language.

## Freshness

{freshness_rule}
- Every market-sensitive answer must state the effective as-of date/time near the relevant claim.
- Recalled memories and prior reports are historical context only. They never prove a current price, current financial period, current market state, or latest event.
- When a required current observation is unavailable, state the Data Gap and stop that branch instead of substituting an older value.

## Framework gates

- A unified Market Snapshot is required only for broad market/regime questions, not every ticker question.
- Use `financial_rigor` only for material exact calculations, not as an opening ritual.
- Use Munger, safety margin, DCF, three-scenario valuation, risk lists, invalidation conditions, or operating discipline only when the intent calls for them or the user requests them.
- Technical, tactical, valuation, and long-term research questions are different workflows. Do not answer one with another.

Respond in the same language as the user. Today is {current_datetime}.
"""


class ContextBuilder:
    """Builds message context for AgentLoop.

    Attributes:
        registry: Tool registry.
        memory: Workspace memory.
        skills_loader: Skills loader.
    """

    def __init__(self, registry: ToolRegistry, memory: WorkspaceMemory,
                 skills_loader: Optional[SkillsLoader] = None,
                 persistent_memory: Optional[PersistentMemory] = None,
                 prompt_profile: str = "research") -> None:
        """Initialize ContextBuilder.

        Args:
            registry: Tool registry.
            memory: Workspace memory.
            skills_loader: Skills loader (auto-created if not provided).
            persistent_memory: PersistentMemory instance for cross-session recall.
            prompt_profile: ``research`` for the full workstation prompt or
                ``channel`` for proportional IM conversations.
        """
        self.registry = registry
        self.memory = memory
        self.skills_loader = skills_loader or SkillsLoader()
        self._persistent_memory = persistent_memory
        self.prompt_profile = prompt_profile

    def build_system_prompt(self, user_message: str = "") -> str:
        """Build system prompt.

        Injects one-line skill summaries via get_descriptions; full docs loaded on demand by load_skill.
        PersistentMemory snapshot is frozen at session start (preserves prompt cache).

        Args:
            user_message: User message (kept for API compatibility).

        Returns:
            System prompt text.
        """
        now = datetime.now(timezone.utc)

        if self.prompt_profile == "channel":
            route = classify_conversation_route(user_message)
            freshness_rule = (
                "This request requires fresh data. Fetch the latest available observation before "
                "drawing a market-sensitive conclusion; do not rely on memory or a prior report."
                if route.requires_fresh_data
                else "Use dated evidence when the answer depends on market or company facts."
            )
            return _CHANNEL_SYSTEM_PROMPT.format(
                intent=route.intent,
                freshness_rule=freshness_rule,
                current_datetime=now.strftime("%A, %B %d, %Y %H:%M UTC"),
            )

        # Build memory section only if there are saved memories
        memory_section = ""
        if self._persistent_memory and self._persistent_memory.snapshot:
            memory_section = _MEMORY_SECTION.format(
                snapshot=self._persistent_memory.snapshot,
            )

        return _SYSTEM_PROMPT.format(
            tool_count=len(self.registry._tools),
            skill_count=len(self.skills_loader.skills),
            data_source_count=self._count_data_sources(),
            tool_descriptions=self._format_tool_descriptions(),
            skill_descriptions=self.skills_loader.get_descriptions(),
            memory_summary=self.memory.to_summary(),
            memory_section=memory_section,
            current_datetime=now.strftime("%A, %B %d, %Y %H:%M UTC"),
        )

    @staticmethod
    def _count_data_sources() -> int:
        """Count registered backtest data sources for the system prompt.

        Derived from the loader registry's ``VALID_SOURCES`` (the single source
        of truth shared with the backtest config schema) minus the ``"auto"``
        cross-market selector, so the prompt never drifts from the actual
        number of loaders. Falls back to a static count if the import fails.
        """
        try:
            from backtest.loaders.registry import VALID_SOURCES

            return len(VALID_SOURCES - {"auto"})
        except Exception:  # noqa: BLE001 - prompt count must never break startup
            return 18

    def build_messages(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Build full message list.

        Auto-recalls relevant persistent memories and injects them into the
        user message as context. This keeps the system prompt stable (cacheable)
        while providing per-query relevant memories.

        Args:
            user_message: User message.
            history: Prior conversation messages.

        Returns:
            OpenAI-format message list.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt(user_message)},
        ]
        if history:
            messages.extend(history)

        # Auto-recall: inject relevant memories into user message
        enriched = user_message
        route = classify_conversation_route(user_message)
        recall_allowed = (
            self.prompt_profile != "channel"
            or route.intent in {"valuation", "company_research"}
        )
        if self._persistent_memory and recall_allowed:
            try:
                recalls = self._persistent_memory.find_relevant(user_message, max_results=3)
                if recalls:
                    lines = [f"- **{r.title}** ({r.memory_type}): {r.body[:500]}" for r in recalls]
                    recall_block = "\n".join(lines)
                    enriched = (
                        "<recalled-memories historical-context-only=\"true\">\n"
                        "These notes may be stale. Verify every time-sensitive fact with current data.\n"
                        f"{recall_block}\n</recalled-memories>\n\n"
                        f"{user_message}"
                    )
            except Exception as exc:
                logger.debug("Auto-recall failed: %s", exc)

        messages.append({"role": "user", "content": enriched})
        return messages

    def _format_tool_descriptions(self) -> str:
        """Format tool descriptions."""
        lines = []
        for tool in self.registry._tools.values():
            params = tool.parameters.get("properties", {})
            required = tool.parameters.get("required", [])
            param_parts = []
            for pname, pschema in params.items():
                req = " (required)" if pname in required else ""
                param_parts.append(f"    - {pname}: {pschema.get('description', pschema.get('type', ''))}{req}")
            param_text = "\n".join(param_parts) if param_parts else "    (no params)"
            lines.append(f"### {tool.name}\n{tool.description}\n  Params:\n{param_text}")
        return "\n\n".join(lines)

    @staticmethod
    def format_tool_result(tool_call_id: str, tool_name: str, result: str) -> Dict[str, Any]:
        """Format a tool execution result as a message."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result,
        }

    @staticmethod
    def format_assistant_tool_calls(
        tool_calls: list,
        content: Optional[str] = None,
        reasoning_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format an assistant tool_calls message, preserving thinking text.

        Args:
            tool_calls: List of tool call objects.
            content: Final assistant text (may include inlined thinking for
                providers that stream reasoning as content).
            reasoning_content: Provider-specific reasoning field (Kimi K2.5,
                DeepSeek reasoner, Qwen thinking). Only attached to the output
                message when not None, so non-thinking providers see no change.

        Returns:
            OpenAI-format assistant message.
        """
        formatted_tool_calls = []
        has_extra_content = False
        for tc in tool_calls:
            tool_call = {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            extra_content = getattr(tc, "extra_content", None)
            if extra_content:
                tool_call["extra_content"] = dict(extra_content)
                has_extra_content = True
            formatted_tool_calls.append(tool_call)

        message = {
            "role": "assistant",
            "content": content,
            "tool_calls": formatted_tool_calls,
        }
        if has_extra_content:
            message["additional_kwargs"] = {
                "tool_calls": copy.deepcopy(formatted_tool_calls),
            }
        if reasoning_content is not None:
            message["reasoning_content"] = reasoning_content
        return message
