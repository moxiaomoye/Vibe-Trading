# M1.3 Validation — Ledger

## Baseline
- **Branch:** `fix/m1-3-validation`
- **HEAD:** `c2c5876` (V3 no-lookahead audit)
- **M1.2 Base:** `ef45594`

## Milestone Ledger

| ID | Status | Commit | Tests | Runtime | Findings | Blocker |
|----|--------|--------|-------|---------|----------|---------|
| V0 | done | a6e618a | 117/117 | 5.51s | 14 milestones, 24 new files (11 src + 11 test + 2 docs), no TODO/FIXME, NotImplementedError=expected abstract base pattern, no financial threshold modifications, clean | None |
| V1 | done | — | 121 pass / 12 pre-existing fail / 87 pre-existing collection errors | 4.36s | 52 pre-M1.3 + 69 M1.3 tests pass; 12 test_cli_interactive.py pre-existing; 87 collection errors = missing deps (python-multipart, fastmcp, jinja2, scipy, defusedxml, aiohttp, yfinance) — all pre-existing, not M1.3 | None |
| V2 | done | — | Frontend: 38/38 test files, 322/322 tests pass, tsc OK, build OK | 17.00s | InvestmentResearch page has historical date/manual import/shadow report/outcome features. Build succeeded. | None |
| V3 | done | c2c5876 | 194 M1.3 tests pass; 4 new audit tests; 3 low-risk fixes | 4.71s | Fixed: (1) validator uses Shanghai date not UTC for future check, (2) conflicting_versions report bug, (3) manual import 18:30 cutoff. Tests added for timezone boundary, cutoff, fingerprint immutability, clock skew. | None |
| R1 | done | 5536196 | 42/42 (validator + existing) | 1.10s | Fix: naive tz TypeError crash, CONFLICTING_VERSION row marking. 7 new robustness tests. | None |
| R2 | done | 848e67c | 204 pass | 12.94s | Wire historical_evaluation_routes into real api_server via app.include_router. Integration test with source-code AST assertion + router-direct test. Note: endpoint uses FixtureOutcomeLoader({}) — contract-only. | None |
| R3 | done | 7fa371c | ledger update | — | Capability matrix: real (stock prices, CSI300, frontend), manual (upload), fixture/contract-only (market panel, outcomes, ETF, max drawdown), unverified (Docker). Key finding: FixtureOutcomeLoader({}) hardcoded in production route. | None |
| R4 | active | — | — | — | Defining outcome formulas, implementing PriceSeriesOutcomeLoader | None |
| V5 | pending | — | — | — | — | — |
| V6 | pending | — | — | — | — | — |
| V7 | pending | — | — | — | — | — |
| V8 | pending | — | — | — | — | — |
| V9 | pending | — | — | — | — | — |
| V10 | pending | — | — | — | — | — |
| V11 | pending | — | — | — | — | — |
| V12 | pending | — | — | — | — | — |

## R4 — Outcome Formula Definitions

These definitions are fixed in the ledger before any implementation change.

