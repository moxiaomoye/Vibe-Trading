param(
    [string]$PythonExecutable = "python",
    [string]$RepoRoot = "D:\AIStock\Vibe-Trading",
    [string]$TaskName = "VibeTrading-AI-Investment-Researcher"
)

$ErrorActionPreference = "Stop"
$agentRoot = Join-Path $RepoRoot "agent"
$dailyScript = Join-Path $agentRoot "scripts\run_investment_research_daily.py"
$deliveryScript = Join-Path $agentRoot "scripts\deliver_investment_research.py"

if (-not (Test-Path -LiteralPath $dailyScript) -or -not (Test-Path -LiteralPath $deliveryScript)) {
    throw "Investment Researcher scripts were not found under $agentRoot"
}

$command = "Set-Location -LiteralPath '$agentRoot'; & '$PythonExecutable' '$dailyScript'; & '$PythonExecutable' '$deliveryScript'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -Command `"$command`""
$trigger = New-ScheduledTaskTrigger -Daily -At "18:30"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "AI Investment Researcher daily research and notification delivery" -Force
Write-Host "Scheduled task installed: $TaskName"
