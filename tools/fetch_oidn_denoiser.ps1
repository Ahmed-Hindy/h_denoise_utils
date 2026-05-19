param(
    [string]$Repository = "Ahmed-Hindy/h_denoise_utils",
    [string]$Tag = "",
    [string]$Version = "2.4.1",
    [string]$Platform = "windows-x64",
    [string]$SourceShortSha = ""
)

$ErrorActionPreference = "Stop"

if ($Platform -ne "windows-x64") {
    throw "Unsupported OIDN denoiser platform '$Platform'. Expected windows-x64."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "h_denoise_utils\vendor\oidn-denoiser\$Platform\oidn-$Version"

function Get-OidnDenoiserAssetPattern {
    if ($SourceShortSha) {
        return "oidn-denoiser-$Platform-oidn-$Version-$SourceShortSha.zip"
    }
    return "oidn-denoiser-$Platform-oidn-$Version-*.zip"
}

function Resolve-OidnDenoiserReleaseTag {
    param([Parameter(Mandatory = $true)][string]$Pattern)

    $releaseJson = gh release list --repo $Repository --exclude-drafts --exclude-pre-releases --limit 50 --json tagName
    $releases = $releaseJson | ConvertFrom-Json
    foreach ($release in $releases) {
        $candidateTag = [string]$release.tagName
        if (-not $candidateTag.StartsWith("v")) {
            continue
        }

        $viewJson = gh release view $candidateTag --repo $Repository --json assets
        $view = $viewJson | ConvertFrom-Json
        $asset = $view.assets | Where-Object { $_.name -like $Pattern } | Select-Object -First 1
        if ($asset) {
            return $candidateTag
        }
    }

    throw "No non-draft app release in $Repository contains an OIDN denoiser asset matching $Pattern. Pass -Tag vX.Y.Z or set HDU_OIDN_DENOISER_ZIP_DIR."
}

function Test-OidnDenoiserInstalled {
    return (
        (Test-Path -LiteralPath (Join-Path $vendorDir "Denoiser.exe")) -and
        (Test-Path -LiteralPath (Join-Path $vendorDir "manifest.json"))
    )
}

if (Test-OidnDenoiserInstalled) {
    Write-Host "Bundled OIDN denoiser already exists: $(Join-Path $vendorDir 'Denoiser.exe')"
    exit 0
}

$downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hdu-oidn-denoiser-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $downloadDir | Out-Null

try {
    $zipPath = $null
    $localZipDir = $env:HDU_OIDN_DENOISER_ZIP_DIR
    $pattern = Get-OidnDenoiserAssetPattern
    if ($localZipDir) {
        $localZip = Get-ChildItem -LiteralPath $localZipDir -Filter $pattern | Select-Object -First 1
        if (-not $localZip) {
            throw "HDU_OIDN_DENOISER_ZIP_DIR is missing $pattern"
        }
        $zipPath = Join-Path $downloadDir $localZip.Name
        Copy-Item -LiteralPath $localZip.FullName -Destination $zipPath -Force
    }
    else {
        if (-not $Tag) {
            $Tag = Resolve-OidnDenoiserReleaseTag -Pattern $pattern
            Write-Host "Resolved OIDN denoiser release tag: $Tag"
        }
        gh release download $Tag --repo $Repository --pattern $pattern --dir $downloadDir
        $downloaded = Get-ChildItem -LiteralPath $downloadDir -Filter $pattern | Select-Object -First 1
        if (-not $downloaded) {
            throw "Downloaded OIDN denoiser asset not found for pattern $pattern"
        }
        $zipPath = $downloaded.FullName
    }

    $extractDir = Join-Path $downloadDir "extract"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $foundExe = Get-ChildItem -LiteralPath $extractDir -Filter "Denoiser.exe" -Recurse | Select-Object -First 1
    if (-not $foundExe) {
        throw "Denoiser.exe was not found in $zipPath"
    }
    $foundManifest = Get-ChildItem -LiteralPath $extractDir -Filter "manifest.json" -Recurse | Select-Object -First 1
    if (-not $foundManifest) {
        throw "manifest.json was not found in $zipPath"
    }

    New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null
    Get-ChildItem -LiteralPath $extractDir -File -Recurse |
        Copy-Item -Destination $vendorDir -Force

    Write-Host "Bundled OIDN denoiser installed: $(Join-Path $vendorDir 'Denoiser.exe')"
}
finally {
    if (Test-Path -LiteralPath $downloadDir) {
        Remove-Item -LiteralPath $downloadDir -Recurse -Force
    }
}