| Field | Definition |
|-------|-----------|
| **Entry Price** | Close price of the evaluated stock on trading day T (evaluation_date). Uses **前复权** (forward-adjusted) price from `akshare.stock_zh_a_hist(adjust="qfq")`. |
| **T+n horizon** | **A-share trading days** (not calendar days). T+5 = 5th trading day after T. Resolved via `TradingCalendar.nth_trading_day_forward(T, n)`. |
| **Price adjustment** | **前复权 (forward-adjusted)** — all historical prices are adjusted backward so that the series reflects total return including dividends and corporate actions. This is the standard for A-share performance measurement. |
| **Asset return (T+n)** | `(close_T+n / close_T) - 1` where `close_T+n` is the forward-adjusted close on the n-th trading day after T. |
| **Benchmark return (T+n)** | `csi300_T+n / csi300_T - 1` where `csi300_T` is the CSI 300 index close on day T, and `csi300_T+n` is the CSI 300 close on the n-th trading day after T. CSI 300 dates are strictly aligned to the same A-share trading days as the asset. |
| **Excess return (T+n)** | `asset_return_T+n - benchmark_return_T+n` |
| **Maximum drawdown (T to T+n)** | `min((price_t / peak_to_t) - 1 for t in [T+1, ..., T+n])` where peak_to_t = `max(price_T, ..., price_t)`. Calculated using daily forward-adjusted close prices. |
| **Suspension / missing price** | If `close_T+n` is NaN or zero for any reason (suspension, delisting, trading halt), the window is marked `data_gap="price_data_missing"`. Asset return, excess return, and max drawdown are None. Benchmark return is still computed if available. |
| **Delisting before horizon** | If the stock is delisted before T+n, all subsequent windows return `data_gap="delisted"`. The last available price is used for partial windows up to the delisting date. |
| **Not-yet-matured window** | If T+n > current trading day, the window returns `data_gap="not_yet_matured"` with all returns as None. |
| **CSI 300 date alignment** | CSI 300 index values are fetched for the exact same trading days as the asset. If CSI 300 has a gap on a trading day, the previous available value is carried forward. |
| **Entry price for panic scenario** | If the evaluation is for a panic shadow report, the entry price is the **trigger day's close** (the day the panic signal fired), not the evaluation_date's close. |

## Data Source Capability Matrix (R3)

| # | Component | Capability | Detail | File |
|---|-----------|-----------|--------|------|
| 1 | Historical market panel | **contract-only** | `HistoricalMarketLoader._fetch_panel_data()` raises NotImplementedError. `FixtureHistoricalMarketLoader` reads in-memory dict only. Parallel live path (`ComponentFallbackPostCloseProvider`) is real but uses current-date-only akshare API. | `market_loader.py` |
| 2 | Individual stock prices | **real** (API) / **manual** (upload) | `AksharePostCloseProvider` → East Money HTTP API / `SinaSpotAdapter`. Manual import via `parse_manual_import_json`. Runtime API currently unavailable in sandbox. | `post_close_provider.py`, `manual_import.py` |
| 3 | CSI 300 benchmark | **real** (API) / **manual** (upload) | `akshare.stock_zh_index_daily_em("sh000300")` / Sina fallback. Manual `benchmark` field. Runtime API currently unavailable. | `post_close_provider.py` |
| 4 | T+5/T+20/T+60 forward outcomes | **contract-only** | `FixtureOutcomeLoader({})` hardcoded in route — always returns `data_gap="not_yet_tracked"`. No forward-price-fetching code exists anywhere. | `outcome_loader.py`, `historical_evaluation_routes.py:44` |
| 5 | Maximum drawdown | **contract-only** | Passes through from `WindowOutcome.maximum_drawdown` which is always None from fixture. No price-series calculation. | `evaluation_metrics.py` |
| 6 | ETF outcomes | **fixture** | `ETFOutcomeLoader` mirrors `FixtureOutcomeLoader` pattern. `compute_tracking_error()` is pure function with no data source. | `etf_support.py` |
| 7 | Historical date frontend | **real** (HTTP) | Fetches live from backend API routes. `/evaluate` endpoint returns contract-only outcomes. | `InvestmentResearch.tsx` |
| 8 | Docker/HTTP | **unverified** | Dockerfile exists but end-to-end container test not run. | `Dockerfile` |

**Key architectural finding:** Two parallel market-data abstractions coexist. `HistoricalMarketLoader` (for the history-replay path used by M1.3 shadow runner) has NO real implementation. The real akshare-based providers only work for current-date spot data.

## Known Gaps (carried forward from M1.3)
1. SZSE Provider: blocked_by_api_documentation
2. Tushare: permission_denied
3. No frontend tooling (npm/node)
4. Docker verification deferred
5. AGENTS.md missing at root
