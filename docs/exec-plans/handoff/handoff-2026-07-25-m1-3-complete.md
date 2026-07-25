# M1.3 Historical Evaluation — Handoff

**Date:** 2026-07-25
**Branch:** `feat/historical-evaluation-m1-3`
**Base:** `ef45594` (M1.2, fix/trial-release-m1)
**HEAD:** `c1274fe`

## Summary

All 13 milestones (M0-M12) of the Historical Evaluation M1.3 task are complete. 117 tests pass across all modules.

## New Modules

### Models
- `src/investment_research/models/historical_market_panel.py` — `HistoricalMarketPanel` dataclass (date, price, MA5/10/20, volume, turnover, amplitude)

### Operations
- `market_loader.py` — `HistoricalMarketLoader` base + `FixtureHistoricalMarketLoader` for date-safe market data loading
- `historical_shadow_run.py` — `HistoricalShadowRunner` with `run_for_date` / `run_for_dates` API
- `outcome_loader.py` — `WindowOutcome`, `HistoricalEvaluationOutcome`, `FixtureOutcomeLoader` for T+5/T+20/T+60 outcome data
- `evaluation_metrics.py` — `MetricsCalculator` producing hit rate, FP/FN rate, avg excess return, avg max drawdown
- `review_labeling.py` — `ReviewLabel` enum (correct_call, false_positive, false_negative, unclear) + labeling utilities
- `etf_support.py` — `ETFOutcomeLoader`, `compute_tracking_error`, `etf_review_labels`
- `trading_calendar.py` — `TradingCalendar` for forward/backward trading day resolution, nth-day lookups
- `panic_episode_review.py` — `PanicEpisodeReviewWorkflow` for episode-level aggregate evaluation

### API
- `src/api/historical_evaluation_routes.py` — FastAPI router with `/status` and `/evaluate/{trade_date}` endpoints

### Tests (14 new test modules)
- `test_historical_market_panel.py`, `test_market_loader.py`, `test_historical_shadow_run.py`, `test_outcome_loader.py`, `test_evaluation_metrics.py`, `test_review_labeling.py`, `test_etf_support.py`, `test_historical_evaluation_routes.py`, `test_trading_calendar.py`, `test_panic_episode_review.py`, `test_m12_comprehensive_validation.py`

## Current State
- All 117 tests in the M1.3 regression group pass
- Ledger committed to `docs/exec-plans/active/historical-evaluation-m1-3.md`
- Verify script at `scripts/verify_market_shadow.ps1` enhanced with Git/runtime/date feature checks

## Known Gaps (unaffected by M1.3)
1. SZSE Provider: blocked_by_api_documentation
2. Tushare: permission_denied
3. No frontend tooling (npm/node)
4. Docker verification deferred
5. AGENTS.md missing at root

## Soft Blockers (bypassed)
- None encountered during M1.3 execution
