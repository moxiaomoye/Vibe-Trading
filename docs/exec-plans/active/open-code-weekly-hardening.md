# OpenCode Weekly Shadow Hardening Queue

## Baseline

- **Branch:** `agent/opencode-weekly-hardening`
- **Base commit:** `2352ff9` (docs: update exec plan ledger and PROGRESS.md for Phase B completion)
- **Base branch:** `agent/opencode-phase-b-contracts`
- **Worktree:** `D:\AIStock\worktrees\Vibe-Trading-opencode-week`
- **Created:** 2026-07-24

## Git & Docker Status

| Check | Status |
|-------|--------|
| Branch | `agent/opencode-weekly-hardening` |
| HEAD | `2352ff9` |
| Working tree | Clean |
| Staging | Empty |
| Diff check | Clean |

## Milestone Ledger

| ID | Description | Status | Commit | Tests | Findings | Blocker |
|----|-------------|--------|--------|-------|----------|---------|
| W0 | Worktree setup & ledger | done | — | — | AGENTS.md and PROJECT_CONSTITUTION.md not found | — |
| W1 | Credential & exception redaction matrix | done | `2c5a421` | 31 | Extended _redact_query_secrets to cover token/access_token; fixed sk- regex in check_connectivity.py for dashed keys | — |
| W2 | Optional routes full-state contract | done | `a44aa1c` | 10 | Auth failure, duplicate registration, failure isolation, DB/trading side-effect tests | — |
| W3 | Point-in-Time / No-Lookahead adversarial | done | `01fae90` | 24 | Fixed FixtureFinancialProvider: datetime.now() → as_of-based comparison for determinism | — |
| W4 | Determinism, idempotency & stable serialization | done | `6e833ca` | 11 | Fixture determinism, dict-order independence, fingerprint consistency | — |
| W5 | Provider failure/fallback matrix | pending | — | — | — | — |
| W6 | Shadow report evidence completeness matrix | pending | — | — | — | — |
| W7 | Frontend state & usability hardening | skipped | — | — | No frontend tooling available; documented for GPT-5.6 | — |
| W8 | Safe diagnostic & verification scripts | pending | — | — | — | — |
| W9 | Report readability & human review quality | pending | — | — | — | — |
| W10 | Bounded performance measurement | pending | — | — | — | — |
| W11 | Documentation consistency audit | pending | — | — | — | — |
| W12 | TODO/Stub/Risk inventory | pending | — | — | — | — |
| W13 | Release evidence pack & handoff | pending | — | — | — | — |
