<#
.SYNOPSIS
    Stop Market Shadow — stop the local shadow API server.

.DESCRIPTION
    Stops the Python process running api_server.py on the configured port.
    Only stops the shadow service — does not touch Docker or other processes.

.PARAMETER Port
    Port the shadow server is listening on (default 8899).

.PARAMETER Force
    Force-kill the process if graceful shutdown fails.

.EXAMPLE
    .\scripts\stop_market_shadow.ps1
    .\scripts\stop_market_shadow.ps1 -Port 8898 -Force
#>

param(
    [int]$Port = 8899,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Find python process listening on the given port
$proc = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.OwningProcess -gt 0 } |
    Select-Object -First 1

if (-not $proc) {
    Write-Host "No process found listening on port $Port. Nothing to stop." -ForegroundColor Yellow
    exit 0
}

$pid = $proc.OwningProcess
$process = Get-Process -Id $pid -ErrorAction SilentlyContinue

if (-not $process) {
    Write-Host "Process $pid no longer exists." -ForegroundColor Yellow
    exit 0
}

Write-Host "Stopping shadow server (PID $pid) on port $Port ..." -ForegroundColor Yellow

if ($Force) {
    $process.Kill()
    Write-Host "Force-stopped." -ForegroundColor Green
} else {
    $process.CloseMainWindow() | Out-Null
    $wait = $process.WaitForExit(5000)
    if (-not $wait) {
        Write-Host "Graceful shutdown timed out, force-stopping ..." -ForegroundColor Yellow
        $process.Kill()
    }
    Write-Host "Shadow server stopped." -ForegroundColor Green
}
