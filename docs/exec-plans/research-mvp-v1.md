# Vibe-Trading Research MVP V1 Execution Plan

## Product boundary

Deliver one investor-usable research loop at `/investment-research`: generate a
point-in-time after-market report, inspect up to five research candidates, review
two-sided evidence and data gaps, and replay historical results. The product
produces research plans only. It does not produce buy/sell instructions,
position advice, automated trading, scheduled sends, or automatic Feishu sends.

## M0 capability inventory

### Existing capabilities and locations

| Capability | Existing implementation | Reuse decision |
| --- | --- | --- |
| Market snapshot and breadth | `agent/src/value_hunter/providers.py` (`AkshareProvider.load_market`) and `agent/src/value_hunter/models.py` | Reuse the provider observation; do not rescan the market in Research MVP. |
| Panic classification | `agent/src/value_hunter/scoring.py` (`score_market`) plus `agent/src/investment_research/market/assessment.py` | Reuse the deterministic Value Hunter score and map its existing level into the four UI states. Preserve reasons and missing coverage as Data Gap. |
| Watchlist loading | `agent/src/value_hunter/providers.py` (`load_watchlist_csv`, `_base_watchlist`) and `value_hunter_watchlist.example.csv` | Reuse configured/default watchlist loading. Do not create another watchlist store. |
| Candidate observations and scoring | `agent/src/value_hunter/models.py`, `agent/src/value_hunter/scoring.py`, `agent/src/value_hunter/service.py` | Reuse observations, score breakdown, reasons, first rejection, risk flags, and missing fields; limit the Research MVP response to Top 5. |
| Relative strength | `CandidateObservation.relative_to_sector_pct` and the existing price-history enrichment in `agent/src/value_hunter/providers.py` | Reuse the existing sector-relative field. Add benchmark-relative presentation only from point-in-time price data; missing values remain Data Gap. |
| Research Candidate domain | `agent/src/investment_research/candidates/models.py`, daily research models/renderers, discovery triage | Reuse the evidence-first language and candidate boundary. Screen output remains a research candidate, never a recommendation. |
| Evidence framework | `agent/src/investment_research/evidence/`, readiness service, evidence routes and repositories | Reuse supporting/counter evidence contracts and surface missing evidence explicitly. No database change. |
| Historical evaluation | `agent/src/investment_research/validation/models.py`, `quality.py`, `sqlite_validation.py` | Reuse point-in-time rules and outcome vocabulary. Add a read-only market-data adapter for requested-date T+5/T+20/T+60 display; no new database. |
| Daily research API | `agent/src/api/investment_research_routes.py` and `application/daily_pipeline.py` | Add one POST orchestration endpoint inside the existing route/module boundary. Keep existing read-only routes compatible. |
| Investment Research frontend | `frontend/src/pages/InvestmentResearch.tsx`, `frontend/src/lib/api.ts`, router entry | Extend the existing page and API client; no second frontend or dashboard shell. |
| Notification outbox / Feishu | `agent/src/investment_research/operations/`, `agent/src/channels/feishu.py`, existing channel runtime | Reuse preview/delivery boundaries. Default `send=false`; no scheduler and no automatic send. |
| Docker runtime | `Dockerfile`, `docker-compose.yml`, built frontend served on `127.0.0.1:8899` | Rebuild and validate the existing service only. |

### Current working-tree finding

At M0 start, `main` at `b9e85ea` already contained uncommitted Research UI/API
work plus local environment/log files. Those changes are treated as user-owned.
They will be reviewed and either incorporated through targeted edits or left
unstaged. Sensitive `.env*` files and logs must never be committed.

The uncommitted `trial-daily-watchlist` implementation is not the requested MVP
contract: it duplicates a fixed watchlist, contains mojibake, includes
action/entry-zone language outside the product boundary, and does not expose the
required POST route, Top 5 contract, detail view, or historical replay. It is not
accepted as an M0 capability.

## Missing capabilities

1. `POST /investment-research/research-run` with the required response contract.
2. A thin orchestration service that calls existing Value Hunter provider and
   scoring functions exactly once per run and translates their output without
   fabricating missing fields.
3. Point-in-time trade-date resolution to the latest complete trading session.
4. Top 5 candidate UI backed by the POST endpoint.
5. Candidate detail UI with quality, financials, valuation, support, counter
   evidence, risks, Data Gap, and observation/risk/validation Research Plan.
