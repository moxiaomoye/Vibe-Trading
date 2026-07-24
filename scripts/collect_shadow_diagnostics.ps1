<#
.SYNOPSIS
    Collect non-secret Trial Release diagnostics without changing runtime state.

.PARAMETER Port
    Local API port to probe.

.PARAMETER OutputDir
    Optional directory for a timestamped JSON copy. No existing file is deleted.
#>

param(
    [int]$Port = 8899,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$diag = [ordered]@{
    collected_at = (Get-Date).ToUniversalTime().ToString("o")
    project_root = $ProjectRoot
    port = $Port
}

Push-Location $ProjectRoot
try {
    $diag["compose_config_valid"] = $false
    & docker compose --project-directory $ProjectRoot -f $ComposeFile config --quiet
    $diag["compose_config_valid"] = ($LASTEXITCODE -eq 0)

    $containerId = & docker compose --project-directory $ProjectRoot -f $ComposeFile ps -q vibe-trading
    $diag["container_present"] = [bool]$containerId
    if ($containerId) {
        $diag["container_state"] = (& docker inspect --format "{{.State.Status}}" $containerId).Trim()
        $diag["container_health"] = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" $containerId).Trim()
    }

    try {
        $diag["live"] = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/live" -TimeoutSec 5
    } catch {
        $diag["live"] = @{ status = "unreachable"; error_type = $_.Exception.GetType().Name }
    }

    $diag["expected_shadow_flags"] = @{
        INVESTMENT_RESEARCH_ROUTES_ENABLED = $true
        PANIC_SHADOW_REPORT_API_ENABLED = $true
        VIBE_TRADING_ENABLE_SCHEDULER = $false
        VIBE_TRADING_CHANNELS_AUTO_START = $false
        VIBE_RESEARCH_DELIVERY_MODE = "disabled"
    }
} finally {
    Pop-Location
}

$json = $diag | ConvertTo-Json -Depth 5
Write-Host $json

if ($OutputDir) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $path = Join-Path $OutputDir "shadow_diagnostics_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $json | Out-File -LiteralPath $path -Encoding utf8 -NoClobber
    Write-Host "Diagnostics saved to: $path" -ForegroundColor Green
}
