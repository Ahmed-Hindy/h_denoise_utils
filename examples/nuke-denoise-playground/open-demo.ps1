[CmdletBinding()]
param(
    [ValidateSet("14.1v8", "15.0v1", "15.1v4", "17.0v3")]
    [string]$NukeVersion = "17.0v3",

    [ValidateSet("8.1", "9.0", "9.1")]
    [string]$OptixVersion = "9.1",

    [string]$InputExr = "G:\Projects\AYON_PROJECTS\Canyon_Run\sq001\sh001\publish\render\renderFxMain\v001\CanRun_sh001_renderFxMain_v001.exr"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$launcher = Join-Path $PSScriptRoot "launch-nuke-playground.ps1"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Playground launcher was not found: $launcher"
}

& $launcher `
    -NukeVersion $NukeVersion `
    -OptixVersion $OptixVersion `
    -InputExr $InputExr
