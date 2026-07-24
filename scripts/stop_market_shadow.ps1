<#
.SYNOPSIS
    Stop the local Trial Release shadow service without deleting data.

.DESCRIPTION
    Stops only the Compose vibe-trading service while preserving containers,
    named volumes, images, reports, and user data.
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"

Push-Location $ProjectRoot
try {
    & docker compose --project-directory $ProjectRoot -f $ComposeFile stop vibe-trading
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to stop the shadow service."
    }
    Write-Host "Shadow service stopped. Containers, images, volumes, and reports were preserved." -ForegroundColor Green
} finally {
    Pop-Location
}
