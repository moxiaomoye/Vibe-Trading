$partsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$partsDir = Join-Path $partsDir "parts"
Get-ChildItem -Path $partsDir -Filter "*.part1" | ForEach-Object {
    $baseName = $_.Name -replace '\.part\d+$', ''
    $outFile = Join-Path (Split-Path -Parent $partsDir) "$baseName.zip"
    Write-Host "Joining $baseName..."
    Get-ChildItem -Path $partsDir -Filter "$baseName.part*" | Sort-Object Name | ForEach-Object {
        $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
        [System.IO.File]::WriteAllBytes($outFile, [System.IO.File]::ReadAllBytes($outFile))  # append mode not supported, use stream
    }
    # Actually use streaming append
    $stream = [System.IO.File]::Create($outFile)
    Get-ChildItem -Path $partsDir -Filter "$baseName.part*" | Sort-Object Name | ForEach-Object {
        $data = [System.IO.File]::ReadAllBytes($_.FullName)
        $stream.Write($data, 0, $data.Length)
    }
    $stream.Close()
    Write-Host "  Created: $outFile ($([math]::Round((Get-Item $outFile).Length / 1MB, 2)) MB)"
}
