param(
    [string]$Variant = ""
)

$ErrorActionPreference = "Stop"

function Invoke-FrozenExecutableCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath,
        [Parameter(Mandatory = $true)]
        [string]$CheckName,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 60
    )

    if (-not (Test-Path -LiteralPath $ExePath)) {
        throw "Expected executable was not found for $CheckName`: $ExePath"
    }

    $workingDirectory = Split-Path -Parent $ExePath
    $stamp = [Guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path ([System.IO.Path]::GetTempPath()) "hdu-$CheckName-$stamp.out"
    $stderrPath = Join-Path ([System.IO.Path]::GetTempPath()) "hdu-$CheckName-$stamp.err"

    try {
        $process = Start-Process `
            -FilePath $ExePath `
            -ArgumentList $Arguments `
            -WorkingDirectory $workingDirectory `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -WindowStyle Hidden

        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while (-not $process.HasExited) {
            if ((Get-Date) -ge $deadline) {
                try {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                }
                catch {
                    # The process may have exited between the timeout check and Stop-Process.
                }
                throw "$CheckName timed out after $TimeoutSeconds seconds: $ExePath $($Arguments -join ' ')"
            }
            Start-Sleep -Milliseconds 250
            $process.Refresh()
        }

        $stdout = ""
        if (Test-Path -LiteralPath $stdoutPath) {
            $stdout = [string](Get-Content -LiteralPath $stdoutPath -Raw)
        }
        $stderr = ""
        if (Test-Path -LiteralPath $stderrPath) {
            $stderr = [string](Get-Content -LiteralPath $stderrPath -Raw)
        }

        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            Write-Host $stdout.TrimEnd()
        }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Host $stderr.TrimEnd()
        }
        if ($process.ExitCode -ne 0) {
            throw "$CheckName failed with exit code $($process.ExitCode): $ExePath $($Arguments -join ' ')"
        }
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Variant) {
    $Variant = $env:HDU_PACKAGE_VARIANT
}
if (-not $Variant) {
    $Variant = "bundled"
}
if ($Variant -ne "bundled") {
    throw "Invalid package variant '$Variant'. Expected 'bundled'."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    $versionMatch = Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $versionMatch) {
        throw "Could not read project version from pyproject.toml"
    }
    $version = $versionMatch.Matches[0].Groups[1].Value

    $distDir = Join-Path $repoRoot "dist"
    $appDir = Join-Path $distDir "h-denoise"
    $buildDir = Join-Path $repoRoot "build"
    $zipPath = Join-Path $distDir "h-denoise-$Variant-windows-x64-v$version.zip"
    $smokeArgs = @("--smoke-test", "--smoke-runtime", "all")
    $env:HDU_PACKAGE_VARIANT = $Variant

    $optixDenoiser = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\windows-x64\optix-9.0\Denoiser.exe"
    if (-not (Test-Path -LiteralPath $optixDenoiser)) {
        throw "Bundled package requires the OptiX 9.0 Denoiser.exe. Expected: $optixDenoiser"
    }
    $oidnDenoiser = Join-Path $repoRoot "h_denoise_utils\vendor\oidn-denoiser\windows-x64\oidn-2.4.1\Denoiser.exe"
    if (-not (Test-Path -LiteralPath $oidnDenoiser)) {
        throw "Bundled package requires the custom OIDN Denoiser.exe. Expected: $oidnDenoiser"
    }

    if (Test-Path -LiteralPath $appDir) {
        Remove-Item -LiteralPath $appDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $buildDir) {
        Remove-Item -LiteralPath $buildDir -Recurse -Force
    }
    Get-ChildItem -Path $distDir -Filter "h-denoise-$Variant-windows-x64-v*.zip" -ErrorAction SilentlyContinue |
        Remove-Item -Force

    uv run --native-tls --frozen --extra pyside6 --extra package pyinstaller --noconfirm --clean "packaging/h-denoise.spec"

    $exePath = Join-Path $appDir "h-denoise.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Expected executable was not created: $exePath"
    }

    Invoke-FrozenExecutableCheck -ExePath $exePath -CheckName "dist-version" -Arguments @("--version")
    Invoke-FrozenExecutableCheck -ExePath $exePath -CheckName "dist-smoke-test" -Arguments $smokeArgs

    Compress-Archive -Path $appDir -DestinationPath $zipPath -Force

    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Expected package was not created: $zipPath"
    }

    $extractDir = Join-Path $buildDir "package-smoke-$Variant-$version"
    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $extractDir | Out-Null
    try {
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
        $extractedExePath = Join-Path $extractDir "h-denoise\h-denoise.exe"
        Invoke-FrozenExecutableCheck -ExePath $extractedExePath -CheckName "zip-version" -Arguments @("--version")
        Invoke-FrozenExecutableCheck -ExePath $extractedExePath -CheckName "zip-smoke-test" -Arguments $smokeArgs
    }
    finally {
        if (Test-Path -LiteralPath $extractDir) {
            Remove-Item -LiteralPath $extractDir -Recurse -Force
        }
    }

    Write-Host "Package created: $zipPath"
}
finally {
    Pop-Location
}
