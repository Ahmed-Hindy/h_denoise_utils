param(
    [Parameter(Mandatory = $true)]
    [double]$NuitkaBuildSeconds,
    [Parameter(Mandatory = $true)]
    [double]$PyInstallerBuildSeconds,
    [int]$Iterations = 5
)

$ErrorActionPreference = "Stop"

function Invoke-TimedExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 60
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ExePath
    $startInfo.WorkingDirectory = Split-Path -Parent $ExePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Arguments = $Arguments -join " "

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $process.Start()) {
            throw "Could not start executable: $ExePath"
        }
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw "Executable timed out after $TimeoutSeconds seconds: $ExePath"
        }
        $stopwatch.Stop()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        if ($process.ExitCode -ne 0) {
            throw "Executable failed with exit code $($process.ExitCode): $ExePath`n$stdout`n$stderr"
        }
        return $stopwatch.Elapsed.TotalMilliseconds
    }
    finally {
        $process.Dispose()
    }
}

function Measure-Startup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [int]$Count
    )

    $measurements = for ($index = 0; $index -lt $Count; $index++) {
        Invoke-TimedExecutable -ExePath $ExePath -Arguments $Arguments
    }

    return [ordered]@{
        average_ms = [math]::Round(($measurements | Measure-Object -Average).Average, 2)
        minimum_ms = [math]::Round(($measurements | Measure-Object -Minimum).Minimum, 2)
        maximum_ms = [math]::Round(($measurements | Measure-Object -Maximum).Maximum, 2)
    }
}

function Get-PackageMetrics {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Directory,
        [Parameter(Mandatory = $true)]
        [string]$Archive,
        [Parameter(Mandatory = $true)]
        [double]$BuildSeconds,
        [Parameter(Mandatory = $true)]
        [int]$StartupIterations
    )

    if (-not (Test-Path -LiteralPath $Directory)) {
        throw "$Name package directory was not found: $Directory"
    }
    if (-not (Test-Path -LiteralPath $Archive)) {
        throw "$Name package archive was not found: $Archive"
    }

    $exePath = Join-Path $Directory "h-denoise.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "$Name executable was not found: $exePath"
    }

    $files = Get-ChildItem -LiteralPath $Directory -Recurse -File
    $directoryBytes = ($files | Measure-Object Length -Sum).Sum
    $archiveBytes = (Get-Item -LiteralPath $Archive).Length

    return [ordered]@{
        name = $Name
        directory_bytes = [long]$directoryBytes
        archive_bytes = [long]$archiveBytes
        file_count = $files.Count
        build_seconds = [math]::Round($BuildSeconds, 2)
        version_startup = Measure-Startup `
            -ExePath $exePath `
            -Arguments @("--version") `
            -Count $StartupIterations
        qt_startup = Measure-Startup `
            -ExePath $exePath `
            -Arguments @("--smoke-test", "--smoke-runtime", "none") `
            -Count $StartupIterations
    }
}

function Format-SizeMb {
    param([long]$Bytes)
    return "{0:N2} MB" -f ($Bytes / 1MB)
}

function Format-Delta {
    param(
        [double]$NuitkaValue,
        [double]$PyInstallerValue
    )

    if ($PyInstallerValue -eq 0) {
        return "n/a"
    }
    $percent = (($NuitkaValue - $PyInstallerValue) / $PyInstallerValue) * 100
    $sign = if ($percent -gt 0) { "+" } else { "" }
    return "$sign$([math]::Round($percent, 1))%"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distDir = Join-Path $repoRoot "dist"
$versionMatch = Select-String -Path (Join-Path $repoRoot "pyproject.toml") -Pattern '^version\s*=\s*"([^"]+)"' |
    Select-Object -First 1
if (-not $versionMatch) {
    throw "Could not read project version from pyproject.toml."
}
$version = $versionMatch.Matches[0].Groups[1].Value

$nuitka = Get-PackageMetrics `
    -Name "Nuitka" `
    -Directory (Join-Path $distDir "h-denoise") `
    -Archive (Join-Path $distDir "h-denoise-bundled-windows-x64-v$version.zip") `
    -BuildSeconds $NuitkaBuildSeconds `
    -StartupIterations $Iterations
$pyinstaller = Get-PackageMetrics `
    -Name "PyInstaller" `
    -Directory (Join-Path $distDir "h-denoise-pyinstaller") `
    -Archive (Join-Path $distDir "h-denoise-pyinstaller-windows-x64-v$version.zip") `
    -BuildSeconds $PyInstallerBuildSeconds `
    -StartupIterations $Iterations

$report = [ordered]@{
    version = $version
    python = "3.11"
    iterations = $Iterations
    nuitka = $nuitka
    pyinstaller = $pyinstaller
}
$reportPath = Join-Path $distDir "package-comparison.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8NoBOM

$summaryLines = @(
    "## Windows packaging comparison",
    "",
    "Both packages use Python 3.11, PySide6, OptiX 8.1/9.0/9.1, and OIDN 2.5.0 from the same commit.",
    "",
    "| Metric | Nuitka | PyInstaller | Nuitka delta |",
    "|---|---:|---:|---:|",
    "| ZIP size | $(Format-SizeMb $nuitka.archive_bytes) | $(Format-SizeMb $pyinstaller.archive_bytes) | $(Format-Delta $nuitka.archive_bytes $pyinstaller.archive_bytes) |",
    "| Unpacked size | $(Format-SizeMb $nuitka.directory_bytes) | $(Format-SizeMb $pyinstaller.directory_bytes) | $(Format-Delta $nuitka.directory_bytes $pyinstaller.directory_bytes) |",
    "| File count | $($nuitka.file_count) | $($pyinstaller.file_count) | $(Format-Delta $nuitka.file_count $pyinstaller.file_count) |",
    "| Build time | $($nuitka.build_seconds) s | $($pyinstaller.build_seconds) s | $(Format-Delta $nuitka.build_seconds $pyinstaller.build_seconds) |",
    "| ``--version`` startup | $($nuitka.version_startup.average_ms) ms | $($pyinstaller.version_startup.average_ms) ms | $(Format-Delta $nuitka.version_startup.average_ms $pyinstaller.version_startup.average_ms) |",
    "| Qt smoke startup | $($nuitka.qt_startup.average_ms) ms | $($pyinstaller.qt_startup.average_ms) ms | $(Format-Delta $nuitka.qt_startup.average_ms $pyinstaller.qt_startup.average_ms) |",
    "",
    "Startup values are averages of $Iterations runs. Lower is better for every metric."
)

$summaryLines | ForEach-Object { Write-Host $_ }
if ($env:GITHUB_STEP_SUMMARY) {
    Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value $summaryLines
}

Write-Host "Comparison report: $reportPath"
