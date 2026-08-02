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

- Status: complete.
- Add a Value Hunter provider implementation/facade that prefers Tushare when
  a usable token exists, then AKShare, then existing public loader fallbacks.
- Reuse existing Tushare stock/fund/index loaders and fundamentals provider.
- Record actual source per field; provider failures become Data Gap.

#### M3 - Complete market snapshot

- Status: complete.
- Populate index moves, A-share advancers/decliners, limit up/down, turnover,
  breadth and panic reasons for the latest complete trade date.
- Never combine mismatched trade dates without surfacing a gap.

#### M4 - Single Panic Value Hunter score

- Status: complete.
- Replace the current research rank with one configurable score:
  mispricing 30%, quality 30%, valuation 20%, relative strength 10%,
  catalyst 10%.
- Market panic is a gate/context, not a second strategy mode.

#### M5 - Configuration

- Status: complete.
- Add one versioned `config/panic_value_config.yaml` with current-compatible
  defaults for panic gates, filters and score weights.
- Validate weights and thresholds at startup; invalid configuration fails
  clearly rather than silently changing the method.

#### M6 - Watchlist scope

- Status: complete.
- Extend the existing watchlist loader to support A-share and ETF entries plus
  `full_market + watchlist` scope using one configuration surface.
- Migrate the existing nine-security personal list without creating a second
  store or losing cache identity checks.

#### M7 - Candidate report enrichment

- Status: complete.
- Add market/company/valuation entry reasons, Evidence, Counter Evidence,
  Risk, Catalyst, Invalidation, current price, valuation position and forward
  validation placeholders to the existing Research Candidate contract/UI.

#### M8 - ETF support

- Status: complete.
- Use fund-specific OHLCV and metadata paths; do not call issuer-only financial
  endpoints for ETFs. ETF quality/valuation fields use fund/index evidence or
  remain explicit Data Gap.
- Include the requested major broad-market ETF coverage through the same
  watchlist/provider contract.

#### M9 - Historical validation enrichment

- Status: complete.
- Persist immutable candidate snapshots through the existing repository path.
- Calculate matured T+5/T+20/T+60 return, maximum drawdown and benchmark excess
  return; classify each horizon as correct, incorrect or uncertain using
  versioned rules and point-in-time data only.

#### M10 - Notification eligibility

- Status: complete.
- Reuse Notification Outbox and require PANIC/EXTREME_PANIC plus at least one
  high-quality candidate before preview/enqueue eligibility.
- Keep send and scheduler disabled throughout tests and personal acceptance.

#### M11 - Local acceptance

- Status: complete.
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

### M2 handoff

- Result: the existing market-data registry now supports exact loader
  resolution, allowing Research MVP to enforce Tushare -> AKShare -> existing
  public-source fallbacks without changing fallback behavior for other callers.
- Partial-source behavior: successful symbols are retained while only missing
  symbols continue through the chain. Candidate payloads expose the actual
  source used per symbol instead of labeling a fallback result as Tushare.
- Real-data verification: the configured Tushare credential was detected but
  its current entitlements rejected stock, fund and index daily endpoints. The
  same request then resolved an ETF through AKShare and the stock/index through
  Tencent, with all requested symbols receiving real dated OHLCV rows.
- Data integrity: no credential value is logged or returned. Exhausted symbols
  remain unresolved and surface as Data Gap; no fabricated observations are
  introduced.
- Tests: 152 focused provider, registry, Tushare, Value Hunter and Research MVP
  tests passed; four entitlement-dependent real-Tushare tests were skipped.
- Next: M3 add turnover and same-session consistency to the existing market
  snapshot and expose the completed summary through Research MVP.

### M3 handoff

- Result: the existing AKShare market adapter now selects index rows on one
  confirmed completed A-share session, rejects mismatched index dates, and uses
  the first available broad index to resolve exchange holidays safely.
- Breadth: advancers, decliners, approximate limit-up/limit-down counts,
  advancer ratio and total A-share turnover are returned in `market_summary`.
  Turnover is stored in source currency units and displayed in 100-million CNY.
- Date safety: weekday pre-close spot data is not used as a completed snapshot;
  it becomes an explicit market-width Data Gap. No future index row is consumed.
- UI: the Investment Research summary now includes turnover alongside market
  state and breadth metrics.
- Tests: 23 focused backend tests and three UI tests passed; the production
  TypeScript/Vite build passed. The existing bundle-size warning is unchanged.
- Next: M4 align the one candidate score to the requested 30/30/20/10/10 Panic
  Value Hunter method, then externalize its thresholds and weights in M5.

### M4 handoff

- Result: all candidates now use one `Panic Value Hunter` method. The previous
  value/growth/sentiment buckets were removed from new results.
