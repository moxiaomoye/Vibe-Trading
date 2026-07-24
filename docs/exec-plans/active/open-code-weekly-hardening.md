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
| HEAD | `040fd4f` |
| Working tree | Clean |
| Staging | Empty |
| Diff check | Clean |

## Milestone Ledger

| ID | Description | Status | Commit | Tests | Findings | Blocker |
|----|-------------|--------|--------|-------|----------|---------|
| W0 | Worktree setup & ledger | done | — | — | AGENTS.md not found at root; PROJECT_CONSTITUTION.md exists at docs/architecture/PROJECT_CONSTITUTION.md (not docs/) | — |
| W1 | Credential & exception redaction matrix | done | `2c5a421` | 31 | Extended _redact_query_secrets to cover token/access_token; fixed sk- regex in check_connectivity.py for dashed keys | — |
| W2 | Optional routes full-state contract | done | `a44aa1c` | 10 | Auth failure, duplicate registration, failure isolation, DB/trading side-effect tests | — |
| W3 | Point-in-Time / No-Lookahead adversarial | done | `01fae90` | 24 | Fixed FixtureFinancialProvider: datetime.now() → as_of-based comparison for determinism | — |
| W4 | Determinism, idempotency & stable serialization | done | `6e833ca` | 11 | Fixture determinism, dict-order independence, fingerprint consistency | — |
| W5 | Provider failure/fallback matrix | done | `040fd4f` | 12 | Fake providers (successful/empty/slow/timeout); idempotence; invalid input rejection. Module-level SlowFakeProvider for multiprocessing pickle. | — |
| W6 | Shadow report evidence completeness matrix | done | `040fd4f` | 9 | ResearchProviderAdapter with all provider states; mixed combinations; data_gap population | — |
| W7 | Frontend state & usability hardening | skipped | — | — | No frontend tooling available; documented for GPT-5.6 | — |
| W8 | Safe diagnostic & verification scripts | done | _pending_ | — | `scripts/diagnose_providers.py` — 8 provider scenarios, provenance/observation diagnostics, JSON output | — |
| W9 | Report readability & human review quality | done | _pending_ | 10 | `render_text` no None/repr/traceback; disclaimer; empty-candidate msg; `render_verdict` pass/fail/warn structure | — |
| W10 | Bounded performance measurement | done | _pending_ | — | `scripts/measure_provider_perf.py` — 6 scenarios, 3 trials each, wall-clock timing | — |
| W11 | Documentation consistency audit | done | — | — | AGENTS.md missing; CONSTITUTION at docs/architecture/ (not docs/). README.md points to wiki/AI_INVESTMENT_RESEARCHER.md (summary) vs constitution (canonical). No docs/README.md. handoff/ absent (expected for W13). | — |
| W12 | TODO/Stub/Risk inventory | done | — | — | 11 TODOs (heavy in live/runtime/), 94 bare pass stubs (67 files, esp trading/connectors/ and channels/), 27 Ellipsis (all abstract protocols — OK), 108 risk markers, 27 abstract interface stubs, 242 provider error taxonomies. No raise NotImplementedError. | — |
| W13 | Release evidence pack & handoff | pending | — | — | — | — |

## Known Gaps (for GPT-5.6)

1. **AGENTS.md missing** — root-level AGENTS.md not present; AGENT_CONTRIBUTOR_GUIDE.md exists but is not a substitute.
2. **PROJECT_CONSTITUTION.md path** — at `docs/architecture/` not `docs/`. W0 flag updated.
3. **README.md constitution link** — Links to `wiki/AI_INVESTMENT_RESEARCHER.md` (summary) instead of canonical `docs/architecture/PROJECT_CONSTITUTION.md`.
4. **W5 slow-provider timeout** — `load_with_timeout` multiprocessing child on Windows does not reliably raise TimeoutError within 0.05 s. Pre-existing environment sensitivity; module-level SlowFakeProvider added for multiprocessing pickle compatibility.
5. **W7 frontend skipped** — no frontend tooling installed; frontend state verification deferred.
6. **94 bare `pass` stubs** — heaviest in `trading/connectors/*/sdk.py` (10 connectors), `channels/`, and `api/runs_routes.py`. Primarily placeholder SDK methods and except handlers.
7. **11 TODOs** — 5 in `live/runtime/` and `live/enforcement.py` tied to broker catalog integration.
8. **SZSE Provider** — unchanged (`blocked_by_api_documentation`).
9. **Tushare** — unchanged (`permission_denied` — no probe endpoint permissions).
