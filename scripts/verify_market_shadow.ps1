<#
.SYNOPSIS
    Verify Market Shadow — check that the shadow service is healthy.

.DESCRIPTION
    Verifies the shadow API server is running and responsive:
    - Checks /live endpoint returns 200 JSON
    - Checks optional route status (disabled/enabled)
    - Prints safe URLs
    - Shows configured boolean flags (no secrets)

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

# 1. Check /live
Write-Host "[1/4] Checking /live endpoint ..." -ForegroundColor Yellow
try {
    $live = Invoke-RestMethod -Uri "${base}/live" -TimeoutSec 5
    if ($live.status -eq "ok") {
        Write-Host "  /live: OK (status=$($live.status))" -ForegroundColor Green
    } else {
        Write-Host "  /live: unexpected response: $($live | ConvertTo-Json -Compress)" -ForegroundColor Yellow
    }
} catch {
    Write-Error "  /live failed: $_"
    exit 1
}

# 2. Check optional route status
Write-Host "[2/4] Checking optional routes ..." -ForegroundColor Yellow
$optionalEndpoints = @(
    "/value-hunter/status",
    "/investment-research/status",
    "/investment-research/panic-shadow/status"
)
foreach ($ep in $optionalEndpoints) {
    try {
        $resp = Invoke-WebRequest -Uri "${base}${ep}" -TimeoutSec 5 -SkipHttpErrorCheck
        $body = $resp.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        $enabled = if ($body.enabled) { "enabled" } else { "disabled" }
        $statusColor = if ($body.enabled) { "Green" } else { "DarkYellow" }
        Write-Host "  ${ep}: $enabled" -ForegroundColor $statusColor
    } catch {
        Write-Host "  ${ep}: error ($($_.Exception.Message))" -ForegroundColor Red
    }
}

# 3. Print safe URLs
Write-Host "[3/4] URLs ..." -ForegroundColor Yellow
Write-Host "  API:      ${base}" -ForegroundColor Green
Write-Host "  Docs:     ${base}/docs" -ForegroundColor Green
Write-Host "  Health:   ${base}/live" -ForegroundColor Green

# 4. Show configured booleans (no secrets)
Write-Host "[4/4] Feature flags (safe booleans only) ..." -ForegroundColor Yellow
$boolVars = @(
    "VIBE_TRADING_VALUE_HUNTER_ENABLED",
    "VIBE_TRADING_INVESTMENT_RESEARCH_ENABLED",
    "VIBE_TRADING_PANIC_SHADOW_ENABLED"
)
foreach ($var in $boolVars) {
    $val = [Environment]::GetEnvironmentVariable($var)
    if ($val -eq "1" -or $val -eq "true") {
        Write-Host "  ${var}: enabled" -ForegroundColor Green
    } else {
        Write-Host "  ${var}: disabled" -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "=== Verification complete ===" -ForegroundColor Cyan
