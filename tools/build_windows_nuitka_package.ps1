param(
    [switch]$IncludeBundledRuntimes
)

$ErrorActionPreference = "Stop"

function Import-MsvcEnvironment {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) {
        throw "Visual Studio Installer's vswhere.exe was not found."
    }

    $installationPath = (& $vswhere `
        -latest `
        -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath).Trim()
    if (-not $installationPath) {
        throw "Visual Studio with the MSVC x64 build tools was not found."
    }

    $vcvars = Join-Path $installationPath "VC\Auxiliary\Build\vcvars64.bat"
    if (-not (Test-Path -LiteralPath $vcvars)) {
        throw "MSVC environment script was not found: $vcvars"
    }

    $environmentCommand = "`"$vcvars`" >nul && set"
    $environmentLines = & $env:ComSpec /d /s /c $environmentCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to initialize the MSVC build environment."
    }

    foreach ($line in $environmentLines) {
        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            continue
        }
        $name = $line.Substring(0, $separator)
        $value = $line.Substring($separator + 1)
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }

    $compiler = Get-Command cl.exe -ErrorAction SilentlyContinue
    if (-not $compiler) {
        throw "cl.exe was not available after initializing the MSVC environment."
    }
    Write-Host "Using MSVC environment: $($compiler.Source)"
}

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

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ExePath
    $startInfo.WorkingDirectory = Split-Path -Parent $ExePath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Arguments = ($Arguments | ForEach-Object {
        '"' + $_.Replace('"', '\"') + '"'
    }) -join " "

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Could not start $CheckName`: $ExePath"
    }

    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill()
        throw "$CheckName timed out after $TimeoutSeconds seconds."
    }

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $exitCode = $process.ExitCode
    $process.Dispose()

    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        Write-Host $stdout.TrimEnd()
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        Write-Host $stderr.TrimEnd()
    }
    if ($exitCode -ne 0) {
        throw "$CheckName failed with exit code $exitCode."
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    foreach ($name in @(
        "MSYSTEM",
        "MSYSTEM_CARCH",
        "MSYSTEM_CHOST",
        "MINGW_PREFIX",
        "MINGW_CHOST",
        "MINGW_PACKAGE_PREFIX",
        "MSYS"
    )) {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }

    Import-MsvcEnvironment

    $nuitkaCompilerArgs = @()
    $windowsSdkVersion = [version]$env:WindowsSDKVersion.TrimEnd("\\")
    if ($windowsSdkVersion -ge [version]"10.0.19041.0") {
        $env:CC = "cl.exe"
        $env:CXX = "cl.exe"
        Write-Host "Using MSVC with Windows SDK $windowsSdkVersion"
    }
    else {
        $mingwRoot = "C:\msys64\ucrt64\bin"
        $gcc = Join-Path $mingwRoot "gcc.exe"
        $gxx = Join-Path $mingwRoot "g++.exe"
        if (-not (Test-Path -LiteralPath $gcc) -or -not (Test-Path -LiteralPath $gxx)) {
            throw "Nuitka requires Windows SDK 10.0.19041 or newer for MSVC. Installed: $windowsSdkVersion"
        }

        $env:PATH = "$mingwRoot;$env:PATH"
        $env:CC = $gcc
        $env:CXX = $gxx
        $nuitkaCompilerArgs = @(
            "--mingw64",
            "--experimental=force-accept-windows-gcc",
            "--disable-ccache",
            "--lto=no"
        )
        Write-Host "Windows SDK $windowsSdkVersion is too old for Nuitka MSVC builds."
        Write-Host "Using existing experimental MSYS2 GCC: $gcc"
    }

    $versionMatch = Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' |
        Select-Object -First 1
    if (-not $versionMatch) {
        throw "Could not read project version from pyproject.toml."
    }
    $version = $versionMatch.Matches[0].Groups[1].Value

    $buildRoot = Join-Path $repoRoot "build\nuitka-windows"
    $compiledDir = Join-Path $buildRoot "nuitka_entry.dist"
    $appDir = Join-Path $repoRoot "dist\h-denoise-nuitka"
    $zipPath = Join-Path $repoRoot "dist\h-denoise-nuitka-windows-x64-v$version.zip"

    Remove-Item -LiteralPath $buildRoot, $appDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $buildRoot | Out-Null

    $env:QT_BACKEND = "pyside6"
    $nuitkaArgs = @(
        "--mode=standalone"
    ) + $nuitkaCompilerArgs + @(
        "--enable-plugin=pyside6",
        "--include-package=h_denoise_utils",
        "--include-module=PySide6.QtCore",
        "--include-module=PySide6.QtGui",
        "--include-module=PySide6.QtWidgets",
        "--include-data-files=h_denoise_utils/ui/style.qss=h_denoise_utils/ui/style.qss",
        "--include-data-dir=h_denoise_utils/ui/icons=h_denoise_utils/ui/icons",
        "--nofollow-import-to=PyQt6",
        "--include-windows-runtime-dlls=yes",
        "--windows-console-mode=force",
        "--windows-icon-from-ico=h_denoise_utils/ui/icons/logo.ico",
        "--output-dir=$buildRoot",
        "--output-filename=h-denoise.exe",
        "--report=$buildRoot\compilation-report.xml",
        "packaging/nuitka_entry.py"
    )

    $elapsed = Measure-Command {
        & uv run --system-certs --frozen --extra pyside6 --extra package-nuitka nuitka @nuitkaArgs
        $compileExitCode = $LASTEXITCODE
        if ($compileExitCode -ne 0) {
            throw "Nuitka compilation failed with exit code $compileExitCode."
        }
    }

    if (-not (Test-Path -LiteralPath $compiledDir)) {
        throw "Expected Nuitka standalone directory was not created: $compiledDir"
    }

    Copy-Item -LiteralPath $compiledDir -Destination $appDir -Recurse

    if ($IncludeBundledRuntimes) {
        $optixSource = Join-Path $repoRoot "h_denoise_utils\vendor\optix-denoiser\windows-x64"
        $oidnSource = Join-Path $repoRoot "h_denoise_utils\vendor\oidn-denoiser\windows-x64\oidn-2.5.0"
        if (-not (Test-Path -LiteralPath $optixSource)) {
            throw "Bundled OptiX runtimes were not found: $optixSource"
        }
        if (-not (Test-Path -LiteralPath $oidnSource)) {
            throw "Bundled OIDN 2.5.0 runtime was not found: $oidnSource"
        }

        $vendorRoot = Join-Path $appDir "h_denoise_utils\vendor"
        $optixDestination = Join-Path $vendorRoot "optix-denoiser"
        $oidnDestination = Join-Path $vendorRoot "oidn-denoiser\windows-x64"
        New-Item -ItemType Directory -Path $optixDestination, $oidnDestination -Force | Out-Null
        Copy-Item -LiteralPath $optixSource -Destination $optixDestination -Recurse
        Copy-Item -LiteralPath $oidnSource -Destination $oidnDestination -Recurse
    }

    $exePath = Join-Path $appDir "h-denoise.exe"
    Invoke-FrozenExecutableCheck -ExePath $exePath -CheckName "nuitka-version" -Arguments @("--version")
    $runtime = if ($IncludeBundledRuntimes) { "all" } else { "none" }
    Invoke-FrozenExecutableCheck `
        -ExePath $exePath `
        -CheckName "nuitka-smoke" `
        -Arguments @("--smoke-test", "--smoke-runtime", $runtime)

    Compress-Archive -Path $appDir -DestinationPath $zipPath -Force

    $extractDir = Join-Path $buildRoot "package-smoke-$version"
    Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $extractDir | Out-Null
    try {
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
        $extractedExe = Get-ChildItem -LiteralPath $extractDir -Filter "h-denoise.exe" -Recurse |
            Select-Object -First 1
        if (-not $extractedExe) {
            throw "The Nuitka archive does not contain h-denoise.exe."
        }
        Invoke-FrozenExecutableCheck `
            -ExePath $extractedExe.FullName `
            -CheckName "nuitka-archive-version" `
            -Arguments @("--version")
        Invoke-FrozenExecutableCheck `
            -ExePath $extractedExe.FullName `
            -CheckName "nuitka-archive-smoke" `
            -Arguments @("--smoke-test", "--smoke-runtime", $runtime)
    }
    finally {
        Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    $files = Get-ChildItem -LiteralPath $appDir -Recurse -File
    $totalBytes = ($files | Measure-Object Length -Sum).Sum
    $zipBytes = (Get-Item -LiteralPath $zipPath).Length
    Write-Host ("Nuitka build time: {0:N2} seconds" -f $elapsed.TotalSeconds)
    Write-Host "Nuitka package directory: $appDir"
    Write-Host "Nuitka archive: $zipPath"
    Write-Host "Nuitka directory bytes: $totalBytes"
    Write-Host "Nuitka archive bytes: $zipBytes"
    Write-Host "Nuitka file count: $($files.Count)"
}
finally {
    Pop-Location
}