6. Requested-date replay with market state, contemporaneous candidates, and
   T+5/T+20/T+60 returns using only data available for each calculation.
7. Feishu preview plus explicit confirmation path with `send=false` and
   `scheduler=false` defaults.
8. Docker, real-data, and browser acceptance evidence at port 8899.

## Milestones

### M0 - Capability inventory

- Status: complete.
- Evidence: repository map and reuse decisions above.
- Code changes: none.
- Verification: branch/status/tree/diff inspection completed.

### M1 - Unified research entry

- Status: complete.
- Add or complete `POST /investment-research/research-run`.
- Return `trade_date`, `market_state`, `market_summary`, `candidates`, and
  `data_gaps`.
- Reuse Value Hunter market/provider/scoring and Investment Research contracts.
- Add targeted backend tests, run diff check, commit, update this handoff.

### M2 - Candidate board

- Status: complete.
- Wire the existing page to the real POST API.
- Display Top 5 candidate identity, price, drawdown, benchmark/sector relative
  performance, selection reason, risk, and Data Gap.
- Add frontend tests, build, diff check, commit, update handoff.

### M3 - Candidate detail and Research Plan

- Status: complete.
- Add a candidate detail interaction on the existing page.
- Show quality, financials, valuation, support/counter evidence, risks, gaps,
  and the three-part Research Plan.
- Test, inspect diff, commit, update handoff.

### M4 - Historical validation connection

- Status: complete.
- Accept a requested date and reconstruct that point-in-time research run.
- Display T+5/T+20/T+60 performance without future leakage or current-price
  substitution.
- Test known dates and unavailable horizons, inspect diff, commit, update handoff.

### M5 - Feishu preview

- Status: complete.
- Generate a preview from the research result.
- Require explicit user confirmation before any send path.
- Keep `send=false` and `scheduler=false` by default; do not send during tests.
- Test, inspect diff, commit, update handoff.

### M6 - Real runtime acceptance

- Status: complete for personal testing.
- Build and run the existing Docker service.
- Verify `/live`, the page, the generation click, real-data provenance,
  candidates/detail, and historical validation in a browser.
- Record exact acceptance evidence and remaining Data Gaps here.

## Milestone handoff log

### M0 handoff

- Branch/HEAD: `main` / `b9e85ea` before the M0 documentation commit.
- Result: reuse map established; no production code modified.
- Main implementation direction: Value Hunter owns scanning and screen inputs;
  Investment Research owns the unified contract and research presentation.
- Risks: upstream provider fields can be unavailable; every such absence must be
  returned as Data Gap. Existing uncommitted trial code requires careful
  reconciliation and remains unstaged until reviewed.
- Next: M1 unified POST endpoint and targeted backend contract tests.

### M1 handoff

- Result: added the unified POST route through a thin Investment Research
  adapter over `ValueHunterService.run(notify=False)`; no market scanner was
  duplicated and no notification was sent.
- Contract: trade date, four-state market classification, breadth summary,
  Top 5 maximum candidates, and explicit top-level/candidate Data Gaps.
- Provider reuse improvement: existing observations now retain breadth counts
  and candidate current price already present in the provider response.
- Tests: 17 targeted Research MVP and Value Hunter tests passed; Python compile
  and `git diff --check` passed.
- Safety: no scheduler, Feishu send, order path, dependency, or database change.
- Next: M2 replace the incomplete trial UI contract with the real POST response.

### M2 handoff

- Result: the existing `/investment-research` page now waits for the explicit
  “生成盘后研究” action, calls `POST /investment-research/research-run`, and
  renders the returned market summary and Top 5 maximum candidate board.
- Candidate display: name, code, current price, drawdown, benchmark-relative
  Data Gap, sector performance, selection reasons, first rejection, risks, and
  candidate Data Gaps.
- Tests: focused Vitest passed; TypeScript and production Vite build passed;
  `git diff --check` passed. Existing chunk-size warnings are unchanged.
- Boundary: zero candidates is displayed honestly; there is no mock fallback,
  order action, position advice, scheduler, or notification send.
- Next: M3 candidate detail interaction and three-part Research Plan.

### M3 handoff

- Result: each candidate now opens an inline detail view on the same page.
- Detail contract: company quality, financials, valuation, supporting evidence,
  counter evidence, potential risks, candidate Data Gap, and a three-part
  Research Plan covering observation, error/risk, and future validation.
