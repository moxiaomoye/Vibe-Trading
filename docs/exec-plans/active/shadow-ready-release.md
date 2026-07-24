# AI Investment Researcher V2 — Shadow-Ready Release

## Status

Branch: `agent/opencode-shadow-ready`
Base: `deeda0c` (M0 Existing Worktree Intake)

## Milestone Ledger

| Milestone | Description | Status | Commit | Notes |
|-----------|------------|--------|--------|-------|
| M0 | Existing Worktree Intake | ✅ Done | `deeda0c` | 13 files committed |
| M1 | Test Suite Hygiene | ✅ Done | `deeda0c` | 41/41 key tests pass; env dependency errors are pre-existing (missing `requests`, `rich`, `fastmcp` etc.) |
| M2 | Optional Routes Hardening | ✅ Done | `deeda0c` | DisabledStub + 13 optional routes tests pass; 7 panic-shadow tests pass; 8 IR tests pass |
| M3 | SZSE & Credential Infrastructure | ⏸️ Partial | `deeda0c` | Env vars, provider config status, connectivity check done. **Soft-blocked by missing SZSE API docs.** |
| M4 | SZSE Route-Variant Research Endpoints | ⏸️ Blocked | — | Depends on M3 SZSE provider unblocking |
| M5 | Feature-Freeze & Polish | ✅ Done | `80f7425` | No credentials in tracked files; compileall clean; 41/41 tests; example files sanitised; .gitignore correct; Soft Blockers documented in Ledger |
| M6 | Tier-3 Shadow-Release Validation | ✅ Done | `80f7425` | 123 tests pass; compileall clean; no credentials leaked; disabled stub API contract validated (JSON not SPA); feature isolation verified; Soft Blockers documented |

## Phase A — Usable Market Shadow MVP

| Milestone | Description | Status | Notes |
|-----------|------------|--------|-------|
| A0 | Fix review findings (Ledger hash, credential leak, POST status) | ✅ Done | `agent/api_server.py`, `agent/src/api/investment_research_routes.py`, `agent/src/config/check_connectivity.py` |
| A1 | One-command startup script (`start_market_shadow.ps1`) | ✅ Done | `scripts/start_market_shadow.ps1` created, sets `PYTHONPATH` automatically |
| A2 | Wire real Sina market data into shadow pipeline | ✅ Done | `SinaBenchmarkAdapter` fixed for historical `as_of`; `run_market_shadow.py` fetches Sina spot (5530 rows) + CSI300 benchmark |
| A3 | Manual shadow run → JSON/Markdown report | ✅ Done | Verified: panic scan (panic), watchlist (20/20 matched), reports saved to `agent/data/` |
| A4 | Docker + browser auto-acceptance test | ⏸️ Deferred | Not required for MVP; manual `start_market_shadow.ps1` suffices |

Known Phase A limitations (Phase B items):
- `agent/data/` output directory added to `.gitignore`
- 3 report-level data gaps (broad_index_drawdown, index_long_trend, turnover_stress) — need historical data
- Per-symbol sector data gaps — need sector mapping
- Research candidates = 0 when regime != PANIC — expected scheduler gate behaviour

Phase B (post-A): point-in-time financial provider contracts, announcement/event contracts, asset/issuer identity mapping, historical attribution, small-scale historical validation.

## Soft Blockers

### SZSE Provider — `blocked_by_api_documentation`

**Blocker:** Missing official SZSE Data API technical specification.

**Already in place:**
- Configuration fields: `SZSE_DATA_ACCESS_KEY`, `SZSE_DATA_ACCESS_SECRET`, `SZSE_DATA_ACCESS_TOKEN` (env_schema.py)
- Provider config status: `get_provider_config("szse_data")` returns `configured`/`missing` (market_data_providers.py)
- Connectivity check: `check_szse_data()` returns `blocked_by_api_documentation` with structured error (check_connectivity.py)
- 13 credential-config tests pass (test_market_data_providers.py)
- Credential values never exposed in status output

**Recovery conditions** (user must provide):
1. Base URL
2. Auth flow (Key + Secret + Token — roles/order)
3. Request header names
4. Signature algorithm + canonical string format
5. Timestamp, nonce, expiry rules
6. At least one announcement or market-data endpoint path
7. Request example (with sanitised values)
8. Success response example
9. Error code reference

**Rule:** No fake `szse_provider.py`. No placeholder signature against real service.

### Tushare — `permission_denied`

**Blocker:** Tushare Pro token authenticates but account lacks probe endpoint permissions (trade_cal, daily, daily_basic, stock_basic all return "没有接口访问权限").

**Already in place:**
- Configuration field: `TUSHARE_TOKEN` (env_schema.py)
- Provider config status: `get_provider_config("tushare")` (market_data_providers.py)
- Connectivity check: `check_tushare()` detects `permission_denied` vs `upstream_unavailable`
- Fallback probe sequence (4 endpoints) already implemented

**Rule:** Do not retry real calls. Treat as Soft Blocker. Complete Provider protocol, mock, fixture, error classification, and data gap without requiring a real token now.

## Notes

- M0 commit `deeda0c` merged all work into a single intake commit. No uncommitted changes to split.
- All M1/M2 tests pass. Ledger marked done for those milestones.
- M3 is partial — infrastructure done, provider implementation soft-blocked.
- Continue with any pending Milestone whose dependencies are satisfied.
