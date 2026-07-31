"""Tests for RC8 bounded feedback workflow aggregation logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch


class TestBoundedFeedbackAggregation:
    def test_market_state_distribution(self) -> None:
        from src.scripts.bounded_feedback_workflow import _market_state_distribution

        mock_scan = MagicMock()
        mock_scan.panic.panic_observation.value = "normal"
        mock_replay = MagicMock()
        mock_replay.daily_scans = [mock_scan, mock_scan]
        result = _market_state_distribution(mock_replay)
        assert result["total_days"] == 2
        assert result["regime_counts"].get("normal") == 2

    def test_candidate_counts(self) -> None:
        from src.scripts.bounded_feedback_workflow import _candidate_counts

        mock_scan = MagicMock()
        mock_scan.data_date = date(2026, 7, 24)
        mock_scan.watchlist = [1, 2, 3]
        mock_replay = MagicMock()
        mock_replay.daily_scans = [mock_scan]
        result = _candidate_counts(mock_replay)
        assert len(result) == 1
        assert result[0]["candidate_count"] == 3

    def test_evidence_completeness(self) -> None:
        from src.scripts.bounded_feedback_workflow import _evidence_completeness

        mock_scan = MagicMock()
        mock_scan.financial_provenance = {"category": "available"}
        mock_scan.event_provenance = None
        mock_replay = MagicMock()
        mock_replay.daily_scans = [mock_scan]
        result = _evidence_completeness(mock_replay)
        assert result["total_days"] == 1
        assert result["financial_data_days"] == 1
        assert result["event_data_days"] == 0

    def test_outcome_availability(self) -> None:
        from src.scripts.bounded_feedback_workflow import _outcome_availability

        mock_outcome = MagicMock()
        mock_outcome.outcome_5d = 0.05
        mock_outcome.outcome_20d = None
        mock_cal = MagicMock()
        mock_cal.outcomes = [mock_outcome]
        result = _outcome_availability(mock_cal)
        assert result["total_outcomes"] == 1
        assert result["5d_available"] == 1
        assert result["20d_available"] == 0

    def test_review_rows_empty(self) -> None:
        from src.scripts.bounded_feedback_workflow import _review_rows

        mock_cal = MagicMock()
        mock_cal.outcomes = []
        result = _review_rows(mock_cal)
        assert result == []

    def test_provenance_limitations_with_data(self) -> None:
        from src.scripts.bounded_feedback_workflow import _provenance_limitations

        mock_replay = MagicMock()
        mock_replay.daily_scans = [MagicMock()]
        result = _provenance_limitations(mock_replay)
        assert len(result) > 0

    def test_provenance_limitations_no_data(self) -> None:
        from src.scripts.bounded_feedback_workflow import _provenance_limitations

        mock_replay = MagicMock()
        mock_replay.daily_scans = []
        result = _provenance_limitations(mock_replay)
        assert any("no historical" in r for r in result)
