<#
.SYNOPSIS
    Start Market Shadow — one-command launcher for the usable market shadow MVP.

.DESCRIPTION
    1. Installs akshare (free, no-auth market data) if not present
    2. Runs the market shadow report with real A-share data
    3. Starts the API server + frontend on localhost
    4. Opens the browser

    No credentials required.  No notifications sent.  No trades executed.

.EXAMPLE
    .\scripts\start_market_shadow.ps1

    # Run shadow report only (no server):
    .\scripts\start_market_shadow.ps1 -ShadowOnly
#>

param(
    [switch]$ShadowOnly,
    [string]$Date = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AgentDir = Join-Path $ProjectRoot "agent"

Write-Host "=== Market Shadow MVP ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Ensure akshare is available
Write-Host "[1/4] Checking market data dependencies ..." -ForegroundColor Yellow
python -c "import akshare" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing akshare (free, no-auth market data library) ..."
    pip install akshare -q
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install akshare. Please run: pip install akshare"
        exit 1
    }
    Write-Host "  akshare installed."
} else {
    Write-Host "  akshare is available."
}

# Step 2: Run shadow report
Write-Host "[2/4] Running market shadow report ..." -ForegroundColor Yellow
$dateArg = if ($Date) { "--date", $Date } else { @() }
$outputArg = if ($OutputDir) { "--output-dir", $OutputDir } else { @() }

$reportJson = $null
$reportMd = $null
Push-Location $AgentDir
try {
    $env:PYTHONPATH = $AgentDir
    $output = python -m scripts.run_market_shadow @dateArg @outputArg 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host $output -ForegroundColor Red
        Write-Error "Shadow report failed (exit code: $exitCode)"
        exit 1
    }
    Write-Host $output
    # Extract the JSON and MD paths from output
    foreach ($line in $output) {
        if ($line -match "JSON report saved: (.+)") {
            $reportJson = $Matches[1]
        }
        if ($line -match "Markdown report saved: (.+)") {
            $reportMd = $Matches[1]
        }
    }
} finally {
    Pop-Location
}

# Step 3: Start API server
if (-not $ShadowOnly) {
    Write-Host "[3/4] Starting API server ..." -ForegroundColor Yellow
    $serverProcess = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList @(
        "$AgentDir/api_server.py", "--port", "8899"
    )

    Write-Host "  API server starting on http://127.0.0.1:8899" -ForegroundColor Green
    Write-Host "  API docs: http://127.0.0.1:8899/docs" -ForegroundColor Green

    # Step 4: Open report in browser
    Write-Host "[4/4] Opening report ..." -ForegroundColor Yellow
    if ($reportMd -and (Test-Path $reportMd)) {
        Start-Process $reportMd
    } elseif ($reportJson -and (Test-Path $reportJson)) {
        Start-Process $reportJson
    }

    Write-Host ""
    Write-Host "=== Market Shadow MVP is running ===" -ForegroundColor Green
    Write-Host "  API:  http://127.0.0.1:8899" -ForegroundColor Green
    if ($reportMd) { Write-Host "  Report: $reportMd" -ForegroundColor Green }
    if ($reportJson) { Write-Host "  JSON:   $reportJson" -ForegroundColor Green }
    Write-Host ""
    Write-Host "  Endpoints:" -ForegroundColor Cyan
    Write-Host "  GET  /investment-research/panic-shadow/status" -ForegroundColor Cyan
    Write-Host "  POST /investment-research/panic-shadow/run    (explicit input only)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor Yellow

    $serverProcess.WaitForExit()
} else {
    Write-Host "[3-4/4] Skipped (ShadowOnly mode)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "=== Shadow report complete ===" -ForegroundColor Green
    if ($reportMd) { Write-Host "  Report: $reportMd" -ForegroundColor Green }
    if ($reportJson) { Write-Host "  JSON:   $reportJson" -ForegroundColor Green }
}
