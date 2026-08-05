# Phase 2 Gap Analysis — Panic Value Hunter MVP

Date: 2026-08-05
Status: DRAFT (M0 deliverable)

## 1. Objective

First usable Panic Value Hunter: user opens `http://127.0.0.1:8899/investment-research`,
selects a historical panic day (e.g. 2025-04-07) and gets:

- Market state (index observations, panic level)
- Candidate list with entry reasons and risk factors
- T+5 / T+20 / T+60 outcomes

Acceptance: the 2025-04-07 historical run must produce real candidates from
real historical data (proof that the research loop closes without data gaps).

## 2. Constraints

- No new architecture: reuse Provider Layer / Market Snapshot / Research
  Candidate / Historical Evaluation / Notification Outbox.
- No second research system, database, or trading logic.
- No auto-trading, no buy/sell advice. Output is capped at
  Research Candidate + Action Level + Daily Intelligence.
- No future-data leakage: every historical computation must be point-in-time
  (only data up to the selected date).

## 3. Architecture inventory (M0 findings)

| Layer | Module | Status |
|---|---|---|
| Provider abstraction | `agent/src/value_hunter/providers.py` (947 lines) | OK — `ValueHunterProvider` ABC, `DemoProvider`, `AkshareProvider`, `build_provider`, `RESEARCH_MARKET_DATA_FALLBACK_CHAIN` |
| Domain models | `agent/src/value_hunter/models.py` | OK — `IndexObservation`, `MarketObservation`, `CandidateObservation`, `ScoreBreakdown`, `CandidateResult`, `MarketResult`, `ScanResult` |
| Scoring | `agent/src/value_hunter/scoring.py` | OK — `score_market`, `score_candidate` |
| Scan orchestration | `agent/src/value_hunter/service.py` | OK — `ValueHunterService.run` |
| Market data fetch | `agent/src/market_data.py` | OK — `fetch_market_data` with loader registry + fallback chains |
| Loader registry | `agent/backtest/loaders/registry.py` | OK — 23 sources, `FALLBACK_CHAINS` |
| Tushare loader | `agent/backtest/loaders/tushare.py` | OK — includes `_is_entitlement_error` |
| Research app | `agent/src/investment_research/application/research_mvp.py` | GAP — `build_historical_evaluation` reads **stored scan snapshots only**; no historical fetch path |
| Exec plan | `docs/exec-plans/research-mvp-v1.md` | OK — already documents M0–M15, M11 notes historical Data Gap |

## 4. Data Gap Analysis

### 4.1 The blocker

`build_historical_evaluation(as_of_date)` today only works if a scan snapshot
was stored for that date by a live run. 2025-04-07 has **no stored snapshot**,
so the historical report cannot be produced.

Fix direction: add a point-in-time reconstruction path that rebuilds
`MarketObservation` + candidate universe from historical market data for the
requested date, with no future leakage.

### 4.2 Data source availability (verified 2026-08-05)

| Source | Endpoint | Auth | Result |
|---|---|---|---|
| Tushare `daily` / `index_daily` / `trade_cal` / `stock_basic` | api.tushare.pro | token in `.env.market-data.local` + `agent/.env` | **FAILED** — "没有接口(daily)访问权限" (token has no entitlements, consistent with M2 handoff note) |
| AKShare 新浪指数历史 | `stock_zh_index_daily` (finance.sina.com.cn) | none | **OK** — 2025-04 has 21 rows for sh000300 |
| AKShare 腾讯指数历史 | `stock_zh_index_daily_tx` | none | **OK** — 2025-04 has 22 rows |
| AKShare 东财 (requests) | push2his.eastmoney.com | none | **UNSTABLE** — `RemoteDisconnected` via requests on this machine (urllib works; root cause likely local TLS/connection issue) |
| AKShare 新浪个股历史 | `stock_zh_a_daily` | none | not yet tested (next) |

### 4.3 Consequences

1. **Tushare is not usable** for this MVP. The existing Tushare loader stays
   untouched (it is not the blocker), but the historical provider must use
   AKShare.
2. **Eastmoney via requests is unreliable** on this machine. The historical
   provider should prefer Sina / Tencent, and mark Eastmoney-derived fields as
   degraded if it is the only option for some field (e.g. limit-up/down counts).
3. A-shares individual stock history via Sina/Tencent must be verified next;
   if it works, the full point-in-time rebuild is feasible.

### 4.4 Candidate data requirements vs. sources

| Field used by scoring | Historical source plan |
|---|---|
| Index close / daily return / drawdown / below MA250 / below 120d low | Sina index history (sh000001, sz399001, sz399006, sz399005) |
| Advancer / decliner ratio | Rebuild from universe daily bars (need stock history) |
| Above-MA60 ratio | Rebuild from universe daily bars |
| Limit-up / limit-down counts | Eastmoney `stock_zh_a_pankou` or Tencent (verify); else mark `None` with warning |
| Turnover z-score | Sina/Tencent volume history; warn if unavailable |
| Stock close / returns / 20d/60d returns / volume ratio | Stock daily history (Sina/Tencent) |
| PE / PB / fundamentals | **not available historically** → must remain `None` with explicit `missing_fields` / warnings |

## 5. Milestone plan (M0–M8)

- M0 ✅ (this doc): status review, provider inventory, gap analysis, git status.
- M1: Historical data provider (AKShare Sina/Tencent) in Provider Layer;
  point-in-time fetch for indices + universe with no future leakage.
- M2: Rebuild `MarketObservation` for a historical date (indices, breadth,
  panic inputs); fall back gracefully when a field is unavailable.
- M3: Rebuild candidate universe at the historical date (closes, returns,
  volume, drawdown); run existing `score_candidate` unchanged.
- M4: Wire `build_historical_evaluation` to the new reconstruction path
  (fallback to stored snapshot if present, else rebuild).
- M5: 2025-04-07 end-to-end run: market state + panic level + candidates +
  entry reasons + risk factors + T+5/T+20/T+60 outcomes.
- M6: Regression: existing live scan + stored-snapshot evaluation still pass.
- M7: UI confirmation at `/investment-research` (historical date picker works).
- M8: Acceptance: 2025-04-07 produces real candidates; commit handoff.

## 6. Open questions

1. Does Sina/Tencent provide individual A-share daily history (needed for
   breadth and candidate rebuild)? — to verify in M1.
2. Limit-up/down counts historically: which endpoint, and is it reliable
   enough? If not, acceptable to emit `None` + warning (scoring already
   tolerates missing fields).
3. `VALUE_HUNTER_PROVIDER` env value: confirm it points to `akshare`
   (default) so the historical provider is used automatically.
