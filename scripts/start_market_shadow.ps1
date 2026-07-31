<#
.SYNOPSIS
    Start the local Trial Release shadow environment with Docker Compose.

.DESCRIPTION
    Reuses the existing Compose image, temporarily enables the authenticated
    Investment Research, Panic Shadow, and manual Value Hunter HTTP routes,
    waits for container health, and opens the browser UI. It does not install
    packages or enable trading. Research delivery, the Feishu channel, and the
    read-only daily research scheduler remain opt-in switches.

.PARAMETER NoBrowser
    Start and verify the service without opening a browser.

.PARAMETER Build
    Build the local Compose image before starting so current working-tree
    changes are included. No packages are installed on the host.

.PARAMETER EnableFeishuBot
    Start only the channels already enabled in the protected agent config.
    This is opt-in so a normal shadow launch remains side-effect free.

.PARAMETER EnableNotifications
    Enable configured research-only notification transports. Delivery failures
    remain isolated from the research pipeline.

.PARAMETER EnableDailyAutomation
    Enable one idempotent post-close research run per trading day. This never
    enables broker, order, or real-money execution.

.PARAMETER WaitSeconds
    Maximum number of seconds to wait for the container to become healthy.
#>

param(
    [switch]$NoBrowser,
    [switch]$Build,
    [switch]$EnableNotifications,
    [switch]$EnableFeishuBot,
    [switch]$EnableDailyAutomation,
    [ValidateRange(10, 300)]
    [int]$WaitSeconds = 120
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"
$FrontendUrl = "http://127.0.0.1:8899/investment-research"
$LiveUrl = "http://127.0.0.1:8899/live"
$HistoricalSample = Join-Path $ProjectRoot "examples\historical_evaluation_sample.json"

Push-Location $ProjectRoot
try {
    & docker compose --project-directory $ProjectRoot -f $ComposeFile config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed."
    }

    if ($Build) {
        & docker compose --project-directory $ProjectRoot -f $ComposeFile build vibe-trading
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed to build the local vibe-trading image."
        }
    }

    $imageName = (& docker compose --project-directory $ProjectRoot -f $ComposeFile config --images |
        Select-Object -First 1).Trim()
    if (-not $imageName) {
        throw "Docker Compose did not resolve an image name for vibe-trading."
    }
    & docker image inspect $imageName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "No existing vibe-trading Compose image was found. Build the reviewed image first with: docker compose build vibe-trading"
    }

    $overridePath = [System.IO.Path]::Combine(
        [System.IO.Path]::GetTempPath(),
        "vibe-trading-shadow-$([guid]::NewGuid().ToString('N')).yml"
    )
    $deliveryMode = if ($EnableNotifications) { "live" } else { "disabled" }
    $channelAutoStart = if ($EnableFeishuBot) { "true" } else { "false" }
    $dailyAutomation = if ($EnableDailyAutomation) { "true" } else { "false" }
    @"
services:
  vibe-trading:
    environment:
      INVESTMENT_RESEARCH_ROUTES_ENABLED: "true"
      PANIC_SHADOW_REPORT_API_ENABLED: "true"
      VALUE_HUNTER_ROUTES_ENABLED: "true"
      VALUE_HUNTER_ENABLED: "false"
      VIBE_INVESTMENT_RESEARCH_ENABLED: "false"
      VIBE_TRADING_ENABLE_SCHEDULER: "false"
      VIBE_TRADING_CHANNELS_AUTO_START: "$channelAutoStart"
      VIBE_RESEARCH_DELIVERY_MODE: "$deliveryMode"
      VIBE_RESEARCH_DAILY_AUTOMATION_ENABLED: "$dailyAutomation"
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
    if ($live.status -notin @("healthy", "ok")) {
        throw "The /live endpoint returned an unexpected response."
    }

    Write-Host "Trial Release shadow environment is healthy." -ForegroundColor Green
    Write-Host "UI:   $FrontendUrl"
    Write-Host "Live: $LiveUrl"
    Write-Host "T+20 sample: $HistoricalSample"
    Write-Host "Provider and Manual Import require the existing Server API key in Web Settings."
    if ($EnableNotifications) {
        Write-Host "Research delivery is enabled."
        if ($EnableDailyAutomation) {
            Write-Host "Daily read-only research automation is enabled at the configured time."
            Write-Host "Real trading remains disabled."
        } else {
            Write-Host "Daily automation remains disabled; sends require explicit confirmation."
        }
    } else {
        Write-Host "Scheduler, notification delivery, channel auto-start, and trading remain disabled."
        Write-Host "To enable manual Feishu/email delivery, rerun with -EnableNotifications."
    }
    if ($EnableDailyAutomation -and -not $EnableNotifications) {
        Write-Host "Daily research generation is enabled, but delivery remains disabled."
    }
    if ($EnableFeishuBot) {
        Write-Host "Configured Feishu bot channel auto-start is enabled."
    } else {
        Write-Host "To start the configured Feishu bot, rerun with -EnableFeishuBot."
    }

    if (-not $NoBrowser) {
        Start-Process $FrontendUrl
    }
} finally {
    Pop-Location
}
