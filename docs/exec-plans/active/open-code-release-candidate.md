# OpenCode Release Candidate Build

## Baseline

- **Branch:** `agent/opencode-release-candidate`
- **Base commit:** `9b16498` (docs: fix ledger HEAD and W8/W9/W10 commit references)
- **Base branch:** `agent/opencode-weekly-hardening`
- **Worktree:** `D:\AIStock\worktrees\Vibe-Trading-opencode-week`
- **Created:** 2026-07-24

## Git & Docker Status

| Check | Status |
|-------|--------|
| Branch | `agent/opencode-release-candidate` |
| HEAD | `c9ddd0a` |
| Working tree | Dirty (3 new scripts, ledger update) |
| Staging | scripts/, docs/ |
| Diff check | Clean |

## Docker

| Check | Status |
|-------|--------|
| Running | unknown |
| compose config | unknown |
| 8899 default-off | unknown |
| 8898 enabled | unknown |

## Current Manual-Run Entry Point

- `scripts/start_market_shadow.ps1` — starts shadow service on port 8899
- `scripts/stop_market_shadow.ps1` — stops the shadow service (graceful + force)
- `scripts/verify_market_shadow.ps1` — checks /live, optional routes, prints URLs & flags
- `scripts/collect_shadow_diagnostics.ps1` — collects process/port/live/flags/env info

## Milestone Ledger

| ID | Description | Status | Commit | Tests | Runtime | Blocker |
|----|-------------|--------|--------|-------|---------|---------|
| RC0 | Ledger & baseline | done | adaaa97 | — | — | — |
| RC1 | Executable acceptance flow | done | c9ddd0a | 24/24 | 0.8s | — |
| RC2 | One-command local release mode | done | d8ce65d | — | — | — |
| RC3 | Complete current-market input modes | done | 6441e3f | 14 tests | 0.2s | — |
| RC4 | End-to-end manual shadow run | done | db1120e | — | — | — |
| RC5 | Local report storage | done | da08e34 | 8 tests | 0.2s | — |
| RC6 | Frontend completion | skipped | — | — | — | No frontend tooling (same as W7) |
| RC7 | Smoke validation | done | b9583c1 | 2/3 smoke | 0.3s | 1 skipped (needs network) |
| RC8 | Bounded feedback workflow | done | 0827b21 | 7 tests | 0.2s | — |
| RC9 | Final automated validation | done | — | 109/110 | 2.9s | 1 skipped (provider needs network) |
| RC10 | User guide | done | pending | — | — | — |
| RC11 | Freeze and GPT-5.6 handoff | pending | — | — | — | — |

## Known Gaps (carried forward)

1. AGENTS.md missing — root-level not present; AGENT_CONTRIBUTOR_GUIDE.md exists
2. PROJECT_CONSTITUTION.md at docs/architecture/ not docs/
3. SZSE Provider: blocked_by_api_documentation
4. Tushare: permission_denied
5. W7 frontend skipped — no frontend tooling in environment
6. 94 bare pass stubs in trading/connectors/ and channels/
7. No Docker verification yet
