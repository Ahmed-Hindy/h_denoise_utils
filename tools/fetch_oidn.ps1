param(
    [string]$Repository = "RenderKit/oidn",
    [string]$Version = "2.4.1",
    [string]$Tag = "v2.4.1",
    [string]$AssetName = "",
    [string]$Platform = "windows-x64"
)

$ErrorActionPreference = "Stop"

if ($Platform -ne "windows-x64") {
    throw "Unsupported OIDN platform '$Platform'. This fetcher currently supports windows-x64."
}

if (-not $AssetName) {
    $AssetName = "oidn-$Version.x64.windows.zip"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vendorRoot = Join-Path $repoRoot "h_denoise_utils\vendor\oidn\$Platform"
$installDir = Join-Path $vendorRoot "oidn-$Version"

function Test-OidnInstalled {
    return (
        (Test-Path -LiteralPath (Join-Path $installDir "bin\oidnDenoise.exe")) -and
        (Test-Path -LiteralPath (Join-Path $installDir "bin\OpenImageDenoise.dll")) -and
        (Test-Path -LiteralPath (Join-Path $installDir "bin\OpenImageDenoise_core.dll")) -and
        (Test-Path -LiteralPath (Join-Path $installDir "doc\LICENSE.txt"))
    )
}

function Assert-OidnPackage {
    param([Parameter(Mandatory = $true)][string]$Root)

    $required = @(
        "bin\oidnDenoise.exe",
        "bin\OpenImageDenoise.dll",
        "bin\OpenImageDenoise_core.dll",
        "doc\LICENSE.txt",
        "include\OpenImageDenoise\oidn.h",
        "lib\OpenImageDenoise.lib"
    )
    foreach ($rel in $required) {
        $path = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $path)) {
            throw "OIDN package is missing required file: $rel"
        }
    }
}

if (Test-OidnInstalled) {
    Write-Host "Bundled OIDN runtime already exists under: $installDir"
    exit 0
}

New-Item -ItemType Directory -Path $vendorRoot -Force | Out-Null
$downloadDir = Join-Path ([System.IO.Path]::GetTempPath()) ("hdu-oidn-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $downloadDir | Out-Null

try {
    $zipPath = Join-Path $downloadDir $AssetName
    $localZipDir = $env:HDU_OIDN_ZIP_DIR

    if ($localZipDir) {
        $localZip = Join-Path $localZipDir $AssetName
        if (-not (Test-Path -LiteralPath $localZip)) {
            throw "HDU_OIDN_ZIP_DIR is missing $AssetName"
        }
        Copy-Item -LiteralPath $localZip -Destination $zipPath -Force
    }
    else {
        $url = "https://github.com/$Repository/releases/download/$Tag/$AssetName"
        Write-Host "Downloading OIDN SDK from: $url"
        Invoke-WebRequest -Uri $url -OutFile $zipPath -Headers @{ "User-Agent" = "h_denoise_utils" }
    }

    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Downloaded OIDN asset not found: $zipPath"
    }

    $extractDir = Join-Path $downloadDir "extract"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $packageRoot = Get-ChildItem -LiteralPath $extractDir -Directory |
        Where-Object { $_.Name -eq "oidn-$Version.x64.windows" -or $_.Name -eq "oidn-$Version" } |
        Select-Object -First 1
    if (-not $packageRoot) {
        throw "Could not find extracted OIDN package root in $AssetName"
    }

    Assert-OidnPackage -Root $packageRoot.FullName

    if (Test-Path -LiteralPath $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Get-ChildItem -LiteralPath $packageRoot.FullName -Force |
        Copy-Item -Destination $installDir -Recurse -Force

    $summary = [ordered]@{
        release_repository = "https://github.com/$Repository"
        release_tag = $Tag
        version = $Version
        platform = $Platform
        asset = $AssetName
        executable = "bin/oidnDenoise.exe"
        license = "doc/LICENSE.txt"
        note = "Official oidnDenoise is a sample app; production multipart EXR support uses the HDU OIDN Denoiser.exe wrapper."
    }
    $summary |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $installDir "manifest.json") -Encoding utf8NoBOM

    Write-Host "Bundled OIDN runtime installed: $(Join-Path $installDir 'bin\oidnDenoise.exe')"
}
finally {
    if (Test-Path -LiteralPath $downloadDir) {
        Remove-Item -LiteralPath $downloadDir -Recurse -Force
    }
}
