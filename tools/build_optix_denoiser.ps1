param(
    [ValidateSet("8.1", "9.0", "9.1")]
    [string]$OptixVersion = "9.0",
    [string]$Configuration = "Release",
    [string]$Platform = "windows-x64",
    [string]$OptixDevCommit = "",
    [switch]$SkipOptixFetch
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$optixSdkCommits = @{
    "8.1" = "50021ea0af6d41609a97777ceebbdf1e1d34efe7"
    "9.0" = "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
    "9.1" = "f1f6dd803f3159992d248178f6e09421c6eb8b6d"
}

if ($Platform -ne "windows-x64") {
    throw "Unsupported OptiX denoiser platform '$Platform'. Expected windows-x64."
}
if (-not $OptixDevCommit) {
    $OptixDevCommit = $optixSdkCommits[$OptixVersion]
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$nativeDir = Join-Path $repoRoot "native\optix-denoiser"
$optixDir = Join-Path $nativeDir "contrib\optix"
$buildRoot = Join-Path $repoRoot "build\optix-denoiser\$Platform\optix-$OptixVersion"
$bundleRoot = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\$Platform\optix-$OptixVersion"
$distRoot = Join-Path $repoRoot "dist"

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

function Sync-OptixDev {
    param(
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Commit
    )

    if (Test-Path -LiteralPath (Join-Path $Destination ".git")) {
        git -C $Destination fetch origin $Commit
        git -C $Destination checkout --force $Commit
        git -C $Destination clean -fdx
    }
    else {
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        git clone --no-checkout https://github.com/NVIDIA/optix-dev.git $Destination
        git -C $Destination fetch origin $Commit
        git -C $Destination checkout --force $Commit
    }

    if (-not (Test-Path -LiteralPath (Join-Path $Destination "include\optix.h"))) {
        throw "OptiX SDK checkout is missing include\optix.h: $Destination"
    }
}

if (-not $SkipOptixFetch) {
    Sync-OptixDev -Destination $optixDir -Commit $OptixDevCommit
}

if (-not (Test-Path -LiteralPath (Join-Path $optixDir "include\optix.h"))) {
    throw "OptiX SDK headers were not found under $optixDir. Run without -SkipOptixFetch first."
}

$sourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$sourceKey = Get-OptixDenoiserSourceKey `
    -RepoRoot $repoRoot `
    -OptixVersion $OptixVersion `
    -OptixDevCommit $OptixDevCommit `
    -Platform $Platform `
    -Configuration $Configuration
$sourceKeyShort = $sourceKey.Substring(0, [Math]::Min(12, $sourceKey.Length))

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
    uv run --native-tls --with conan conan install . --output-folder $buildRoot --build=missing -s build_type=$Configuration -s compiler.cppstd=20 -o openimageio/*:with_ffmpeg=False

    $toolchain = Join-Path $buildRoot "build\generators\conan_toolchain.cmake"
    if (-not (Test-Path -LiteralPath $toolchain)) {
        $toolchain = Join-Path $buildRoot "generators\conan_toolchain.cmake"
    }
    if (-not (Test-Path -LiteralPath $toolchain)) {
        throw "Conan toolchain file was not created under $buildRoot"
    }

    cmake -S $nativeDir -B $buildRoot -G "Visual Studio 17 2022" -A x64 `
        -DCMAKE_TOOLCHAIN_FILE="$toolchain" `
        -DCMAKE_POLICY_DEFAULT_CMP0091=NEW `
        -DCMAKE_INSTALL_PREFIX="$bundleRoot"
    cmake --build $buildRoot --config $Configuration --target install
}
finally {
    Pop-Location
}

$installedExe = Join-Path $bundleRoot "bin\Denoiser.exe"
$exePath = Join-Path $bundleRoot "Denoiser.exe"
if ((Test-Path -LiteralPath $installedExe) -and -not (Test-Path -LiteralPath $exePath)) {
    Move-Item -LiteralPath $installedExe -Destination $exePath
}
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "OptiX Denoiser.exe was not created: $exePath"
}

$licensePath = Join-Path $nativeDir "LICENSE"
if (Test-Path -LiteralPath $licensePath) {
    Copy-Item -LiteralPath $licensePath -Destination (Join-Path $bundleRoot "LICENSE") -Force
}

$sha256 = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
$fileInfo = Get-Item -LiteralPath $exePath
$manifest = [ordered]@{
    name = "hdu-optix-denoiser"
    executable = "Denoiser.exe"
    source_commit = $sourceCommit
    source_key = $sourceKey
    optix_version = $OptixVersion
    optix_dev_commit = $OptixDevCommit
    platform = $Platform
    build_time_utc = (Get-Date).ToUniversalTime().ToString("o")
    sha256 = $sha256
    size = $fileInfo.Length
    contract = "optix-compatible-multipart-v1"
}
$manifest |
    ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $bundleRoot "manifest.json") -Encoding utf8NoBOM

$assetName = "optix-denoiser-$Platform-optix-$OptixVersion-$sourceKeyShort.zip"
$assetPath = Join-Path $distRoot $assetName
if (Test-Path -LiteralPath $assetPath) {
    Remove-Item -LiteralPath $assetPath -Force
}
Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $assetPath -Force

Write-Host "OptiX denoiser bundle created: $bundleRoot"
Write-Host "OptiX denoiser asset created: $assetPath"
