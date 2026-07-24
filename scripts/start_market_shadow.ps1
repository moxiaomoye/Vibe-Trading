<#
.SYNOPSIS
    Start the local Trial Release shadow environment with Docker Compose.

.DESCRIPTION
    Reuses the existing Compose image, temporarily enables only the authenticated
    Investment Research and Panic Shadow HTTP routes, waits for container health,
    and opens the browser UI. It does not install packages, build images, start
    schedulers, send notifications, or enable trading.

.PARAMETER NoBrowser
    Start and verify the service without opening a browser.

.PARAMETER WaitSeconds
    Maximum number of seconds to wait for the container to become healthy.
#>

param(
    [switch]$NoBrowser,
    [ValidateRange(10, 300)]
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$FrontendUrl = "http://127.0.0.1:8899/investment-research"
$LiveUrl = "http://127.0.0.1:8899/live"

Push-Location $ProjectRoot
try {
    & docker compose --project-directory $ProjectRoot -f $ComposeFile config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed."
    }

    $imageId = & docker compose --project-directory $ProjectRoot -f $ComposeFile images -q vibe-trading
    if ($LASTEXITCODE -ne 0 -or -not $imageId) {
        throw "No existing vibe-trading Compose image was found. Build the reviewed image first with: docker compose build vibe-trading"
    }

    $overridePath = [System.IO.Path]::Combine(
        [System.IO.Path]::GetTempPath(),
        "vibe-trading-shadow-$([guid]::NewGuid().ToString('N')).yml"
    )
    @"
services:
  vibe-trading:
    environment:
      INVESTMENT_RESEARCH_ROUTES_ENABLED: "true"
      PANIC_SHADOW_REPORT_API_ENABLED: "true"
      VALUE_HUNTER_ROUTES_ENABLED: "false"
      VALUE_HUNTER_ENABLED: "false"
      VIBE_INVESTMENT_RESEARCH_ENABLED: "false"
      VIBE_TRADING_ENABLE_SCHEDULER: "false"
      VIBE_TRADING_CHANNELS_AUTO_START: "false"
      VIBE_RESEARCH_DELIVERY_MODE: "disabled"
"@ | Set-Content -LiteralPath $overridePath -Encoding utf8

    try {
        & docker compose --project-directory $ProjectRoot -f $ComposeFile -f $overridePath up -d --no-build vibe-trading
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed to start the shadow service."
        }
    } finally {
        Remove-Item -LiteralPath $overridePath -Force -ErrorAction SilentlyContinue
    }

    $containerId = & docker compose --project-directory $ProjectRoot -f $ComposeFile ps -q vibe-trading
    if ($LASTEXITCODE -ne 0 -or -not $containerId) {
        throw "The shadow container was not created."
    }

    $deadline = (Get-Date).AddSeconds($WaitSeconds)
    $health = ""
    do {
        $health = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $containerId).Trim()
        if ($health -eq "healthy") {
            break
        }
        if ($health -in @("unhealthy", "exited", "dead")) {
            throw "The shadow container entered state '$health'."
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($health -ne "healthy") {
        throw "Timed out waiting for the shadow container to become healthy."
    }

    $live = Invoke-RestMethod -Uri $LiveUrl -TimeoutSec 10
    if ($live.status -ne "ok") {
        throw "The /live endpoint returned an unexpected response."
    }

    Write-Host "Trial Release shadow environment is healthy." -ForegroundColor Green
    Write-Host "UI:   $FrontendUrl"
    Write-Host "Live: $LiveUrl"
    Write-Host "Provider and Manual Import require the existing Server API key in Web Settings."
    Write-Host "Scheduler, notification delivery, channel auto-start, and trading remain disabled."

    if (-not $NoBrowser) {
        Start-Process $FrontendUrl
    }
} finally {
    Pop-Location
}
