# AI Investment Researcher V2 — Implementation Status

Date: 2026-07-23

## Outcome

Vibe-Trading contains an additive, isolated AI Investment Researcher V2 domain. It has no broker-order path and
does not output buy/sell or position-sizing instructions. Its strongest output is an evidence-backed Research
Candidate; weaker observations remain Discovery Leads with explicit evidence gaps or attribution questions.

## Implemented

- Project Constitution, V2 domain model, architecture, roadmap, capability research, Thesis design, Mispricing
  design, Daily Intelligence design, historical-validation design, and migration plan.
- Versioned Thesis tree with point-in-time supporting/counter evidence, catalysts, kill criteria, review dates,
  append-only history, and strict Version 1 initialization.
- JSON Thesis Initialization Manifest V3 and schema. Initialization requires the exact persisted and still-current
  approved Evidence Set Review, then atomically records Version 1, the review id, approval reference, audit record,
  and first scheduled review; identical reruns are idempotent.
- Evidence Inbox with immutable raw items, source/content/subject deduplication, pending-by-default state, and
  append-only accept/reject decisions. Accepted evidence requires final subject, direction, reviewer, rationale,
  and timestamp.
- Contextual Evidence Association ledger. Inbox acceptance atomically persists the review, one canonical neutral
  Evidence fact, and a context-relative association. One fact may support one Thesis and counter another.
- Categorical Thesis evidence readiness with explicit gaps and a first-rejection question. It checks the current
  point-in-time association heads and never emits a numerical readiness score.
- Append-only human Evidence Set Review. Approval requires the complete current set, support and counter evidence,
  the strongest counter case, quality-warning exceptions where needed, reviewer, rationale, cutoff, and approval
  reference. New evidence invalidates the displayed approval. A controlled CLI records reviews without creating a
  Thesis Version.
- Thesis Initialization Manifest V3 separates neutral source facts from contextual assessments and rejects future,
  missing, duplicated, mismatched, example-only, fabricated-review, stale-review, and cutoff-mismatched inputs.
- Asset-neutral identities for stock, ETF, index, and sector research.
- Price-move attribution split into trigger/amplifier/background and temporary/structural/uncertain permanence.
- Conservative Discovery triage that distinguishes Evidence Gap, Attribution Required, Opportunity Review,
  and rejection.
- Research Candidate and append-only Action Assessment with Watch, Research, Prepare, and Action Candidate.
- Fixed Opportunity Alert gate: valid Thesis, complete evidence, Panic/Systemic Stress, meaningful mispricing,
  temporary cause, confidence at least 85%, and Action Candidate.
- Full Daily Research Report with Market State, Thesis updates, Discovery Leads, Opportunities, Candidates,
  warnings, and a truthful “continue waiting” conclusion.
- Historical replay with frozen rule/data/model/prompt versions, point-in-time checks, process/outcome separation,
  lucky-gain/reasonable-failure classification, and Research Quality metrics.
- SQLite WAL persistence, idempotent daily jobs, notification Outbox, retry/backoff, and channel deduplication.
- Feishu webhook and SMTP transports, default disabled; dry-run tested.
- One-shot daily runner, delivery runner, and Windows Task Scheduler installer.
- Read-only FastAPI routes and `/investment-research` web page showing Daily Research, Discovery Leads,
  Candidates, Thesis initialization coverage, and pending evidence.
- Temporary anti-corruption adapter that consumes observable V1 market data while ignoring V1 scores and
  recommendation labels. External providers run with a hard timeout and degrade to explicit data gaps.
- First issuer-level point-in-time source: official SEC EDGAR filing-index ingestion. It uses precise acceptance
  timestamps where available, conservatively infers end-of-day availability otherwise, filters future records,
  and writes only pending, neutral Asset items to Evidence Inbox. It is opt-in, subscription-driven, idempotent,
  separately runnable, visible in the read-only status API, and never auto-attributes evidence or creates a
  Research Candidate.
- A-share 盘后恐慌初筛 (post-close panic shadow report) with dedicated FastAPI routes:
  `GET /investment-research/panic-shadow/status` and `POST /investment-research/panic-shadow/run`.
- Frontend panic shadow section in the Investment Research page with disabled/loading/ready/error states,
  market-state summary, data-gap warnings, watchlist scan, research candidates, and version listing.
- Dry-run / explicit-input-only mode: the report only loads from developer-provided JSON fixtures when
  `explicit_input_only` is enabled, preventing accidental runs against production market data.
- `manual_review_required: true` contract enforced server-side and validated by the frontend contract parser.
- A-share panic screening with limit-up/limit-down symbol filtering, market regime classification,
  and candidate quality/valuation/attribution evaluation.

## Verification

- V2 backend regression: 207 passed.
- Investment Research domain coverage: 94%.
- Static analysis: Ruff passed for the full V2 implementation and tests.
- Frontend regression: 250 passed across 29 test files (InvestmentResearch page tests include panic shadow).
- Frontend TypeScript/Vite production build: passed.
- JSON initialization schema: valid JSON; strict manifest tests passed.
- Full legacy backend suite: not executed in this lightweight verification environment because test collection
  requires the complete legacy dependency set (`numpy`, `pandas`, `langchain_core`, and others). This is reported
  as unverified, not as a product regression.
- Secret boundary: real credentials remain only in ignored local configuration and are excluded from packages.

## Current truthful limitation

The daily research architecture is operational, but issuer coverage is currently limited to SEC filing metadata;
A-share official disclosures, filing-body extraction, identity mastering, and high-quality price-move attribution
remain the main research bottlenecks. Accepted Evidence Associations do not
automatically create a Thesis Version. Evidence readiness and a human Evidence Set Review now prove balance and
expose source-quality exceptions; a separate reviewed Initialization Manifest V3 must still define the claim,
catalysts, kill criteria, confidence, and review schedule.

## External action awaiting confirmation

Real Feishu and email delivery has not been triggered. V2 uses dedicated `VIBE_RESEARCH_*` variables and does not
silently reuse older Value Hunter secrets. One controlled test can be sent only after explicit user confirmation.
