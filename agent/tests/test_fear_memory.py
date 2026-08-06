"""Phase 5 Fear Memory System tests - Historical Crisis Library (PIT-safe)."""

from __future__ import annotations

from datetime import date

from src.investment_research.models.fear_memory import (
    FEAR_MEMORY_VERSION,
    CrisisSeverity,
    FearMemoryConfig,
    query_fear_memory,
)


class TestPointInTimeVisibility:
    def test_future_episodes_are_hidden_not_leaked(self) -> None:
        memory = query_fear_memory(date(2017, 1, 2))
        assert memory.hidden_episodes_count == 3
        ids = {episode.crisis_id for episode in memory.visible_episodes}
        assert ids == {"2015-leverage-crash", "2016-circuit-breaker"}
        for episode in memory.visible_episodes:
            assert episode.start_date <= date(2017, 1, 2)
        assert "隐藏" in memory.summary[0]

    def test_2018_episode_visible_after_start(self) -> None:
        memory = query_fear_memory(date(2018, 6, 1))
        ids = {episode.crisis_id for episode in memory.visible_episodes}
        assert "2018-deleveraging" in ids
        assert "2020-covid-shock" not in ids

    def test_all_episodes_visible_late_enough(self) -> None:
        memory = query_fear_memory(date(2025, 1, 1))
        assert memory.hidden_episodes_count == 0
        assert len(memory.visible_episodes) == 5

    def test_episode_starting_on_as_of_is_visible(self) -> None:
        memory = query_fear_memory(date(2024, 1, 29))
        ids = {episode.crisis_id for episode in memory.visible_episodes}
        assert "2024-microcap-liquidity" in ids

    def test_2024_crisis_hidden_on_eve(self) -> None:
        memory = query_fear_memory(date(2024, 1, 28))
        ids = {episode.crisis_id for episode in memory.visible_episodes}
        assert "2024-microcap-liquidity" not in ids
        assert memory.hidden_episodes_count == 1


class TestCuratedLibrary:
    def test_episodes_are_facts_not_predictions(self) -> None:
        config = FearMemoryConfig.curated()
        for episode in config.episodes:
            assert episode.start_date < episode.end_date
            assert episode.label
            assert episode.narrative
            assert episode.sources
            assert "预测" not in episode.narrative
            assert "未来" not in episode.narrative

    def test_episode_ids_are_unique(self) -> None:
        config = FearMemoryConfig.curated()
        ids = [episode.crisis_id for episode in config.episodes]
        assert len(ids) == len(set(ids))

    def test_severity_is_typed(self) -> None:
        config = FearMemoryConfig.curated()
        assert all(
            episode.severity in CrisisSeverity for episode in config.episodes
        )


class TestContractShape:
    def test_deterministic_for_same_date(self) -> None:
        assert query_fear_memory(date(2019, 5, 1)).model_dump() == query_fear_memory(
            date(2019, 5, 1)
        ).model_dump()

    def test_version_is_frozen(self) -> None:
        assert FearMemoryConfig().version == FEAR_MEMORY_VERSION
        assert query_fear_memory(date(2017, 1, 2)).version == FEAR_MEMORY_VERSION

    def test_never_emits_trading_directives(self) -> None:
        serialized = query_fear_memory(date(2025, 1, 1)).model_dump()
        for key in ("action", "signal", "recommendation", "order", "buy", "sell", "rating"):
            assert key not in serialized

    def test_summary_names_latest_visible_episode(self) -> None:
        memory = query_fear_memory(date(2024, 3, 1))
        assert "微盘股" in memory.summary[1]

    def test_episodes_are_pit_filtered_even_when_queried_late(self) -> None:
        memory = query_fear_memory(date(2016, 2, 1))
        assert len(memory.visible_episodes) == 2
        assert memory.hidden_episodes_count == 3
