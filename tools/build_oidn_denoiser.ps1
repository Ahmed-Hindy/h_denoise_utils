param(
    [string]$Version = "2.4.1",
    [string]$Configuration = "Release",
    [string]$Platform = "windows-x64",
    [string]$SourceCommit = "",
    [switch]$SkipOidnFetch
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

if ($Platform -ne "windows-x64") {
    throw "Unsupported OIDN denoiser platform '$Platform'. Expected windows-x64."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$nativeDir = Join-Path $repoRoot "native\oidn-denoiser"
$oidnRoot = Join-Path $repoRoot "h_denoise_utils\vendor\oidn\$Platform\oidn-$Version"
$bundleRoot = Join-Path $repoRoot "h_denoise_utils\vendor\oidn-denoiser\$Platform\oidn-$Version"
$buildRoot = Join-Path $repoRoot "build\oidn-denoiser\$Platform\oidn-$Version"
$distRoot = Join-Path $repoRoot "dist"

if (-not $SkipOidnFetch) {
    & (Join-Path $PSScriptRoot "fetch_oidn.ps1") -Version $Version -Platform $Platform
}

if (-not (Test-Path -LiteralPath (Join-Path $oidnRoot "include\OpenImageDenoise\oidn.hpp"))) {
    throw "OIDN headers were not found under $oidnRoot. Run tools/fetch_oidn.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $oidnRoot "lib\OpenImageDenoise.lib"))) {
    throw "OIDN import library was not found under $oidnRoot. Run tools/fetch_oidn.ps1 first."
}

if (-not $SourceCommit) {
    $SourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
}
$sourceShort = $SourceCommit.Substring(0, [Math]::Min(7, $SourceCommit.Length))

if (Test-Path -LiteralPath $buildRoot) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
if (Test-Path -LiteralPath $bundleRoot) {
    Remove-Item -LiteralPath $bundleRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $buildRoot, $bundleRoot, $distRoot -Force | Out-Null

Push-Location $nativeDir
try {
    uv run --native-tls --with conan conan profile detect --force
    uv run --native-tls --with conan conan install . --output-folder $buildRoot --build=missing -s build_type=$Configuration -s compiler.cppstd=20

    $toolchain = Join-Path $buildRoot "build\generators\conan_toolchain.cmake"
    if (-not (Test-Path -LiteralPath $toolchain)) {
        $toolchain = Join-Path $buildRoot "generators\conan_toolchain.cmake"
    }
    if (-not (Test-Path -LiteralPath $toolchain)) {
        throw "Conan toolchain file was not created under $buildRoot"
    }

    cmake -S $nativeDir -B $buildRoot -G "Visual Studio 17 2022" -A x64 `
        -DCMAKE_TOOLCHAIN_FILE="$toolchain" `
        -DOIDN_ROOT="$oidnRoot" `
        -DCMAKE_INSTALL_PREFIX="$bundleRoot"
    cmake --build $buildRoot --config $Configuration
    cmake --install $buildRoot --config $Configuration
}
finally {
    Pop-Location
}

$exePath = Join-Path $bundleRoot "Denoiser.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "OIDN Denoiser.exe was not created: $exePath"
}

Get-ChildItem -LiteralPath (Join-Path $oidnRoot "bin") -Filter "*.dll" |
    Copy-Item -Destination $bundleRoot -Force

foreach ($licenseName in @(
    "LICENSE.txt",
    "third-party-programs.txt",
    "third-party-programs-DPCPP.txt",
    "third-party-programs-oneTBB.txt"
)) {
    $licensePath = Join-Path $oidnRoot "doc\$licenseName"
    if (Test-Path -LiteralPath $licensePath) {
        Copy-Item -LiteralPath $licensePath -Destination (Join-Path $bundleRoot $licenseName) -Force
    }
}

$sha256 = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
$fileInfo = Get-Item -LiteralPath $exePath
$manifest = [ordered]@{
    name = "hdu-oidn-denoiser"
    executable = "Denoiser.exe"
    source_commit = $SourceCommit
    oidn_version = $Version
    oidn_release = "v$Version"
    platform = $Platform
    build_time_utc = (Get-Date).ToUniversalTime().ToString("o")
    sha256 = $sha256
    size = $fileInfo.Length
    contract = "optix-compatible-multipart-v1"
}
$manifest |
    ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $bundleRoot "manifest.json") -Encoding utf8NoBOM

$assetName = "oidn-denoiser-$Platform-oidn-$Version-$sourceShort.zip"
$assetPath = Join-Path $distRoot $assetName
if (Test-Path -LiteralPath $assetPath) {
    Remove-Item -LiteralPath $assetPath -Force
}
Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $assetPath -Force

Write-Host "OIDN denoiser bundle created: $bundleRoot"
Write-Host "OIDN denoiser asset created: $assetPath"
