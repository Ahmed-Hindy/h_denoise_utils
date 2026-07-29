param(
    [ValidateSet("8.1", "9.0", "9.1")]
    [string]$OptixVersion = "9.1",
    [string]$NukeVersion = "17.0v3",
    [string]$NukeRoot = "",
    [ValidateSet("Release", "RelWithDebInfo", "Debug")]
    [string]$Configuration = "Release",
    [switch]$Stub,
    [switch]$SkipDependencyFetch,
    [switch]$SkipValidation
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

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command $($Arguments -join ' ')"
    }
}

function Import-VisualStudioEnvironment {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) {
        throw "Visual Studio Installer's vswhere.exe was not found."
    }

    $installationPath = (& $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath).Trim()
    if (-not $installationPath) {
        throw "Visual Studio with the C++ x64 toolchain was not found."
    }

    $vsDevCmd = Join-Path $installationPath "Common7\Tools\VsDevCmd.bat"
    $command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && set' -f $vsDevCmd
    $environmentLines = & $env:ComSpec /d /s /c $command
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize the Visual Studio build environment."
    }

    foreach ($line in $environmentLines) {
        if ($line -match '^([^=]+)=(.*)$') {
            Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2]
        }
    }
}

function Resolve-Executable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string[]]$Fallbacks = @()
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    foreach ($fallback in $Fallbacks) {
        if (Test-Path -LiteralPath $fallback) {
            return $fallback
        }
    }
    throw "Required executable was not found: $Name"
}

function Sync-OptixHeaders {
    param(
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Commit
    )

    if (-not (Test-Path -LiteralPath (Join-Path $Destination ".git"))) {
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Invoke-Native -Command git -Arguments @(
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            "https://github.com/NVIDIA/optix-dev.git",
            $Destination
        )
    }

    Invoke-Native -Command git -Arguments @(
        "-C", $Destination, "fetch", "--depth", "1", "origin", $Commit
    )
    Invoke-Native -Command git -Arguments @(
        "-C", $Destination, "checkout", "--force", $Commit
    )
    if (-not (Test-Path -LiteralPath (Join-Path $Destination "include\optix.h"))) {
        throw "OptiX headers were not found under $Destination."
    }
}

function Sync-CudaDriverHeaders {
    param([Parameter(Mandatory = $true)][string]$DependencyRoot)

    $manifestUrl = "https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.9.1.json"
    $manifest = Invoke-RestMethod -UseBasicParsing -Uri $manifestUrl
    $windowsPackage = $manifest.cuda_cudart.PSObject.Properties["windows-x86_64"].Value
    if (-not $windowsPackage) {
        throw "The CUDA redistributable manifest has no Windows x86_64 CUDART package."
    }

    $archiveName = Split-Path -Leaf $windowsPackage.relative_path
    $archivePath = Join-Path $DependencyRoot $archiveName
    $extractRoot = Join-Path $DependencyRoot ([IO.Path]::GetFileNameWithoutExtension($archiveName))
    $archiveUrl = "https://developer.download.nvidia.com/compute/cuda/redist/$($windowsPackage.relative_path)"

    if (-not (Test-Path -LiteralPath $archivePath)) {
        New-Item -ItemType Directory -Path $DependencyRoot -Force | Out-Null
        Write-Host "Downloading minimal CUDA driver headers and import library..."
        Invoke-WebRequest -UseBasicParsing -Uri $archiveUrl -OutFile $archivePath
    }

    if ($windowsPackage.sha256) {
        $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $windowsPackage.sha256.ToLowerInvariant()) {
            throw "CUDA redistributable SHA-256 mismatch: $archivePath"
        }
    }

    if (-not (Test-Path -LiteralPath $extractRoot)) {
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot
    }

    $cudaRoot = Get-ChildItem -LiteralPath $extractRoot -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName "include\cuda.h")) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "lib\x64\cuda.lib"))
        } |
        Select-Object -First 1
    if (-not $cudaRoot) {
        throw "CUDA driver headers and cuda.lib were not found under $extractRoot."
    }
    return $cudaRoot.FullName
}

