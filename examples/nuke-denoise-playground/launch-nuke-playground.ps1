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

    [switch]$RefreshOidn,
    [switch]$SkipOidn,
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

function Resolve-OptixPluginDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$Optix
    )

    $candidate = Join-Path $RepoRoot "build\nuke-optix-package\nuke-$Version\optix-$Optix\HOptixDenoise"
    $dll = Join-Path $candidate "HOptixDenoise.dll"
    if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) {
        throw "The requested native plugin has not been built. Expected: $dll"
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

function Resolve-OidnExecutable {
    param([Parameter(Mandatory = $true)][string[]]$RepoRoots)

    foreach ($root in $RepoRoots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        $candidate = Join-Path $root "h_denoise_utils\vendor\oidn-denoiser\windows-x64\oidn-2.5.0\Denoiser.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    foreach ($root in $RepoRoots) {
        $buildRoot = Join-Path $root "build"
        if (-not (Test-Path -LiteralPath $buildRoot -PathType Container)) {
            continue
        }
        $candidate = Get-ChildItem -LiteralPath $buildRoot -Filter "Denoiser.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "[\\/]oidn-2\.5\.0[\\/]" } |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if ($null -ne $candidate) {
            return $candidate.FullName
        }
    }

    foreach ($root in $RepoRoots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        $candidate = Join-Path $root "h_denoise_utils\vendor\oidn-denoiser\windows-x64\oidn-2.4.1\Denoiser.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            Write-Warning "OIDN 2.5.0 was not found; falling back to OIDN 2.4.1."
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "No bundled OIDN Denoiser.exe was found. Build or fetch the OIDN 2.5.0 wrapper first."
}

function Test-FoundryLicenseHealth {
    $logPath = "C:\ProgramData\The Foundry\RLM\log\foundry.log"
    if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) {
        return
    }

    $recentLog = Get-Content -LiteralPath $logPath -Tail 40 -ErrorAction SilentlyContinue
    if ($recentLog -match "wrong host|does not run on virtual machines|initialization error") {
        Write-Warning "The Foundry RLM service is reachable, but its ISV server is not running. The current log says the license is bound to the wrong host or VM identity. Nuke will not open until that Foundry license is rehosted or renewed."
    }
}

function Invoke-OidnDenoise {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$Beauty,
        [Parameter(Mandatory = $true)][string]$Albedo,
        [Parameter(Mandatory = $true)][string]$Normal
    )

    $arguments = @(
        "-v", "1",
        "-multipart", $Source,
        "-o", $Destination,
        "-beauty-name", $Beauty,
        "-albedo-name", $Albedo,
        "-normal-name", $Normal
    )

    Write-Host "Running OIDN 2.5 playground render..."
    Write-Host "  Input : $Source"
    Write-Host "  Output: $Destination"
    Push-Location (Split-Path -Parent $Executable)
    try {
        & $Executable @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "OIDN exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "OIDN completed without creating: $Destination"
    }
}

$playgroundRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $playgroundRoot "..\..")).Path
$mainCheckout = "G:\Projects\Dev\Github\h_denoise_utils"
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

$nukeExe = Resolve-NukeExecutable -Version $NukeVersion
$pluginDir = Resolve-OptixPluginDirectory -RepoRoot $repoRoot -Version $NukeVersion -Optix $OptixVersion
$oidnExe = Resolve-OidnExecutable -RepoRoots @($repoRoot, $mainCheckout)
Test-FoundryLicenseHealth

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $sceneName = [IO.Path]::GetFileNameWithoutExtension($InputExr)
    $OutputDirectory = Join-Path $env:TEMP "hdu-nuke-playground\$sceneName"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path

$inputItem = Get-Item -LiteralPath $InputExr
$oidnOutput = Join-Path $OutputDirectory ($inputItem.BaseName + ".oidn-guided.exr")
$needsOidn = $RefreshOidn -or -not (Test-Path -LiteralPath $oidnOutput -PathType Leaf)
if (-not $needsOidn -and (Get-Item -LiteralPath $oidnOutput).LastWriteTimeUtc -lt $inputItem.LastWriteTimeUtc) {
    $needsOidn = $true
}
if (-not $SkipOidn -and $needsOidn) {
    Invoke-OidnDenoise `
        -Executable $oidnExe `
        -Source $inputItem.FullName `
        -Destination $oidnOutput `
        -Beauty $BeautyLayer `
        -Albedo $AlbedoLayer `
        -Normal $NormalLayer
}
elseif ($SkipOidn -and -not (Test-Path -LiteralPath $oidnOutput -PathType Leaf)) {
    throw "-SkipOidn was requested, but no cached OIDN output exists: $oidnOutput"
}

$env:HDU_PLAYGROUND_INPUT = $inputItem.FullName
$env:HDU_PLAYGROUND_OIDN_OUTPUT = $oidnOutput
$env:HDU_PLAYGROUND_OUTPUT_DIR = $OutputDirectory
$env:HDU_PLAYGROUND_BEAUTY_LAYER = $BeautyLayer
$env:HDU_PLAYGROUND_ALBEDO_LAYER = $AlbedoLayer
$env:HDU_PLAYGROUND_NORMAL_LAYER = $NormalLayer
$env:HDU_PLAYGROUND_OPTIX_VERSION = $OptixVersion
$env:HDU_PLAYGROUND_NUKE_VERSION = $NukeVersion
$env:HDU_PLAYGROUND_OIDN_EXE = $oidnExe
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
Write-Host "h_denoise_utils Nuke playground"
Write-Host "  Nuke   : $nukeExe"
Write-Host "  Plugin : $pluginDir"
Write-Host "  OptiX  : $OptixVersion"
Write-Host "  OIDN   : $oidnExe"
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

Start-Process -FilePath $nukeExe -ArgumentList ('"{0}"' -f $nukeScript) -WorkingDirectory $playgroundRoot
