# M1.3 Validation — Ledger

## Baseline
- **Branch:** `fix/m1-3-validation`
- **HEAD:** `c2c5876` (V3 no-lookahead audit)
- **M1.2 Base:** `ef45594`

## Milestone Ledger

| ID | Status | Commit | Tests | Runtime | Findings | Blocker |
|----|--------|--------|-------|---------|----------|---------|
| V0 | done | a6e618a | 117/117 | 5.51s | 14 milestones, 24 new files (11 src + 11 test + 2 docs), no TODO/FIXME, NotImplementedError=expected abstract base pattern, no financial threshold modifications, clean | None |
| V1 | done | — | 121 pass / 12 pre-existing fail / 87 pre-existing collection errors | 4.36s | 52 pre-M1.3 + 69 M1.3 tests pass; 12 test_cli_interactive.py pre-existing; 87 collection errors = missing deps (python-multipart, fastmcp, jinja2, scipy, defusedxml, aiohttp, yfinance) — all pre-existing, not M1.3 | None |
| V2 | done | — | Frontend: 38/38 test files, 322/322 tests pass, tsc OK, build OK | 17.00s | InvestmentResearch page has historical date/manual import/shadow report/outcome features. Build succeeded. | None |
| V3 | done | c2c5876 | 194 M1.3 tests pass; 4 new audit tests; 3 low-risk fixes | 4.71s | Fixed: (1) validator uses Shanghai date not UTC for future check, (2) conflicting_versions report bug, (3) manual import 18:30 cutoff. Tests added for timezone boundary, cutoff, fingerprint immutability, clock skew. | None |
| V4 | pending | — | — | — | — | — |
| V5 | pending | — | — | — | — | — |
| V6 | pending | — | — | — | — | — |
| V7 | pending | — | — | — | — | — |
| V8 | pending | — | — | — | — | — |
| V9 | pending | — | — | — | — | — |
| V10 | pending | — | — | — | — | — |
| V11 | pending | — | — | — | — | — |
| V12 | pending | — | — | — | — | — |

## Known Gaps (carried forward from M1.3)
1. SZSE Provider: blocked_by_api_documentation
2. Tushare: permission_denied
3. No frontend tooling (npm/node)
4. Docker verification deferred
5. AGENTS.md missing at root
