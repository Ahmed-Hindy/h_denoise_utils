[CmdletBinding()]
param(
    [ValidateSet("14.1v8", "15.0v1", "15.1v4", "17.0v3")]
    [string]$NukeVersion = "17.0v3",

    [ValidateSet("8.1", "9.0", "9.1")]
    [string]$OptixVersion = "9.1",

    [string]$InputExr = "G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr",

    [string]$BeautyLayer = "C",
    [string]$AlbedoLayer = "albedo",
    [string]$NormalLayer = "N",
    [string]$OutputDirectory = "",

    [switch]$PrepareOnly,
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-NukeExecutable {
    param([Parameter(Mandatory = $true)][string]$Version)

    $installRoot = "C:\Program Files\Nuke$Version"
    $binaryVersion = $Version -replace "v\d+$", ""
    $candidate = Join-Path $installRoot "Nuke$binaryVersion.exe"
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Nuke $Version was not found at: $candidate"
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

function Resolve-DenoisePluginDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Optix
    )

    $candidate = Join-Path $RepoRoot "build\nuke-optix-package\nuke-$Version\optix-$Optix\HDenoiseNodes"
    $requiredFiles = @(
        "HOptixDenoise.dll",
        "HOidnDenoise.dll",
        "HOidnBridge.exe",
        "OpenImageDenoise.dll",
        "OpenImageDenoise_core.dll",
        "OpenImageDenoise_device_cuda.dll",
        "manifest.json"
    )
    foreach ($name in $requiredFiles) {
        $path = Join-Path $candidate $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "The requested combined Nuke package is incomplete. Expected: $path"
        }
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

function Test-FoundryLicenseHealth {
    $logPath = "C:\ProgramData\The Foundry\RLM\log\foundry.log"
    if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
        return
    }

    $logItem = Get-Item -LiteralPath $logPath
    if ($logItem.LastWriteTime -lt (Get-Date).AddMinutes(-10)) {
        return
    }
    $recentLog = Get-Content -LiteralPath $logPath -Tail 40 -ErrorAction SilentlyContinue
    if ($recentLog -match "wrong host|does not run on virtual machines|initialization error") {
        Write-Warning "The current Foundry license server log reports an initialization failure. Nuke may not open until the license is repaired."
    }
}

$playgroundRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $playgroundRoot "..\..")).Path
$nukeScript = Join-Path $playgroundRoot "hdu-denoise-playground.nk"
$helperScript = Join-Path $playgroundRoot "hdu_playground.py"

if (-not (Test-Path -LiteralPath $InputExr -PathType Leaf)) {
    throw "Input EXR does not exist: $InputExr"
}
if (-not (Test-Path -LiteralPath $nukeScript -PathType Leaf)) {
    throw "Playground Nuke script is missing: $nukeScript"
}
if (-not (Test-Path -LiteralPath $helperScript -PathType Leaf)) {
    throw "Playground helper is missing: $helperScript"
}

# The .nk is a generated bootstrap, not a user workfile. A recovered autosave
# can contain an obsolete graph and prevent the current helper from rebuilding it.
$autosavePath = "$nukeScript.autosave"
if (Test-Path -LiteralPath $autosavePath -PathType Leaf) {
    Remove-Item -LiteralPath $autosavePath -Force
    Write-Host "Removed stale generated playground autosave: $autosavePath"
}

$nukeExe = Resolve-NukeExecutable -Version $NukeVersion
$pluginDir = Resolve-DenoisePluginDirectory `
    -RepoRoot $repoRoot `
    -Version $NukeVersion `
    -Optix $OptixVersion
$manifest = Get-Content -LiteralPath (Join-Path $pluginDir "manifest.json") -Raw |
    ConvertFrom-Json
if (-not $manifest.oidn_version) {
    throw "The selected Nuke package does not declare an OIDN runtime. Rebuild it with the current build script."
}
$oidnVersion = [string]$manifest.oidn_version
Test-FoundryLicenseHealth

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $sceneName = [IO.Path]::GetFileNameWithoutExtension($InputExr)
    $OutputDirectory = Join-Path $env:TEMP "hdu-nuke-playground\$sceneName"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$inputItem = Get-Item -LiteralPath $InputExr

$env:HDU_PLAYGROUND_INPUT = $inputItem.FullName
$env:HDU_PLAYGROUND_OUTPUT_DIR = $OutputDirectory
$env:HDU_PLAYGROUND_BEAUTY_LAYER = $BeautyLayer
$env:HDU_PLAYGROUND_ALBEDO_LAYER = $AlbedoLayer
$env:HDU_PLAYGROUND_NORMAL_LAYER = $NormalLayer
$env:HDU_PLAYGROUND_OPTIX_VERSION = $OptixVersion
$env:HDU_PLAYGROUND_OIDN_VERSION = $oidnVersion
$env:HDU_PLAYGROUND_NUKE_VERSION = $NukeVersion
$env:HDU_PLAYGROUND_REPO_ROOT = $repoRoot
$env:HDU_PLAYGROUND_NK = $nukeScript

# Let Nuke choose a cache size appropriate for the installed GPU and AIR/Blink.
Remove-Item -Path Env:CUDA_CACHE_MAXSIZE -ErrorAction SilentlyContinue

$nukePaths = @($pluginDir, $playgroundRoot)
if (-not [string]::IsNullOrWhiteSpace($env:NUKE_PATH)) {
    $nukePaths += $env:NUKE_PATH
}
$env:NUKE_PATH = $nukePaths -join [IO.Path]::PathSeparator

Write-Host ""
Write-Host "h_denoise_utils live Nuke playground"
Write-Host "  Nuke   : $nukeExe"
Write-Host "  Plugin : $pluginDir"
Write-Host "  OptiX  : $OptixVersion"
Write-Host "  OIDN   : $oidnVersion CUDA helper"
Write-Host "  EXR    : $($inputItem.FullName)"
Write-Host "  Output : $OutputDirectory"
Write-Host ""

if ($PrepareOnly) {
    exit 0
}

if ($ValidateOnly) {
    & $nukeExe -t $helperScript
    if ($LASTEXITCODE -ne 0) {
        throw "Nuke playground validation failed with code $LASTEXITCODE"
    }
    exit 0
}

Start-Process `
    -FilePath $nukeExe `
    -ArgumentList ('"{0}"' -f $nukeScript) `
    -WorkingDirectory $playgroundRoot