- Tests: backend contract test and frontend interaction test passed; Python
  compile, production frontend build, and `git diff --check` passed.
- Boundary: Research Plan contains verification conditions only and introduces
  no transaction, position, scheduler, or notification behavior.
- Next: M4 requested-date point-in-time replay and T+5/T+20/T+60 outcomes.

### M4 handoff

- Result: added requested-date historical evaluation backed only by stored
  Value Hunter point-in-time snapshots and the existing historical market-data
  loader.
- Outcome logic: T+5/T+20/T+60 use trading-session offsets from the exact base
  trade date. Missing base bars, unfinished horizons, and missing snapshots are
  returned as Data Gap; current candidates and current prices are never used as
  historical substitutes.
- UI: date picker, contemporaneous market state/candidates, horizon table, and
  explicit point-in-time gap messaging are on the existing research page.
- Tests: three backend tests and two frontend tests passed; Python compile and
  production frontend build passed.
- Known data posture: dates such as 2025-04-07 require an archived scan from
  that date. The local Value Hunter database had no such row during M0/M4, so
  that date correctly returns Data Gap rather than a reconstructed claim.
- Next: M5 preview-first Feishu flow with send and scheduler disabled by default.

### M5 handoff

- Result: added a Feishu preview API and UI flow that renders the generated
  research report before any delivery action.
- Confirmation boundary: defaults are `send=false`, `confirmed=false`, and
  `scheduler=false`. Only an explicit second confirmation with `send=true`
  creates an idempotent message in the existing Investment Research outbox.
- Delivery posture: this milestone did not perform a network send and did not
  start a scheduler. The existing outbox/Feishu transport remains the sole
  delivery mechanism.
- Tests: eight backend Research MVP/outbox tests and three frontend interaction
  tests passed. Preview, confirmation gate, and duplicate suppression are
  covered without external delivery.
- Next: M6 Docker build, loopback runtime, real-data API, and browser acceptance.

### M6 handoff

- Docker: existing image built successfully and the current repository service
  is healthy at `127.0.0.1:8899`; `/live` and `/investment-research` returned
  HTTP 200. An older container from a separate worktree that occupied 8899 was
  stopped without deleting its container or volumes.
- Real-data API: authenticated `POST /investment-research/research-run` returned
  HTTP 200 from `AKShare/Eastmoney`, resolved the latest complete weekday to
  `2026-07-31`, and returned five candidates: `688111`, `688256`, `300502`,
  `300308`, and `601138`. All five included real cached prices.
- Provider resilience: live per-company enrichment exceeded 360 seconds. The
  existing provider now falls back to its most recent real candidate cache and
  surfaces the cache date as Data Gap. Research MVP explicitly opts into the
  existing scored research queue so incomplete candidates can be investigated;
  the default Value Hunter notification threshold and behavior are unchanged.
- Browser/UI evidence: the production frontend was built in Docker and served
  at the target URL. The focused UI test clicked “生成盘后研究” and verified
  market/candidate rendering, detail expansion, historical validation, and the
  two-step Feishu preview flow. Direct unauthenticated POST correctly returned
  401 because this installation has API auth enabled; the authenticated real
  API acceptance used the existing credential without printing or persisting it.
- Tests: final focused backend suite passed 16/16; Research MVP/outbox suite
  passed 8/8; frontend interaction suite passed 3/3; production frontend builds
  passed; Docker container is healthy.
- Remaining truthful Data Gaps: historical dates without archived point-in-time
  scans cannot show candidates; current market breadth can be unavailable when
  the upstream spot endpoint fails; stale-cache use is visible in the response.
- Rollback: revert the six milestone commits in reverse order. Local data and
  outbox records are not removed by code rollback.

## Personal Research Assistant continuation (2026-08-01)

### Product decision

Continue from Research MVP V1 as one **Panic Value Hunter** workflow. The
existing Investment Research API/page remains the product entry, Value Hunter
remains the scanner/scorer, the existing market-data loader registry remains
the source adapter layer, and the existing Investment Research repositories,
Historical Evaluation, Daily Pipeline, and Notification Outbox remain the
storage and delivery boundaries. No parallel research mode, database, page,
notification transport, scheduler, or execution path will be introduced.

