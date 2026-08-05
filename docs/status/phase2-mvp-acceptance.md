# Phase 2 MVP Acceptance — Panic Value Hunter (M8)

Date: 2026-08-05
Status: DONE (M8 deliverable, follows `docs/status/phase2-gap-analysis.md` M0)

## 1. Acceptance criteria

From M0 doc §1: user opens `http://127.0.0.1:8899/investment-research`, selects
2025-04-07, and gets market state + candidates + T+5/T+20/T+60 outcomes built
from real historical data with **no future leakage**.

**Result: PASS.** The historical run rebuilds a point-in-time snapshot when none
is stored, persists it, and computes forward outcomes from real subsequent bars.

## 2. What was built (M1–M7)

### M1–M3 — `HistoricalAkshareProvider` (`agent/src/value_hunter/providers.py`)

- `load_market(through=date)` parameterized; historical branch:
  - indices via `stock_zh_index_daily` (Sina) with `stock_zh_index_daily_tx`
    (Tencent) fallback;
  - universe via `build_provider` loader registry fallback chain (`stock_zh_a_daily`
    Sina qfq → Tencent `stock_zh_a_daily_tx` → ...), never touching live spot
    endpoints;
  - breadth (advancer ratio / above-MA60 ratio) rebuilt from universe daily bars,
    explicitly labelled 基于研究标的池 (not full-market) in `warnings`;
  - limit-down count and turnover z-score not available historically → `None`
    with explicit Data Gap warning.
- `_enrich_point_in_time_financials` (Sina `stock_financial_analysis_indicator`
  rows filtered to `date <= through`; annual ROE median from years `< through.year`).
- `_enrich_point_in_time_valuation` (Eastmoney `stock_value_em` historical rows
  filtered to `as_of`; PE-history percentile from the distribution as of the date).
- `HistoricalAkshareProvider(as_of, ...)` + `build_provider(..., as_of=...)`
  (name `"akshare-historical"`); live path untouched (existing tests unchanged).

### M4–M5 — Rebuild path (`agent/src/investment_research/application/research_mvp.py`)

- `build_historical_evaluation` looks up the stored snapshot; if missing →
  `_rebuild_historical_evaluation`: build provider, `_scan_historical_provider`
  (runs existing `score_market` / `score_candidate`, deterministic uuid5 run_id,
  saves snapshot with `mode="akshare-historical"`), fetch T+ prices via
  `fetch_market_data` (`source="auto"`), build candidates payload with
  selection reasons / risks / data gaps.
- Fixed: `panic_sensitivity` now read from scan context (`trigger_count` real),
  so 2025-04-07 correctly classifies **PANIC** (2/2 triggers).
- Fixed: bare 6-digit watchlist symbols normalized via `normalize_ashare_symbol`
  before T+ fetches (both stored and rebuild paths).

### M6 — Regression

- Route test updated: missing snapshot now asserts **rebuild + persist** behavior
  (stub provider, no network).
- Full relevant suite: **119 passed** (value_hunter service/scoring/providers/
  routes, research_mvp routes, panic config, market_data, registry).

### M7 — UI

- `/investment-research` already ships the date picker (default 2025-04-07) and
  historical panel (market state, panic sensitivity, T+ table).
- Text updated: rebuild semantics now explained ("缺失时从公开时点数据重建（不含
  未来信息）并自动保存").
- `npm run build` (tsc + vite) passes.

## 3. End-to-end evidence (2025-04-07)

- Market score 68.6; all four tracked indices below MA250; breadth 0/14
  advancers; ChiNext −12.5%, CSI1000 −11.4% on the day.
- 14 watchlist candidates rebuilt with ROE / drawdown / growth populated;
  T+5/T+20/T+60 returns and excess vs 000300.SH computed from real bars
  (e.g. 601991.SH fetched 69 rows through 2025-07-16).
- First call: rebuild path (≈1–2 min, network bound). Second call: stored
  snapshot path, `rebuilt=None`, ≈16 s.

## 4. Known limitations

1. Historical breadth is universe-based, not full-market (labelled in warnings).
2. Limit-up/down count and turnover z-score remain Data Gap historically.
3. Eastmoney endpoints unreliable via `requests` on this machine (M0 finding) —
   Sina/Tencent are the reliable routes; valuation enricher has its own
   urllib-based retry.
4. Rebuild is slow on first request (full fetch + per-candidate enrichment).

## 5. Run it

```
backend:  python -m agent.src.api.server (or uvicorn, port 8899)
UI:       http://127.0.0.1:8899/investment-research → 历史验证 → 2025-04-07 → 查看历史验证
tests:    .venv\Scripts\python.exe -m pytest agent/tests/test_value_hunter_service.py
          agent/tests/test_value_hunter_scoring.py agent/tests/test_value_hunter_provider_cache.py
          agent/tests/test_value_hunter_routes.py agent/tests/test_research_mvp_routes.py
          agent/tests/test_panic_value_config.py agent/tests/test_market_data.py agent/tests/test_registry.py
```

## 6. Handoff notes

- Commits pending: M1–M4 backend + M6 test + M7 UI text + this doc (one or more
  DCO commits; blocked until the GPG key is unlocked, `commit.gpgsign=true`).
- Tushare token has no entitlements (M0 finding) — unchanged, not a blocker.
