<#
.SYNOPSIS
    Verify Market Shadow — check that the shadow service is healthy and M1.2 features are present.

.DESCRIPTION
    Reports:
    - Current Git branch and commit
    - Running image / container info (Docker or local)
    - /live health check
    - Shadow API status and date features
    - Feature flags (safe booleans only, no secrets)
    - Scheduler/notification/trading off

.PARAMETER Port
    Port the shadow server is listening on (default 8899).

.PARAMETER Host
    Host address (default 127.0.0.1).

.EXAMPLE
    .\scripts\verify_market_shadow.ps1
    .\scripts\verify_market_shadow.ps1 -Port 8898
#>

param(
    [int]$Port = 8899,
    [string]$Host = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$base = "http://${Host}:${Port}"

Write-Host "=== Market Shadow Verification ===" -ForegroundColor Cyan
Write-Host ""

# 0. Git info
Write-Host "[0/7] Git info ..." -ForegroundColor Yellow
try {
    $branch = & git -C "$PSScriptRoot/.." branch --show-current 2>$null
    $commit = & git -C "$PSScriptRoot/.." rev-parse --short HEAD 2>$null
    Write-Host "  Branch: $branch" -ForegroundColor Green
    Write-Host "  Commit: $commit" -ForegroundColor Green
} catch {
    Write-Host "  Git info unavailable: $_" -ForegroundColor Yellow
}

# 1. Docker / runtime info
Write-Host "[1/7] Runtime info ..." -ForegroundColor Yellow
try {
    $imageId = docker inspect --format '{{.Id}}' vibe-trading 2>$null
    $created = docker inspect --format '{{.Created}}' vibe-trading 2>$null
    if ($imageId) {
        Write-Host "  Image: $imageId" -ForegroundColor Green
        Write-Host "  Created: $created" -ForegroundColor Green
    } else {
        Write-Host "  No Docker container 'vibe-trading' found (local mode)" -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  Docker not available (local mode)" -ForegroundColor DarkYellow
}

# 2. Check /live
Write-Host "[2/7] Checking /live endpoint ..." -ForegroundColor Yellow
try {
    $live = Invoke-RestMethod -Uri "${base}/live" -TimeoutSec 5
    if ($live.status -eq "ok" -or $live.status -eq "healthy") {
        Write-Host "  /live: OK (status=$($live.status))" -ForegroundColor Green
    } else {
        Write-Host "  /live: unexpected response: $($live | ConvertTo-Json -Compress)" -ForegroundColor Yellow
    }
} catch {
    Write-Error "  /live failed: $_"
    exit 1
}

# 3. Check shadow status and date features
Write-Host "[3/7] Shadow status & date features ..." -ForegroundColor Yellow
$shadowEndpoints = @(
    "/investment-research/panic-shadow/status"
)
foreach ($ep in $shadowEndpoints) {
    try {
        $resp = Invoke-WebRequest -Uri "${base}${ep}" -TimeoutSec 5 -SkipHttpErrorCheck
        $body = $resp.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 401) {
            Write-Host "  ${ep}: authentication required" -ForegroundColor DarkYellow
        } elseif ($body.enabled) {
            Write-Host "  ${ep}: enabled" -ForegroundColor Green
            Write-Host "    mode: $($body.mode)" -ForegroundColor Green
            Write-Host "    scheduler_enabled: $($body.scheduler_enabled)" -ForegroundColor $(if ($body.scheduler_enabled) {"Red"} else {"Green"})
            Write-Host "    notification_enabled: $($body.notification_enabled)" -ForegroundColor $(if ($body.notification_enabled) {"Red"} else {"Green"})
            Write-Host "    trading_enabled: $($body.trading_enabled)" -ForegroundColor $(if ($body.trading_enabled) {"Red"} else {"Green"})
        } else {
            Write-Host "  ${ep}: disabled" -ForegroundColor DarkYellow
        }
    } catch {
        Write-Host "  ${ep}: error ($($_.Exception.Message))" -ForegroundColor Red
    }
}

# 4. Check /latest (date feature indicator)
Write-Host "[4/7] Date features ..." -ForegroundColor Yellow
try {
    $latest = Invoke-WebRequest -Uri "${base}/investment-research/panic-shadow/latest" -TimeoutSec 5 -SkipHttpErrorCheck
    if ($latest.StatusCode -eq 200) {
        Write-Host "  /latest: available (report storage working)" -ForegroundColor Green
    } else {
        Write-Host "  /latest: status $($latest.StatusCode)" -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  /latest: not reachable (no report yet)" -ForegroundColor DarkYellow
}

# 5. Print safe URLs
Write-Host "[5/7] URLs ..." -ForegroundColor Yellow
Write-Host "  API:      ${base}" -ForegroundColor Green
Write-Host "  Docs:     ${base}/docs" -ForegroundColor Green
Write-Host "  Health:   ${base}/live" -ForegroundColor Green

# 6. Show configured booleans (no secrets)
Write-Host "[6/7] Feature flags (safe booleans only) ..." -ForegroundColor Yellow
$boolVars = @(
    "INVESTMENT_RESEARCH_ROUTES_ENABLED",
    "PANIC_SHADOW_REPORT_API_ENABLED",
    "VIBE_TRADING_ENABLE_SCHEDULER",
    "VIBE_TRADING_CHANNELS_AUTO_START",
    "VIBE_TRADING_ENABLE_TRADING"
)
foreach ($var in $boolVars) {
    $val = [Environment]::GetEnvironmentVariable($var)
    if ($val -eq "1" -or $val -eq "true") {
        Write-Host "  ${var}: enabled" -ForegroundColor Green
    } else {
        Write-Host "  ${var}: disabled" -ForegroundColor DarkYellow
    }
}

# 7. Check frontend bundle
Write-Host "[7/7] Frontend bundle ..." -ForegroundColor Yellow
$frontendDist = Join-Path $PSScriptRoot ".." "agent" "frontend" "dist"
if (Test-Path $frontendDist) {
    Write-Host "  Frontend dist exists: $frontendDist" -ForegroundColor Green
} else {
    Write-Host "  No frontend dist found (not built)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=== Verification complete ===" -ForegroundColor Cyan
