# M1.3 Historical Evaluation — Ledger

## Baseline
- **Branch:** `feat/historical-evaluation-m1-3`
- **Base:** `ef45594` (M1.2, fix/trial-release-m1)
- **Worktree:** `D:\AIStock\worktrees\Vibe-Trading-opencode-week`

## Milestone Ledger

| ID | Description | Status | Commit | Tests | Runtime | Blocker |
|----|-------------|--------|--------|-------|---------|---------|
| M0 | Runtime verification & verify script | completed | 5d840db | 48/48 pass | 2.37s | None |
| M1 | Historical market panel contract | completed | 663e2d0 | 54/54 pass | 2.54s | None |
| M2 | Date-safe historical market loader | completed | 1b1aadf | 60/60 pass | 2.87s | None |
| M3 | Historical shadow run API | completed | e5cff65 | 65/65 pass | 3.22s | None |
| M4 | T+5/T+20/T+60 outcome loader | completed | 3eb08a5 | 71/71 pass | 3.21s | None |
| M5 | Historical evaluation metrics | completed | 2b5ed1b | 77/77 pass | 3.26s | None |
| M6 | Review labels (FP/FN) | completed | 7416bcf | 86/86 pass | 3.62s | None |
| M7 | ETF research support | completed | 62e2da6 | 93/93 pass | 3.69s | None |
| M8 | Historical evaluation frontend | completed | 16277bc | 96/96 pass | 4.13s | None |
| M9 | Trading calendar | completed | af2fd61 | 108/108 pass | 4.15s | None |
| M10 | Panic episode review workflow | completed | 6bd0236 | 112/112 pass | 4.44s | None |
| M11 | Low-risk hardening | completed | 7741b2c | 112/112 pass | 4.39s | None |
| M12 | Comprehensive validation | completed | c1274fe | 117/117 pass | 4.72s | None |
| M13 | Docs & handoff | completed | 2cd6fba | 117/117 pass | 6.56s | None |

## Known Gaps (carried forward)
1. SZSE Provider: blocked_by_api_documentation
2. Tushare: permission_denied
3. No frontend tooling (npm/node)
4. Docker verification deferred
5. AGENTS.md missing at root
