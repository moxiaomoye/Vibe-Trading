<#
.SYNOPSIS
    Collect Market Shadow diagnostics for debugging.

.DESCRIPTION
    Gathers system state, process info, recent logs, and safe config
    booleans.  Output is written to stdout and optionally to a file.
    No secrets are collected or displayed.

.PARAMETER Port
    Port the shadow server is listening on (default 8899).

.PARAMETER OutputFile
    Optional path to write diagnostics JSON to.

.EXAMPLE
    .\scripts\collect_shadow_diagnostics.ps1
    .\scripts\collect_shadow_diagnostics.ps1 -OutputDir C:\tmp\diag
#>

param(
    [int]$Port = 8899,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$diag = @{}

Write-Host "=== Market Shadow Diagnostics ===" -ForegroundColor Cyan

# 1. Process info
Write-Host "[1/5] Process info ..." -ForegroundColor Yellow
$procs = Get-Process -Name python -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, CPU, WorkingSet64, StartTime,
        @{N="CommandLine";E={($_.CommandLine -replace '(?i)(api_key|token|secret|password)=[^\s&]+', '$1=***') -replace '(?i)(sk-[a-zA-Z0-9]{10,})', 'sk-***'}} |
    Where-Object { $_.CommandLine -match "api_server" -or $_.CommandLine -match "uvicorn" }
$diag["processes"] = $procs | ForEach-Object { $_ | Select-Object * -ExcludeProperty CommandLine }

# 2. Port binding
Write-Host "[2/5] Port binding ..." -ForegroundColor Yellow
$tcp = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
$diag["port_binding"] = $tcp

# 3. /live check
Write-Host "[3/5] /live check ..." -ForegroundColor Yellow
try {
    $live = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/live" -TimeoutSec 5
    $diag["live"] = $live
    Write-Host "  OK" -ForegroundColor Green
} catch {
    $diag["live"] = "unreachable"
    Write-Host "  Unreachable: $_" -ForegroundColor Red
}

# 4. Feature flags (safe booleans only)
Write-Host "[4/5] Feature flags ..." -ForegroundColor Yellow
$flags = @{}
$boolVars = @(
    "VIBE_TRADING_VALUE_HUNTER_ENABLED",
    "VIBE_TRADING_INVESTMENT_RESEARCH_ENABLED",
    "VIBE_TRADING_PANIC_SHADOW_ENABLED"
)
foreach ($var in $boolVars) {
    $val = [Environment]::GetEnvironmentVariable($var)
    $flags[$var] = if ($val -eq "1" -or $val -eq "true") { $true } else { $false }
}
$diag["feature_flags"] = $flags

# 5. Python environment
Write-Host "[5/5] Python info ..." -ForegroundColor Yellow
$diag["python_version"] = python --version 2>&1 | Out-String
$diag["working_directory"] = Get-Location | Select-Object -ExpandProperty Path

# Output
Write-Host ""
$json = $diag | ConvertTo-Json -Depth 3
Write-Host $json
Write-Host ""

if ($OutputDir) {
    $path = Join-Path $OutputDir "shadow_diagnostics_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $json | Out-File -FilePath $path -Encoding utf8
    Write-Host "Diagnostics saved to: $path" -ForegroundColor Green
}

Write-Host "=== Diagnostics complete ===" -ForegroundColor Cyan
