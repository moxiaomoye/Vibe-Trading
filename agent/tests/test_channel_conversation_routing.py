from __future__ import annotations

from pathlib import Path

from src.agent.context import ContextBuilder, classify_conversation_route
from src.agent.memory import WorkspaceMemory
from src.agent.tools import ToolRegistry
from src.memory.persistent import PersistentMemory
from src.tools import build_registry


def _builder(tmp_path: Path, profile: str = "channel") -> ContextBuilder:
    return ContextBuilder(
        ToolRegistry(),
        WorkspaceMemory(),
        persistent_memory=PersistentMemory(memory_dir=tmp_path),
        prompt_profile=profile,
    )


def test_tactical_position_question_does_not_enable_valuation_frameworks() -> None:
    route = classify_conversation_route("中天今天涨6%，我34.2卖了200股，周一怎么做T回来？")

    assert route.intent == "tactical_position"
    assert route.requires_fresh_data is True
    assert "get_market_data" in route.tool_names
    assert "financial_rigor" not in route.tool_names
    assert "load_skill" not in route.tool_names
    assert "run_swarm" not in route.tool_names


def test_long_term_and_valuation_questions_take_different_routes() -> None:
    long_term = classify_conversation_route("中天现在值不值得长期持有？")
    valuation = classify_conversation_route("中天现在合理估值是多少钱？")

    assert long_term.intent == "company_research"
    assert valuation.intent == "valuation"
    assert "financial_rigor" not in long_term.tool_names
    assert "financial_rigor" in valuation.tool_names


def test_channel_prompt_is_compact_and_makes_freshness_a_hard_gate(tmp_path: Path) -> None:
    prompt = _builder(tmp_path).build_system_prompt("这只股票今天盘中涨了，我该怎么看？")

    assert len(prompt) < 6_000
    assert "requires fresh data" in prompt
    assert "historical context only" in prompt
    assert "Do not start Market Snapshot" in prompt
    assert "29 multi-agent swarm teams" not in prompt


def test_general_channel_message_does_not_receive_project_memory(tmp_path: Path) -> None:
    memory = PersistentMemory(memory_dir=tmp_path)
    memory.add("用户投资偏好", "用户偏好长期投资、芒格框架和安全边际", "user")
    builder = ContextBuilder(
        ToolRegistry(),
        WorkspaceMemory(),
        persistent_memory=memory,
        prompt_profile="channel",
    )

    messages = builder.build_messages("你好")

    assert messages[-1]["content"] == "你好"
    assert "芒格" not in messages[0]["content"]


def test_recalled_research_memory_is_explicitly_historical(tmp_path: Path) -> None:
    memory = PersistentMemory(memory_dir=tmp_path)
    memory.add("中天科技估值", "截至旧日期的中天科技估值记录", "project")
    builder = ContextBuilder(
        ToolRegistry(),
        WorkspaceMemory(),
        persistent_memory=memory,
        prompt_profile="channel",
    )

    messages = builder.build_messages("分析中天科技的长期投资价值")

    assert "historical-context-only" in messages[-1]["content"]
    assert "Verify every time-sensitive fact" in messages[-1]["content"]


def test_registry_whitelist_keeps_only_requested_available_tools() -> None:
    registry = build_registry(allowed_tool_names=["compact", "load_skill"])

    assert set(registry.tool_names) == {"compact", "load_skill"}