The maximum outputs are `Research Candidate`, `Action Level`, and
`Daily Intelligence`. Candidate labels must not use Buy, Sell, Strong Buy,
position sizing, stop-loss instructions, or order-execution language.

### M0 refreshed capability audit

| Area | Reusable implementation | Verified gap / next decision |
| --- | --- | --- |
| Unified product entry | `POST /investment-research/research-run`, `frontend/src/pages/InvestmentResearch.tsx` | Keep this as the sole user-facing run path. |
| Daily orchestration | `investment_research/application/daily_pipeline.py` and existing repositories | Connect enriched snapshot/candidate records here; do not create a second daily service. |
| OHLCV provider registry | `src/market_data.py`, `backtest/loaders/registry.py`, Tushare/AKShare/Tencent loaders | Already supports fallback and Tushare stock/fund/index routing, but Value Hunter bypasses it. Introduce one Value Hunter-facing provider contract over this registry. |
| Current Value Hunter provider | `value_hunter/providers.py` | AKShare-specific market and issuer calls are coupled in one class. ETF codes are sent to stock-only endpoints and degrade to Data Gap. |
| Market snapshot | `MarketObservation`, `AkshareProvider.load_market`, `score_market` | Index moves, breadth, up/down and limit counts exist. Total turnover is absent and breadth can be lost when the spot endpoint fails. |
| Candidate observation | `CandidateObservation`, `score_candidate` | Current price, 252-day drawdown and some fundamentals exist. Daily/20-day/60-day returns, volume change, benchmark-relative strength, explicit security type and catalyst fields are absent. |
| Tushare support | Existing token settings, `backtest/loaders/tushare.py`, Tushare fundamentals provider | Token is optional and loader routing already distinguishes stock, fund, index and HK symbols. Research scanning does not yet prefer it. |
| Watchlist | `agent/value_hunter_watchlist.csv`, `VALUE_HUNTER_WATCHLIST_PATH` | The personal nine-security universe is active and cache identity is protected. Add security type and optional full-market-plus-watchlist scope without a new store. |
| Scoring | `value_hunter/scoring.py` | Existing five components do not match the single requested 30/30/20/10/10 Panic Value Hunter weighting and are hard-coded. |
| Candidate report | `research_mvp._candidate_payload`, existing candidate detail UI | Evidence, counter evidence, risk and research plan exist. Catalyst, invalidation, period returns, valuation position provenance and clearer market/company/valuation reasons are missing. |
| Historical evaluation | Stored Value Hunter point-in-time scans plus `build_historical_evaluation` | T+5/T+20/T+60 returns exist. Maximum drawdown, benchmark excess return, outcome classification and automatic matured-horizon refresh are missing. Missing snapshots must remain Data Gap. |
| Notifications | Existing Investment Research outbox and Feishu preview/confirmation | Preserve preview-only defaults. Add PANIC/EXTREME_PANIC plus high-quality-candidate eligibility before enqueue; no network send during implementation. |
| Date safety | Latest-complete-session resolution and stored-snapshot-only replay | Preserve strict point-in-time reads and never reconstruct a past candidate set from current fundamentals. |

### Working-tree boundary at refreshed M0

`main` is the only local development line. GitHub, remote pushes, and pull
requests are out of scope. Existing uncommitted files remain user-owned. The
uncommitted `trial-daily-watchlist` route/module is specifically excluded from
the implementation because it duplicates the research path, hard-codes a
second watchlist, contains mojibake, and uses entry-zone/build-position
language outside the product boundary. It remains unstaged and is not a source
for the continuation milestones.

### Continuation milestones

#### M0 - Refreshed audit

- Status: complete.
- Confirm current local Git state, existing modules, provider paths, tests,
  runtime, and product boundaries.
- Deliverable: this continuation audit and milestone handoff.

#### M1 - Real-data observation contract

- Status: complete.
- Define the normalized market/security observation required by the existing
  scanner: source/as-of/provenance, security type, OHLCV-derived changes,
  breadth, turnover, fundamentals, valuation and explicit field-level gaps.
- Adapt existing loaders; business/scoring code receives observations only.
- Preserve the current Research MVP response while adding fields compatibly.

#### M2 - Tushare-first provider

- Add a Value Hunter provider implementation/facade that prefers Tushare when
  a usable token exists, then AKShare, then existing public loader fallbacks.