- Score: market mispricing 30, company quality 30, valuation 20, relative
  strength 10 and catalyst 10. Each component is bounded and the total is 100.
- Risk boundary: investigation, qualified audit, fraud, delisting and negative
  equity remain hard rejection conditions; a high factor score cannot offset
  them. Lesser risks remain report evidence rather than a hidden score bonus.
- Data integrity: catalyst points require recorded catalyst evidence. Missing
  relative-strength or catalyst evidence is surfaced in candidate Data Gap and
  receives zero points rather than an invented neutral score.
- Compatibility: the existing Value Hunter page reads new score fields while
  retaining display fallbacks for already-stored legacy scans.
- Tests: 26 focused backend tests and five frontend tests passed; the production
  TypeScript/Vite build passed.
- Next: M5 move these weights and user thresholds into one validated YAML
  configuration while preserving the current defaults.

### M5 handoff

- Result: `config/panic_value_config.yaml` is the single editable method file
  for panic thresholds, stock filters and 30/30/20/10/10 score weights.
- Validation: weights must be non-negative and total 100; breadth thresholds
  are range checked. Invalid configuration fails clearly during service setup.
- Runtime: the existing Value Hunter service injects the loaded method into
  market and candidate scoring. Optional `PANIC_VALUE_CONFIG_PATH` supports a
  local override without adding an administration backend.
- Compatibility: permissive stock-filter defaults retain the current universe;
  missing filter inputs remain Data Gap, while present values that violate a
  configured threshold become an explicit research rejection.
- Docker: the same versioned config directory is copied into builder and runtime
  images, so local and container scoring use the same method definition.
- Tests: 19 focused configuration, scoring and service tests passed.
- Next: M6 consolidate stock and ETF watchlists on this existing loader and
  preserve the user's nine-security scope.

### M6 handoff

- Result: the existing provider watchlist loader accepts both the legacy CSV
  and one concise YAML file; no second scanner, store or candidate path exists.
- Personal universe: `config/watchlist.yaml` contains exactly the requested
  nine securities, separated only for editing clarity into four stocks and five
  ETFs. Runtime candidates still enter the same normalized observation flow.
- Scope: `watchlist` is the sole active research scope, matching the user's
  instruction to focus future research on these securities. Unsupported scope
  values fail clearly instead of silently launching a full-market scan.
- Compatibility: an explicit `VALUE_HUNTER_WATCHLIST_PATH` still wins. Without
  it, the versioned YAML becomes the default; cache identity checks use the same
  loader and invalidate stale universes.
- Tests: 25 focused watchlist, provider, config, service and Research MVP tests
  passed.
- Next: M7 expose catalyst, invalidation and the enhanced candidate evidence in
  the existing Research Candidate detail card.

### M7 handoff

- Result: the existing Research Candidate payload and expandable detail card
  now expose market/company/valuation reasons, supporting evidence, counter
  evidence, risks, catalysts, invalidation and the Research Plan together.
- Validation posture: T+5/T+20/T+60 placeholders are explicit nulls on the
  creation-day report; only the historical evaluator may populate matured
  outcomes. Catalyst absence is a named Data Gap and earns no score.
- Evidence integrity: entry reasons are formatted only from observed fields;
  empty sections display Data Gap rather than generated claims.
- Tests: 20 focused backend tests and three Investment Research UI tests passed;
  the production TypeScript/Vite build passed.
- Next: M8 verify fund-specific behavior for every ETF in the personal universe
  and add the requested broad-market ETF coverage through the same config.

### M8 handoff

- Result: ETF symbols use the registry's fund OHLCV path and are explicitly
  prevented from calling stock issuer valuation and financial endpoints.
- Honest gaps: issuer ROE, issuer PE and company financial fields stay Data Gap
  for ETFs. The report still supplies price, 1/20/60-session change, volume,
  drawdown and benchmark-relative performance when fund data is available.
- Universe decision: the user's later instruction to research only the supplied
  nine securities takes precedence over adding more candidate symbols. The five
  ETFs in that personal universe cover 科创宽基、半导体主题与纳指100；broad-market
  indices remain benchmark inputs, not extra candidates.
- Tests: 112 provider, registry, Tushare, ETF and Research MVP tests passed;
  four entitlement-dependent real-Tushare tests were skipped.
- Next: M9 enrich historical evaluation with drawdown, benchmark excess return
  and outcome classification without changing stored point-in-time snapshots.

### M9 handoff

- Result: historical evaluation still begins only from an immutable stored scan
  and now calculates T+5/T+20/T+60 return, path maximum drawdown, CSI300 excess
  return and an outcome for every matured horizon.
