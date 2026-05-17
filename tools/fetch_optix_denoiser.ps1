param(
    [string]$Repository = "Ahmed-Hindy/NvidiaAIDenoiser",
    [string]$Tag = "hdu-multilayer-exr-output-8893b60",
    [string]$AssetName = "optix-denoiser-windows-x64-8893b60.zip"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\windows-x64"
$denoiserExe = Join-Path $vendorDir "Denoiser.exe"
$expectedCommit = "8893b605903f273512b750d45993bbe27a003362"

if (Test-Path -LiteralPath $denoiserExe) {
    Write-Host "Bundled OptiX denoiser already exists: $denoiserExe"
    exit 0
}

New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null
$downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hdu-optix-denoiser-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $downloadDir | Out-Null

try {
    $localZip = $env:HDU_OPTIX_DENOISER_ZIP
    if ($localZip) {
        if (-not (Test-Path -LiteralPath $localZip)) {
            throw "HDU_OPTIX_DENOISER_ZIP points to a missing file: $localZip"
        }
        Copy-Item -LiteralPath $localZip -Destination (Join-Path $downloadDir $AssetName)
    }
    else {
        gh release download $Tag --repo $Repository --pattern $AssetName --dir $downloadDir
    }

    $zipPath = Join-Path $downloadDir $AssetName
    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Downloaded denoiser asset not found: $zipPath"
    }

    $extractDir = Join-Path $downloadDir "extract"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $foundExe = Get-ChildItem -LiteralPath $extractDir -Filter "Denoiser.exe" -Recurse | Select-Object -First 1
    if (-not $foundExe) {
        throw "Denoiser.exe was not found in $zipPath"
    }

    Copy-Item -LiteralPath $foundExe.FullName -Destination $denoiserExe -Force
    Get-ChildItem -LiteralPath $extractDir -Filter "manifest.json" -Recurse |
        Select-Object -First 1 |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $vendorDir "manifest.json") -Force
        }

    $manifestPath = Join-Path $vendorDir "manifest.json"
    if (Test-Path -LiteralPath $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($manifest.source_commit -and $manifest.source_commit -ne $expectedCommit) {
            throw "Bundled denoiser commit mismatch: expected $expectedCommit, got $($manifest.source_commit)"
        }
    }

    Write-Host "Bundled OptiX denoiser installed: $denoiserExe"
}
finally {
    if (Test-Path -LiteralPath $downloadDir) {
        Remove-Item -LiteralPath $downloadDir -Recurse -Force
    }
}
