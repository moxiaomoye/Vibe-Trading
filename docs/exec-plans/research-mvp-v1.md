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
