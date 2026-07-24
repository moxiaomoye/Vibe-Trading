# Shadow Release Candidate Guide

## Quick Start

Start the shadow service:

```powershell
.\scripts\start_market_shadow.ps1
```

Run a shadow report only (no server):

```powershell
.\scripts\start_market_shadow.ps1 -ShadowOnly
```

Stop the service:

```powershell
.\scripts\stop_market_shadow.ps1
```

Verify health:

```powershell
.\scripts\verify_market_shadow.ps1
```

Collect diagnostics:

```powershell
.\scripts\collect_shadow_diagnostics.ps1
```

## URLs (when server is running)

| Resource | URL |
|----------|-----|
| API | http://127.0.0.1:8899 |
| API Docs | http://127.0.0.1:8899/docs |
| Health Check | http://127.0.0.1:8899/live |

## Input Modes

### Provider mode (default)

Fetches live A-share market data from Sina (free, no auth required).

### Manual import mode

Create a JSON file with the following format:

```json
{
  "schema_version": "1.0",
  "source": "manual_import",
  "source_date": "2026-07-24",
  "availability_time": "2026-07-24T15:00:00+00:00",
  "rows": [
    {
      "symbol": "000001",
      "name": "平安银行",
      "close": 12.5,
      "previous_close": 12.3,
      "change_percent": 1.63
    }
  ]
}
```

Required fields per row: `symbol`, `name`, `close`, `previous_close`, `change_percent`.
Optional fields: `volume`, `market`, `benchmark`, `limit_status`, `sector_mapping`, `watchlist_override`.

Run with manual input:

```powershell
python -m scripts.run_market_shadow --mode manual --input-file path/to/data.json
```

## API Endpoints

### Default routes (always available)

- `GET /live` — health check
- `GET /sessions` — list sessions
- `GET /runs` — list runs

### Optional routes (gated by env vars)

| Endpoint | Method | Description | Env Var |
|----------|--------|-------------|---------|
| `/value-hunter/status` | GET | Value hunter status | `VIBE_TRADING_VALUE_HUNTER_ENABLED` |
| `/investment-research/status` | GET | Research status | `VIBE_TRADING_INVESTMENT_RESEARCH_ENABLED` |
| `/investment-research/panic-shadow/status` | GET | Shadow status | `VIBE_TRADING_PANIC_SHADOW_ENABLED` |
| `/investment-research/panic-shadow/run` | POST | Run with explicit data | `VIBE_TRADING_PANIC_SHADOW_ENABLED` |
| `/investment-research/panic-shadow/run-current` | POST | Run with live data | `VIBE_TRADING_PANIC_SHADOW_ENABLED` |

## Report Locations

Reports are saved to `agent/data/` by default:
- `agent/data/latest.json` — most recent report
- `agent/data/YYYY-MM-DD/<fingerprint>.json` — dated reports
- `agent/data/YYYY-MM-DD/<fingerprint>.md` — dated markdown

## Bounded Feedback Workflow

Run a 40-trading-day historical evaluation:

```powershell
python -m src.scripts.bounded_feedback_workflow --days 40
```

## Watchlist

Edit `config/research/a_share_watchlist.yaml` to customize the watchlist.

## Known Limitations

1. No Docker environment — requires local Python 3.11+
2. SZSE provider blocked by API documentation availability
3. Tushare requires permission that is not available
4. Frontend not served (no frontend build tooling)
5. 94 pass stubs in connector/channel code
6. No real financial/event providers — uses fixture data
7. Real provider smoke test skipped without network access

## Rollback

```powershell
git checkout agent/opencode-weekly-hardening
```