if ($env:OS -ne "Windows_NT") {
    throw "This script currently builds the Windows Nuke plugin only."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectFile = Join-Path $repoRoot "pyproject.toml"
$versionMatch = [regex]::Match(
    (Get-Content -LiteralPath $projectFile -Raw),
    '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "Could not read the project version from pyproject.toml."
}
$projectVersion = $versionMatch.Groups[1].Value

$nukeBinaryVersion = [regex]::Match($NukeVersion, '^\d+\.\d+').Value
if (-not $nukeBinaryVersion) {
    throw "NukeVersion must start with a major.minor version, for example 17.0v3."
}
if (-not $NukeRoot) {
    $NukeRoot = "C:\Program Files\Nuke$NukeVersion"
}
$nukeExecutable = Join-Path $NukeRoot "Nuke$nukeBinaryVersion.exe"
if (-not (Test-Path -LiteralPath (Join-Path $NukeRoot "include\DDImage\PlanarIop.h"))) {
    throw "Nuke NDK headers were not found under $NukeRoot."
}
if (-not (Test-Path -LiteralPath $nukeExecutable)) {
    throw "Nuke executable was not found: $nukeExecutable"
}

Import-VisualStudioEnvironment
$cmake = Resolve-Executable cmake.exe @(
    "C:\Program Files\CMake\bin\cmake.exe",
    "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
)
$ninja = Resolve-Executable ninja.exe @(
    "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe",
    "C:\Program Files\JetBrains\CLion 2026.2\bin\ninja\win\x64\ninja.exe"
)
$cl = (Resolve-Executable cl.exe).Replace("\", "/")
$rc = (Resolve-Executable rc.exe).Replace("\", "/")
$ninjaForCMake = $ninja.Replace("\", "/")
$env:PATH = "$(Split-Path -Parent $ninja);$env:PATH"

$dependencyRoot = Join-Path $repoRoot "build\deps"
$optixRoot = Join-Path $dependencyRoot "optix-$OptixVersion"
$cudaRoot = ""
if (-not $Stub) {
    if (-not $SkipDependencyFetch) {
        Sync-OptixHeaders -Destination $optixRoot -Commit $optixSdkCommits[$OptixVersion]
        $cudaRoot = Sync-CudaDriverHeaders -DependencyRoot (Join-Path $dependencyRoot "cuda-redist")
    }
    else {
        $cudaRoot = Get-ChildItem -LiteralPath (Join-Path $dependencyRoot "cuda-redist") -Directory -Recurse |
            Where-Object {
                (Test-Path -LiteralPath (Join-Path $_.FullName "include\cuda.h")) -and
                (Test-Path -LiteralPath (Join-Path $_.FullName "lib\x64\cuda.lib"))
            } |
            Select-Object -First 1 -ExpandProperty FullName
    }

    if (-not (Test-Path -LiteralPath (Join-Path $optixRoot "include\optix.h"))) {
        throw "OptiX headers are missing. Run without -SkipDependencyFetch."
    }
    if (-not $cudaRoot) {
        throw "CUDA driver headers are missing. Run without -SkipDependencyFetch."
    }
}

$variant = if ($Stub) { "stub" } else { "optix-$OptixVersion" }
$buildRoot = Join-Path $repoRoot "build\nuke-optix\nuke-$NukeVersion\$variant"
$packageRoot = Join-Path $repoRoot "build\nuke-optix-package\nuke-$NukeVersion\$variant"
$distRoot = Join-Path $repoRoot "dist"
foreach ($path in @($buildRoot, $packageRoot)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $buildRoot, $packageRoot, $distRoot -Force | Out-Null

$configureArguments = @(
    "--fresh",
    "-S", (Join-Path $repoRoot "native\nuke-optix"),
    "-B", $buildRoot,
    "-G", "Ninja",
    "-DCMAKE_BUILD_TYPE=$Configuration",
    "-DCMAKE_MAKE_PROGRAM=$ninjaForCMake",
    "-DCMAKE_CXX_COMPILER=$cl",
    "-DCMAKE_RC_COMPILER=$rc",
    "-DNUKE_VERSION=$NukeVersion",
    "-DNUKE_ROOT=$NukeRoot",
    "-DHDU_VERSION=$projectVersion",
    "-DHDU_NUKE_STUB_OPTIX=$($Stub.IsPresent)"
)
if (-not $Stub) {
    $configureArguments += "-DOPTIX_ROOT=$optixRoot"
    $configureArguments += "-DCUDA_REDIST_ROOT=$cudaRoot"
}

Invoke-Native -Command $cmake -Arguments $configureArguments
Invoke-Native -Command $cmake -Arguments @(
    "--build", $buildRoot, "--config", $Configuration
)
Invoke-Native -Command $cmake -Arguments @(
    "--install", $buildRoot, "--prefix", $packageRoot
)

$pluginRoot = Join-Path $packageRoot "HOptixDenoise"
$pluginBinary = Join-Path $pluginRoot "HOptixDenoise.dll"
if (-not (Test-Path -LiteralPath $pluginBinary)) {
    throw "Nuke plugin was not created: $pluginBinary"
}

$sourceCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$manifest = [ordered]@{
    name = "HOptixDenoise"
    version = $projectVersion
    source_commit = $sourceCommit
    nuke_version = $NukeVersion
    nuke_binary_version = $nukeBinaryVersion
    optix_version = if ($Stub) { $null } else { $OptixVersion }
    optix_dev_commit = if ($Stub) { $null } else { $optixSdkCommits[$OptixVersion] }
    platform = "windows-x64"
    build_configuration = $Configuration
    stub = $Stub.IsPresent
    sha256 = (Get-FileHash -LiteralPath $pluginBinary -Algorithm SHA256).Hash.ToLowerInvariant()
    size = (Get-Item -LiteralPath $pluginBinary).Length
}
$manifestPath = Join-Path $pluginRoot "manifest.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
    $manifestPath,
    $manifestJson,
    [Text.UTF8Encoding]::new($false)
)

if (-not $SkipValidation) {
    $previousNukePath = $env:NUKE_PATH
    try {
        $env:NUKE_PATH = $pluginRoot
        Invoke-Native -Command $nukeExecutable -Arguments @(
            "-t", (Join-Path $repoRoot "tools\validate_nuke_optix_plugin.py")
        )
    }
    finally {
        $env:NUKE_PATH = $previousNukePath
    }
}

$assetName = if ($Stub) {
    "h-denoise-nuke-$nukeBinaryVersion-windows-x64-stub-v$projectVersion.zip"
}
else {
    "h-denoise-nuke-$nukeBinaryVersion-windows-x64-optix-$OptixVersion-v$projectVersion.zip"
}
$assetPath = Join-Path $distRoot $assetName
if (Test-Path -LiteralPath $assetPath) {
    Remove-Item -LiteralPath $assetPath -Force
}
Compress-Archive -LiteralPath $pluginRoot -DestinationPath $assetPath -Force

Write-Host "Nuke plugin package: $pluginRoot"
Write-Host "Nuke plugin asset:   $assetPath"
