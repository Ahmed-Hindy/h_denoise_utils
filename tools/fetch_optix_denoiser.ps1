param(
    [string]$Repository = "Ahmed-Hindy/NvidiaAIDenoiser",
    [string]$Tag = "optix-denoiser-v2026.05.18",
    [string]$SourceShortSha = "fc927b7",
    [string[]]$OptixVersions = @("8.1", "9.0", "9.1")
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\windows-x64"
$expectedSourceCommit = "fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf"
$expectedOptixCommits = @{
    "8.1" = "50021ea0af6d41609a97777ceebbdf1e1d34efe7"
    "9.0" = "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
    "9.1" = "f1f6dd803f3159992d248178f6e09421c6eb8b6d"
}

function Get-OptixAssetName {
    param([Parameter(Mandatory = $true)][string]$Version)
    return "optix-denoiser-windows-x64-optix-$Version-$SourceShortSha.zip"
}

function Get-OptixVariantDir {
    param([Parameter(Mandatory = $true)][string]$Version)
    return Join-Path $vendorDir "optix-$Version"
}

function Test-OptixVariantInstalled {
    param([Parameter(Mandatory = $true)][string]$Version)
    $variantDir = Get-OptixVariantDir -Version $Version
    return (
        (Test-Path -LiteralPath (Join-Path $variantDir "Denoiser.exe")) -and
        (Test-Path -LiteralPath (Join-Path $variantDir "manifest.json"))
    )
}

function Assert-OptixManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$Version
    )

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.source_commit -ne $expectedSourceCommit) {
        throw "Bundled denoiser source commit mismatch for OptiX $Version`: expected $expectedSourceCommit, got $($manifest.source_commit)"
    }
    if ($manifest.optix_version -ne $Version) {
        throw "Bundled denoiser OptiX version mismatch: expected $Version, got $($manifest.optix_version)"
    }
    $expectedOptixCommit = $expectedOptixCommits[$Version]
    if ($manifest.optix_dev_commit -ne $expectedOptixCommit) {
        throw "Bundled denoiser OptiX SDK commit mismatch for OptiX $Version`: expected $expectedOptixCommit, got $($manifest.optix_dev_commit)"
    }
}

foreach ($version in $OptixVersions) {
    if (-not $expectedOptixCommits.ContainsKey($version)) {
        throw "Unsupported OptiX version '$version'. Expected one of: $($expectedOptixCommits.Keys -join ', ')"
    }
}

$alreadyInstalled = $true
foreach ($version in $OptixVersions) {
    if (-not (Test-OptixVariantInstalled -Version $version)) {
        $alreadyInstalled = $false
        break
    }
}
if ($alreadyInstalled) {
    foreach ($legacyName in @("Denoiser.exe", "manifest.json", "LICENSE")) {
        $legacyPath = Join-Path $vendorDir $legacyName
        if (Test-Path -LiteralPath $legacyPath) {
            Remove-Item -LiteralPath $legacyPath -Force
        }
    }
    Write-Host "Bundled OptiX denoiser variants already exist under: $vendorDir"
    exit 0
}

New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null
$downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hdu-optix-denoiser-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $downloadDir | Out-Null

try {
    $localZipDir = $env:HDU_OPTIX_DENOISER_ZIP_DIR
    foreach ($version in $OptixVersions) {
        $assetName = Get-OptixAssetName -Version $version
        $zipPath = Join-Path $downloadDir $assetName

        if ($localZipDir) {
            $localZip = Join-Path $localZipDir $assetName
            if (-not (Test-Path -LiteralPath $localZip)) {
                throw "HDU_OPTIX_DENOISER_ZIP_DIR is missing $assetName"
            }
            Copy-Item -LiteralPath $localZip -Destination $zipPath -Force
        }
        else {
            gh release download $Tag --repo $Repository --pattern $assetName --dir $downloadDir
        }

        if (-not (Test-Path -LiteralPath $zipPath)) {
            throw "Downloaded denoiser asset not found: $zipPath"
        }

        $extractDir = Join-Path $downloadDir "extract-$version"
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
        $foundExe = Get-ChildItem -LiteralPath $extractDir -Filter "Denoiser.exe" -Recurse | Select-Object -First 1
        if (-not $foundExe) {
            throw "Denoiser.exe was not found in $zipPath"
        }
        $foundManifest = Get-ChildItem -LiteralPath $extractDir -Filter "manifest.json" -Recurse | Select-Object -First 1
        if (-not $foundManifest) {
            throw "manifest.json was not found in $zipPath"
        }
        Assert-OptixManifest -ManifestPath $foundManifest.FullName -Version $version

        $variantDir = Get-OptixVariantDir -Version $version
        New-Item -ItemType Directory -Path $variantDir -Force | Out-Null
        Copy-Item -LiteralPath $foundExe.FullName -Destination (Join-Path $variantDir "Denoiser.exe") -Force
        Copy-Item -LiteralPath $foundManifest.FullName -Destination (Join-Path $variantDir "manifest.json") -Force
        Get-ChildItem -LiteralPath $extractDir -Filter "LICENSE" -Recurse |
            Select-Object -First 1 |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $variantDir "LICENSE") -Force
            }

        Write-Host "Bundled OptiX $version denoiser installed: $(Join-Path $variantDir 'Denoiser.exe')"
    }

    foreach ($legacyName in @("Denoiser.exe", "manifest.json", "LICENSE")) {
        $legacyPath = Join-Path $vendorDir $legacyName
        if (Test-Path -LiteralPath $legacyPath) {
            Remove-Item -LiteralPath $legacyPath -Force
        }
    }

    $summary = [ordered]@{
        release_repository = "https://github.com/$Repository"
        release_tag = $Tag
        source_commit = $expectedSourceCommit
        default_optix_version = "9.0"
        variants = $OptixVersions | ForEach-Object {
            [ordered]@{
                optix_version = $_
                optix_dev_commit = $expectedOptixCommits[$_]
                executable = "optix-$_/Denoiser.exe"
                manifest = "optix-$_/manifest.json"
            }
        }
    }
    $summary |
        ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $vendorDir "manifest.json") -Encoding utf8NoBOM

    Write-Host "Bundled OptiX denoiser variants installed under: $vendorDir"
}
finally {
    if (Test-Path -LiteralPath $downloadDir) {
        Remove-Item -LiteralPath $downloadDir -Recurse -Force
    }
}
