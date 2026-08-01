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

- Generate a preview from the research result.
- Require explicit user confirmation before any send path.
- Keep `send=false` and `scheduler=false` by default; do not send during tests.
- Test, inspect diff, commit, update handoff.

### M6 - Real runtime acceptance

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
