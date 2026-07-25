param(
    [string]$Repository = "Ahmed-Hindy/h_denoise_utils",
    [string]$Tag = "",
    [string]$Version = "2.5.0",
    [string]$Platform = "windows-x64",
    [string]$SourceShortSha = "",
    [string]$Configuration = "Release",
    [switch]$AllowSourceKeyMismatch,
    [switch]$CopyAssetToDist
)

$ErrorActionPreference = "Stop"

if ($Platform -ne "windows-x64") {
    throw "Unsupported OIDN denoiser platform '$Platform'. Expected windows-x64."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "h_denoise_utils\vendor\oidn-denoiser\$Platform\oidn-$Version"
$distRoot = Join-Path $repoRoot "dist"

function Get-OidnDenoiserSourceKey {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Platform,
        [Parameter(Mandatory = $true)][string]$Configuration
    )

    $inputs = @(
        (Join-Path $RepoRoot "native\oidn-denoiser"),
        (Join-Path $RepoRoot "tools\build_oidn_denoiser.ps1"),
        (Join-Path $RepoRoot "tools\fetch_oidn.ps1")
    )
    $payload = [System.Collections.Generic.List[string]]::new()
    $payload.Add("version=$Version")
    $payload.Add("platform=$Platform")
    $payload.Add("configuration=$Configuration")

    foreach ($inputPath in $inputs) {
        if (-not (Test-Path -LiteralPath $inputPath)) {
            throw "OIDN source-key input is missing: $inputPath"
        }

        $item = Get-Item -LiteralPath $inputPath
        $files = if ($item.PSIsContainer) {
            Get-ChildItem -LiteralPath $item.FullName -File -Recurse
        }
        else {
            @($item)
        }

        foreach ($file in ($files | Sort-Object FullName)) {
            $relative = [System.IO.Path]::GetRelativePath($RepoRoot, $file.FullName).Replace("\", "/")
            $fileHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $payload.Add("$relative=$fileHash")
        }
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($payload -join "`n"))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha.ComputeHash($bytes)
        return -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
    }
    finally {
        $sha.Dispose()
    }
}

$expectedSourceKey = Get-OidnDenoiserSourceKey -RepoRoot $repoRoot -Version $Version -Platform $Platform -Configuration $Configuration
if (-not $SourceShortSha) {
    $SourceShortSha = $expectedSourceKey.Substring(0, [Math]::Min(12, $expectedSourceKey.Length))
}

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

function Assert-OidnDenoiserManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$ExePath
    )

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.name -ne "hdu-oidn-denoiser") {
        throw "OIDN denoiser manifest name mismatch: expected hdu-oidn-denoiser, got $($manifest.name)"
    }
    if ($manifest.executable -ne "Denoiser.exe") {
        throw "OIDN denoiser manifest executable mismatch: expected Denoiser.exe, got $($manifest.executable)"
    }
    if ($manifest.oidn_version -ne $Version) {
        throw "OIDN denoiser manifest version mismatch: expected $Version, got $($manifest.oidn_version)"
    }
    if ($manifest.platform -ne $Platform) {
        throw "OIDN denoiser manifest platform mismatch: expected $Platform, got $($manifest.platform)"
    }
    if ($manifest.contract -ne "optix-compatible-multipart-v1") {
        throw "OIDN denoiser manifest contract mismatch: expected optix-compatible-multipart-v1, got $($manifest.contract)"
    }
    if (-not $manifest.sha256) {
        throw "OIDN denoiser manifest is missing sha256"
    }

    $actualHash = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash
    if ($actualHash -ne $manifest.sha256) {
        throw "OIDN denoiser executable hash mismatch: expected $($manifest.sha256), got $actualHash"
    }

    if (-not $AllowSourceKeyMismatch) {
        if (-not $manifest.source_key) {
            throw "OIDN denoiser manifest is missing source_key; rebuild it with the current build script."
        }
        if ($manifest.source_key -ne $expectedSourceKey) {
            throw "OIDN denoiser source_key mismatch: expected $expectedSourceKey, got $($manifest.source_key)"
        }
    }
}

if (Test-OidnDenoiserInstalled) {
    Assert-OidnDenoiserManifest `
        -ManifestPath (Join-Path $vendorDir "manifest.json") `
        -ExePath (Join-Path $vendorDir "Denoiser.exe")
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
    if ($foundExe.DirectoryName -ne $foundManifest.DirectoryName) {
        throw "Denoiser.exe and manifest.json must be in the same bundle directory."
    }
    Assert-OidnDenoiserManifest -ManifestPath $foundManifest.FullName -ExePath $foundExe.FullName

    if (Test-Path -LiteralPath $vendorDir) {
        Remove-Item -LiteralPath $vendorDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $vendorDir -Force | Out-Null
    Get-ChildItem -LiteralPath $foundManifest.DirectoryName -Force |
        Copy-Item -Destination $vendorDir -Recurse -Force

    if ($CopyAssetToDist) {
        New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
        Copy-Item -LiteralPath $zipPath -Destination (Join-Path $distRoot (Split-Path $zipPath -Leaf)) -Force
    }

    Write-Host "Bundled OIDN denoiser installed: $(Join-Path $vendorDir 'Denoiser.exe')"
}
finally {
    if (Test-Path -LiteralPath $downloadDir) {
        Remove-Item -LiteralPath $downloadDir -Recurse -Force
    }
}