- Reuse existing Tushare stock/fund/index loaders and fundamentals provider.
- Record actual source per field; provider failures become Data Gap.

#### M3 - Complete market snapshot

- Populate index moves, A-share advancers/decliners, limit up/down, turnover,
  breadth and panic reasons for the latest complete trade date.
- Never combine mismatched trade dates without surfacing a gap.

#### M4 - Single Panic Value Hunter score

- Replace the current research rank with one configurable score:
  mispricing 30%, quality 30%, valuation 20%, relative strength 10%,
  catalyst 10%.
- Market panic is a gate/context, not a second strategy mode.

#### M5 - Configuration

- Add one versioned `config/panic_value_config.yaml` with current-compatible
  defaults for panic gates, filters and score weights.
- Validate weights and thresholds at startup; invalid configuration fails
  clearly rather than silently changing the method.

#### M6 - Watchlist scope

- Extend the existing watchlist loader to support A-share and ETF entries plus
  `full_market + watchlist` scope using one configuration surface.
- Migrate the existing nine-security personal list without creating a second
  store or losing cache identity checks.

#### M7 - Candidate report enrichment

- Add market/company/valuation entry reasons, Evidence, Counter Evidence,
  Risk, Catalyst, Invalidation, current price, valuation position and forward
  validation placeholders to the existing Research Candidate contract/UI.

#### M8 - ETF support

- Use fund-specific OHLCV and metadata paths; do not call issuer-only financial
  endpoints for ETFs. ETF quality/valuation fields use fund/index evidence or
  remain explicit Data Gap.
- Include the requested major broad-market ETF coverage through the same
  watchlist/provider contract.

#### M9 - Historical validation enrichment

- Persist immutable candidate snapshots through the existing repository path.
- Calculate matured T+5/T+20/T+60 return, maximum drawdown and benchmark excess
  return; classify each horizon as correct, incorrect or uncertain using
  versioned rules and point-in-time data only.

#### M10 - Notification eligibility

- Reuse Notification Outbox and require PANIC/EXTREME_PANIC plus at least one
  high-quality candidate before preview/enqueue eligibility.
- Keep send and scheduler disabled throughout tests and personal acceptance.

#### M11 - Local acceptance

- Run focused and regression tests, production frontend build, Docker runtime,
  authenticated real-data API checks and browser interaction at
  `127.0.0.1:8899/investment-research`.
- Verify current date and an archived historical date, including honest Data
  Gap behavior where a point-in-time snapshot does not exist.

### Refreshed M0 handoff

- Branch/HEAD at audit: local `main` at `6662aa8`.
- Existing working-tree changes were inspected and left unstaged.
- Primary architectural move: make Value Hunter consume the existing loader
  registry through one normalized observation contract; do not replace either
  subsystem.
- First implementation target: M1 observation contracts and adapter tests,
  followed by M2 Tushare-first routing.
- Stop conditions remain external data entitlement/token limits, product-boundary
  changes, schema migration, notification send activation, or trade execution.

### M1 handoff

- Result: extended the existing `CandidateObservation` and Research MVP
  candidate payload with security type, current price, daily/20-session/
  60-session change, 20-session volume ratio, 252-session drawdown,
  benchmark-relative return and market-data as-of date.
- Data path: `AkshareProvider` remains the existing scanner provider but now
  obtains OHLCV in one batch through `src.market_data.fetch_market_data`; the
  scoring and Research MVP application layers consume normalized observations
  and do not call a source SDK.
- ETF posture: exchange-listed fund symbols are normalized and typed as ETF;
  registry OHLCV remains usable even when issuer-only AKShare enrichment has no
  fund result. Fund-specific fundamentals/metadata stay scheduled for M8.
- Point-in-time posture: rows later than the latest complete trade date are
  ignored. Insufficient bars, missing volume or unavailable benchmark history
  remain field-level Data Gaps.
- Cache posture: configured-watchlist caches without the new as-of field are
  invalidated once and regenerated; legacy/default cache behavior remains
  backward compatible.
- Tests: 19 focused backend tests and 3 Investment Research UI tests passed;
  TypeScript and the production Vite build passed. Existing bundle-size and
  TestClient deprecation warnings are unchanged.
- Next: M2 select Tushare first when its token is usable, preserve registry
  fallbacks, and expose actual source provenance without leaking credentials.