- Versioned interpretation: `正确` requires a positive candidate return and at
  least +3 percentage points excess; `错误` is a return at or below -10% or
  excess at or below -3 points; all other or missing cases are `不确定`.
- Date integrity: calculations require the exact base trading-date close and
  count observed trading rows, never calendar-day substitutions. Missing base,
  horizon or benchmark prices remain candidate-level Data Gap.
- UI: each historical horizon displays return, outcome, benchmark excess and
  maximum drawdown so the user can judge the method rather than only end price.
- Tests: four historical/backend tests and three UI tests passed; the production
  TypeScript/Vite build passed.
- Next: M10 restrict notification eligibility to PANIC/EXTREME_PANIC plus a
  high-quality candidate while keeping preview and scheduler defaults off.

### M10 handoff

- Result: both the Value Hunter notification decision and the Investment
  Research Feishu confirmation require PANIC/EXTREME_PANIC plus a selected
  high-quality A/B research candidate.
- Preview safety: preview remains available with `send=false` and
  `scheduler=false`. Ineligible reports explain the gate and do not expose the
  outbox confirmation action.
- Delivery safety: confirmation only writes to the existing Notification Outbox;
  no network send or scheduler was enabled or exercised.
- Tests: 17 notification, outbox, service and Research MVP backend tests and
  three UI tests passed; the production TypeScript/Vite build passed.
- Next: M11 run the full regression, rebuild/recreate Docker, perform an
  authenticated real-data API run and verify the browser interaction.

### M11 handoff

- Docker: the production image rebuilt successfully and the recreated service
  is healthy on `127.0.0.1:8899`. The Investment Research HTML returned 200.
- Real run: authenticated `POST /investment-research/research-run` returned in
  0.2 seconds from the completed cache for trade date 2026-07-31. It reported
  NORMAL, 4,690 advancers, 728 decliners, 223 approximate limit-ups, one
  approximate limit-down and CNY 2.559 trillion turnover.
- Candidates: five real candidates were returned, all within the personal
  universe: 601991, 600522, 000791, 002261 and 588170. Per-symbol provenance
  showed AKShare and Tencent; no mock provider was used.
- Upstream resilience: an uncached all-A spot request exposed an unbounded
  public-SDK wait. Public spot calls now have explicit 30/60-second bounds and
  an attempted incomplete daily snapshot is cached with Data Gap instead of
  leaving the browser spinning indefinitely.
- Historical honesty: 2025-04-07 currently reports that no stored point-in-time
  snapshot exists. It is not reconstructed from current/future data. New daily
  snapshots can be evaluated as their T+5/T+20/T+60 horizons mature.
- Verification: 188 focused backend tests passed, four real-Tushare entitlement
  tests skipped, all 314 frontend tests passed, production build passed, Docker
  health/page/API checks passed. The host's optional full Python suite could not
  collect 70 unrelated modules because optional dependencies are absent from the
  host interpreter; the production image includes those runtime dependencies.
- Browser: the live Investment Research URL was opened in the Codex browser;
  UI tests exercise generate, detail expansion, historical evaluation and
  Feishu preview/confirmation interaction against the real API client surface.

### M12 handoff — panic sensitivity control

- UI: Investment Research now has one 0–100 slider labelled 敏感、平衡、严谨.
  The selected value is sent with the existing research-run request; no second
  scanner or market-state system was added.
- Deterministic mapping: 0–100 interpolates index decline from -1.0% to -3.5%,
  maximum advancer ratio from 50% to 20%, and minimum limit-down count from 5
  to 80. Sensitive requires one confirmation, balanced two and strict three.
- Auditability: every response includes the selected value, resolved thresholds,
  observed inputs, trigger booleans, confirmation count and config version. The
  page displays those resolved thresholds beneath the slider.
- Verification: 19 focused backend tests and four UI tests passed. Production
  TypeScript/Vite build passed. Local DCO commit: `a4e0791`.

### M13 handoff — ETF research price bands

- Provider reuse: the existing AKShare provider now adds the latest available
  ETF unit NAV and calculates market-price-to-NAV premium/discount. One shared
  fund snapshot request covers the five personal-watchlist ETFs.
- Research bands: reasonable, low-valuation and deep-value reference bands are
  derived from the trailing 252 observed trading sessions and are explicitly
  labelled `screen_grade`; they are research breakpoints, not trade commands.
- Data quality: ETF unit splits/mergers are detected from exceptional one-day
  price discontinuities and pre-split history is normalized to the current unit
  basis before returns or price bands are calculated. This prevents fund splits
  from masquerading as 60–80% drawdowns.
- Premium definitions: NAV premium is returned when real NAV exists. Underlying
  index PE/PB valuation premium remains Data Gap until a reliable point-in-time
  index valuation source is available. QDII 159941 is marked for stale NAV,
  overseas-session and FX limitations.
