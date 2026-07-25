<#
.SYNOPSIS
    Check that market-data provider credentials are configured.

.DESCRIPTION
    Reads the four SZSE/Tushare env vars available in the current session
    (or from .env.market-data.local) and reports each as "configured" or
    "missing".  Exits with code 0 when all are present, non-zero otherwise.
    Never outputs credential values, partial values, hashes, or lengths.
#>

$vars = @(
    "SZSE_DATA_ACCESS_KEY"
    "SZSE_DATA_ACCESS_SECRET"
    "SZSE_DATA_ACCESS_TOKEN"
    "TUSHARE_TOKEN"
)

$allPresent = $true

foreach ($var in $vars) {
    $val = [Environment]::GetEnvironmentVariable($var)
    if ([string]::IsNullOrEmpty($val)) {
        Write-Output "${var}: missing"
        $allPresent = $false
    } else {
        Write-Output "${var}: configured"
    }
}

if (-not $allPresent) {
    exit 1
}
