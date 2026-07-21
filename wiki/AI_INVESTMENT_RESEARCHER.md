# AI Investment Researcher

## Mission

This project is not a stock recommender, price predictor, automated trader, or position-sizing tool. Its mission is to reduce a large investable universe to a small number of evidence-backed **Research Candidates** when fear, liquidity pressure, expectation resets, or temporary events may create a mispricing.

The optimization target is **Research Quality and Decision Quality**, especially fewer false-positive opportunities. A profitable outcome does not prove that the research process was sound, and a loss caused by an unknowable event does not automatically prove that the process was flawed.

## Research flow

```text
Market State
  -> Thesis and Thesis Version
  -> Discovery Lead
  -> Price-move attribution and permanence review
  -> Mispricing Opportunity
  -> Research Candidate
  -> Action Level
  -> Daily Research Report / rare Opportunity Alert
```

A Discovery Lead is deliberately weaker than an Opportunity. A price decline with incomplete fundamentals becomes `Evidence Gap`; intact fundamentals with an unexplained decline becomes `Attribution Required`. Only a two-sided, point-in-time evidence set can advance to Opportunity review.

## Output boundary

Action Levels are `Watch`, `Research`, `Prepare`, and `Action Candidate`. They prioritize research work and do not instruct a trade. The system contains no broker execution path in the Investment Research domain.

## Current V2 capabilities

- Versioned Thesis tree with supporting evidence, counter evidence, catalysts, kill criteria, and review dates.
- Strict Thesis Version 1 initialization from a point-in-time Manifest V3. Initialization is atomic,
  idempotent, and requires a persisted, still-current, approved Evidence Set Review. The review id and approval
  reference are retained in the initialization audit.
- Evidence Inbox that keeps automatically collected material pending until an explicit, append-only
  accept/reject review records its subject, direction, reviewer, rationale, and review time.
- First issuer-level point-in-time ingestion chain for official SEC EDGAR filings. Exact SEC acceptance time is
  used when available; a missing time is conservatively placed at the filing day's UTC end and carries a quality
  warning. New filings enter the Inbox as neutral Asset evidence only: they never create a Thesis direction,
  Research Candidate, Action Level, or alert without later human review.
- Contextual Evidence Association ledger. Raw evidence is stored as neutral; support/counter direction belongs
  to a Thesis, Market State, Asset, Opportunity, or Validation context and can change only by superseding history.
- Evidence readiness uses categorical gates rather than a score: no evidence, missing support, missing counter,
  source-quality review, ready for human review, or approved for initialization. Every state exposes the first
  rejection question.
- Evidence Set Reviews are append-only human decisions. Approval requires the complete current association set,
  both sides of the Thesis, the strongest counter evidence, a named reviewer, rationale, time cutoff, and approval
  reference. New contextual evidence makes the old approval stale. Approval never creates a Thesis Version.
- Asset-neutral model for stocks, ETFs, indices, and sectors.
- Point-in-time Market State assessment using correlated stress signals.
- Conservative Mispricing Discovery triage with explicit evidence gaps and first-rejection questions.
- Price-move attribution split into trigger, amplifier, and background, plus temporary/structural/uncertain permanence.
- Research Candidate and Action Level history with fixed Opportunity Alert gates.
- Daily research report that may truthfully conclude that no opportunity exists.
- Historical replay that separates process quality from realized return and identifies lucky gains and reasonable failures.
- Idempotent daily jobs, SQLite WAL persistence, notification Outbox, retries, Feishu webhook, and SMTP adapters.
- External public-data providers run in a separate process with a hard timeout; a stalled source degrades to an explicit data gap instead of blocking the daily report.
- Read-only web surface at `/investment-research`.

## Known product gap

The architecture and end-to-end daily pipeline are operational, and one official U.S. issuer-disclosure source is
now available. Coverage remains narrow: A-share exchange disclosures, filing-body extraction, issuer identity
mastering, and two-sided semantic research are still research bottlenecks. Automatic evidence attribution remains
out of scope. Until reviewed sources produce point-in-time, two-sided evidence, the system correctly withholds
Thesis confidence and Research Candidates. This is an intentional quality gate, not a missing recommendation feature.

## Local run

1. Copy `agent/.env.example` to `agent/.env` and leave delivery in `disabled` or `dry_run` until verified.
2. Bootstrap Thesis identities:

   ```powershell
   Set-Location D:\AIStock\Vibe-Trading\agent
   python scripts\bootstrap_investment_research.py
   ```

3. After recording an approved Evidence Set Review, prepare a Manifest V3 using
   `agent/schemas/thesis_initialization.schema.json` and
   `agent/schemas/thesis_initialization.example.json`, then initialize one Thesis:

   ```powershell
   python scripts\initialize_thesis.py path\to\reviewed-initialization.json
   ```

   A Thesis remains `uninitialized` and has no displayed confidence until this gate succeeds.
   The example uses the reserved provider `example-only` and is deliberately rejected until every placeholder
   source is replaced with reviewed evidence.

   Before initialization, inspect `/investment-research/evidence-readiness`. When the evidence is ready, record
   the separate human gate with `scripts/review_evidence_set.py`. The command records an auditable decision only;
   it does not initialize the Thesis.

4. Start the project using its normal backend/frontend launcher.
5. Open `http://localhost:5173/investment-research` for the frontend development server, or the host/port exposed by Docker.
6. Run the daily pipeline after 18:30 Asia/Shanghai:

   ```powershell
   python scripts\run_investment_research_daily.py
   python scripts\deliver_investment_research.py
   ```

   Optional issuer-disclosure intake can be tested separately before joining the daily task:

   ```powershell
   python scripts\ingest_issuer_disclosures.py `
     --subscriptions schemas\issuer_disclosure_subscriptions.example.json `
     --database path\to\investment_research_v2.sqlite3
   ```

   The example subscription is disabled. Copy it to a local configuration file, choose explicit assets/forms,
   then set `VIBE_INVESTMENT_RESEARCH_ISSUER_DISCLOSURES_ENABLED=true` and
   `VIBE_INVESTMENT_RESEARCH_ISSUER_SUBSCRIPTIONS_PATH` only after reviewing the manifest.

7. After dry-run validation, install the Windows daily task from an elevated PowerShell session:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install_investment_research_task.ps1
   ```

Real webhook URLs and email authorization codes belong only in local environment configuration. They must not be committed.

## Evidence boundary

Evidence Inbox acceptance now atomically creates a neutral canonical Evidence record and a contextual association.
Thesis Initialization Manifest V3 validates contextual directions and names the exact persisted Evidence Set Review.
The CLI and atomic database write both reject missing, fabricated, stale, rejected, cutoff-mismatched, or
approval-reference-mismatched reviews. Evidence readiness and the append-only Evidence Set Review make
completeness, balance, quality exceptions, and human approval visible before initialization.
Manual preparation of the reviewed initialization proposal remains deliberate: evidence approval does not invent
the core claim, catalysts, kill criteria, confidence, or next review date.
