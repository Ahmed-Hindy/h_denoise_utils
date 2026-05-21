param(
    [string]$Repository = "Ahmed-Hindy/h_denoise_utils",
    [string]$Tag = "optix-denoiser-v2026.05.21",
    [string[]]$OptixVersions = @("8.1", "9.0", "9.1"),
    [string]$Configuration = "Release",
    [switch]$AllowSourceKeyMismatch
)

$ErrorActionPreference = "Stop"

$platform = "windows-x64"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorDir = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\$platform"
$expectedOptixCommits = @{
    "8.1" = "50021ea0af6d41609a97777ceebbdf1e1d34efe7"
    "9.0" = "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
    "9.1" = "f1f6dd803f3159992d248178f6e09421c6eb8b6d"
}

function Get-OptixDenoiserSourceKey {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$OptixVersion,
        [Parameter(Mandatory = $true)][string]$OptixDevCommit,
        [Parameter(Mandatory = $true)][string]$Platform,
        [Parameter(Mandatory = $true)][string]$Configuration
    )

    $inputs = @(
        (Join-Path $RepoRoot "native\optix-denoiser\CMakeLists.txt"),
        (Join-Path $RepoRoot "native\optix-denoiser\conanfile.txt"),
        (Join-Path $RepoRoot "native\optix-denoiser\cmake"),
        (Join-Path $RepoRoot "native\optix-denoiser\src"),
        (Join-Path $RepoRoot "tools\build_optix_denoiser.ps1"),
        (Join-Path $RepoRoot "tools\build_optix_denoiser.sh")
    )
    $payload = [System.Collections.Generic.List[string]]::new()
    $payload.Add("optix_version=$OptixVersion")
    $payload.Add("optix_dev_commit=$OptixDevCommit")
    $payload.Add("platform=$Platform")
    $payload.Add("configuration=$Configuration")

    foreach ($inputPath in $inputs) {
        if (-not (Test-Path -LiteralPath $inputPath)) {
            throw "OptiX source-key input is missing: $inputPath"
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

function Get-OptixAssetName {
    param(
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$SourceKey
    )
    $shortKey = $SourceKey.Substring(0, [Math]::Min(12, $SourceKey.Length))
    return "optix-denoiser-$platform-optix-$Version-$shortKey.zip"
}

function Get-OptixVariantDir {
    param([Parameter(Mandatory = $true)][string]$Version)
    return Join-Path $vendorDir "optix-$Version"
}

function Assert-OptixManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$ExePath,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$ExpectedSourceKey
    )

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.name -ne "hdu-optix-denoiser") {
        throw "Bundled OptiX manifest name mismatch: expected hdu-optix-denoiser, got $($manifest.name)"
    }
    if ($manifest.executable -ne "Denoiser.exe") {
        throw "Bundled OptiX manifest executable mismatch: expected Denoiser.exe, got $($manifest.executable)"
    }
    if ($manifest.optix_version -ne $Version) {
        throw "Bundled OptiX version mismatch: expected $Version, got $($manifest.optix_version)"
    }
    if ($manifest.optix_dev_commit -ne $expectedOptixCommits[$Version]) {
        throw "Bundled OptiX SDK commit mismatch for $Version`: expected $($expectedOptixCommits[$Version]), got $($manifest.optix_dev_commit)"
    }
    if ($manifest.platform -ne $platform) {
        throw "Bundled OptiX platform mismatch: expected $platform, got $($manifest.platform)"
    }
    if ($manifest.contract -ne "optix-compatible-multipart-v1") {
        throw "Bundled OptiX contract mismatch: expected optix-compatible-multipart-v1, got $($manifest.contract)"
    }

    $actualHash = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash
    if ($actualHash -ne $manifest.sha256) {
        throw "Bundled OptiX executable hash mismatch: expected $($manifest.sha256), got $actualHash"
    }

    if (-not $AllowSourceKeyMismatch) {
        if (-not $manifest.source_key) {
            throw "Bundled OptiX manifest is missing source_key; rebuild it with the current build script."
        }
        if ($manifest.source_key -ne $ExpectedSourceKey) {
            throw "Bundled OptiX source_key mismatch for $Version`: expected $ExpectedSourceKey, got $($manifest.source_key)"
        }
    }
}

foreach ($version in $OptixVersions) {
    if (-not $expectedOptixCommits.ContainsKey($version)) {
        throw "Unsupported OptiX version '$version'. Expected one of: $($expectedOptixCommits.Keys -join ', ')"
    }
}

$expectedKeys = @{}
foreach ($version in $OptixVersions) {
    $expectedKeys[$version] = Get-OptixDenoiserSourceKey `
        -RepoRoot $repoRoot `
        -OptixVersion $version `
        -OptixDevCommit $expectedOptixCommits[$version] `
        -Platform $platform `
        -Configuration $Configuration
}

$alreadyInstalled = $true
foreach ($version in $OptixVersions) {
    $variantDir = Get-OptixVariantDir -Version $version
    $exePath = Join-Path $variantDir "Denoiser.exe"
    $manifestPath = Join-Path $variantDir "manifest.json"
    if (-not ((Test-Path -LiteralPath $exePath) -and (Test-Path -LiteralPath $manifestPath))) {
        $alreadyInstalled = $false
        break
    }
    try {
        Assert-OptixManifest -ManifestPath $manifestPath -ExePath $exePath -Version $version -ExpectedSourceKey $expectedKeys[$version]
    }
    catch {
        Write-Warning "Existing OptiX $version bundle failed validation: $($_.Exception.Message)"
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
        $assetName = Get-OptixAssetName -Version $version -SourceKey $expectedKeys[$version]
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
        if ($foundExe.DirectoryName -ne $foundManifest.DirectoryName) {
            throw "Denoiser.exe and manifest.json must be in the same bundle directory."
        }
        Assert-OptixManifest -ManifestPath $foundManifest.FullName -ExePath $foundExe.FullName -Version $version -ExpectedSourceKey $expectedKeys[$version]

        $variantDir = Get-OptixVariantDir -Version $version
        if (Test-Path -LiteralPath $variantDir) {
            Remove-Item -LiteralPath $variantDir -Recurse -Force
        }
        New-Item -ItemType Directory -Path $variantDir -Force | Out-Null
        Get-ChildItem -LiteralPath $foundManifest.DirectoryName -Force |
            Copy-Item -Destination $variantDir -Recurse -Force

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
        default_optix_version = "9.0"
        variants = $OptixVersions | ForEach-Object {
            [ordered]@{
                optix_version = $_
                optix_dev_commit = $expectedOptixCommits[$_]
                source_key = $expectedKeys[$_]
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