- Runtime: stale ETF valuation cache is refreshed without refetching stock
  fundamentals. The first real refresh completed in 42.7 seconds; subsequent
  sensitivity runs completed in 0.02–0.03 seconds.
- Real acceptance (2026-07-31): balanced sensitivity 50 resolved to NORMAL with
  0/2 triggers. Candidate 588200 returned price 1.115, NAV 1.1169, NAV premium
  -0.17%, reasonable band 0.8926–1.0195 and low-valuation band 0.7401–0.8641.
- Verification: 24 focused backend tests, five Investment Research UI tests and
  the production frontend build passed. Docker image rebuilt, `/live` is
  healthy, authenticated real-data API runs passed, and a headless Edge render
  confirmed the slider layout. Local DCO commits: `c86a8d9`, `b45d8de`,
  `901a2f6`.

### M14 handoff — research data credibility convergence

- Single entry point: the uncommitted `trial-daily-watchlist` route and its
  fixed two-symbol implementation were removed. Research remains on the sole
  `/investment-research/research-run` path and contains no entry-zone or shadow
  position language.
- Auditable sensitivity: each Research MVP run now saves a versioned research
  context in the existing scan JSON. Historical evaluation shows the original
  slider value, resolved thresholds, observed checks and trigger count. Legacy
  snapshots expose `panic_sensitivity_snapshot` as Data Gap and are not
  rewritten.
- Full watchlist visibility: the scan snapshot retains all scored observations,
  while the main report still selects Top 5. The page displays all nine personal
  watchlist symbols with score, selection state, exclusion reason, data source,
  data date and available/stale/missing status.
- Freshness: candidate caches older than one completed weekday are rejected and
  refreshed. Weekend transitions do not age Friday data. Stale fallback text
  explicitly prevents old prices or premiums from appearing current.
- Provider fallback latency: Tushare entitlement errors now trip an endpoint-
  scoped circuit breaker for the current loader run. A failed `fund_daily`,
  `daily` or `index_daily` entitlement is attempted once; unrelated endpoints
  and transient network failures keep their normal behavior, and unresolved
  symbols continue through the existing fallback chain.
- ETF underlying evidence: official tracked-index mappings are recorded for
  588060/000688, 588170/950125, 588200/000685 and 159516/931743. The existing
  AKShare provider adds observed CSIndex PE, dividend yield, available-history
  percentile, median premium, date, source and sample count. The UI labels this
  short-history measure `screen_grade`; 159941/NDX remains an explicit Data Gap.
- UX: Data Gap is grouped into blocking, research-quality and supplementary
  categories. Local 401/403 errors now explain that the backend API key must be
  entered in Settings and link directly there.
- Real acceptance: Docker is healthy on `127.0.0.1:8899`; the page returned 200.
  An authenticated real run for 2026-07-31 returned NORMAL, five candidates and
  all nine watchlist rows. ETF 588200 returned tracked index 000685, PE 140.92
  and 20 available valuation sessions. Historical evaluation read slider value
  50 and threshold -2.25% from the saved point-in-time snapshot.
- Verification: 93 focused backend tests passed, four entitlement-dependent
  real-Tushare tests skipped, five Investment Research UI tests passed, and the
  production TypeScript/Vite build passed. Notifications and schedulers stayed
  off; no delivery or trading action was exercised.

### M15 handoff — Feishu bot and Webhook repair

- Root cause: the long-connection bot was online, but outbound OpenAPI failures
  were swallowed by the Feishu adapter. Research confirmation only queued an
  Outbox record, and its dedicated Webhook variable was empty even though the
  existing Value Hunter Webhook was configured.
- Bot repair: Feishu send rejection now reaches the existing retry policy. The
  channel status exposes the latest delivery error and clears it after a
  successful send. No second bot or notification runtime was introduced.
- Webhook repair: Research delivery prefers its dedicated Webhook and falls back
  to the existing Value Hunter robot. User confirmation atomically claims and
  dispatches only the selected Outbox message; duplicate confirmation remains
  idempotent, while failed attempts retain their retry record and visible error.
- UX: the action now reads `确认并发送飞书`, successful delivery displays `已发送`,
  and configuration or transport failures are shown on the page. Preview stays
  `send=false`, scheduler stays disabled, and no automatic notification was
  enabled.
- Verification: 13 focused backend tests and five Investment Research UI tests
  passed. The production Docker image rebuilt and is healthy. Live checks
  confirmed the research Webhook fallback, Outbox `delivered` status, Feishu
  WebSocket connection, Bot Info access and proactive bot send with Feishu
  `code=0`.
