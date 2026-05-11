$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    $versionMatch = Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $versionMatch) {
        throw "Could not read project version from pyproject.toml"
    }
    $version = $versionMatch.Matches[0].Groups[1].Value

    if ($env:GITHUB_SHA) {
        $shortSha = $env:GITHUB_SHA.Substring(0, 7)
    }
    else {
        $shortSha = (& git rev-parse --short HEAD).Trim()
    }

    $distDir = Join-Path $repoRoot "dist"
    $appDir = Join-Path $distDir "h-denoise"
    $buildDir = Join-Path $repoRoot "build"
    $zipPath = Join-Path $distDir "h-denoise-windows-x64-v$version-$shortSha.zip"

    if (Test-Path -LiteralPath $appDir) {
        Remove-Item -LiteralPath $appDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $buildDir) {
        Remove-Item -LiteralPath $buildDir -Recurse -Force
    }
    Get-ChildItem -Path $distDir -Filter "h-denoise-windows-x64-v*.zip" -ErrorAction SilentlyContinue |
        Remove-Item -Force

    uv run --native-tls --frozen --extra pyside6 --extra package pyinstaller --noconfirm --clean "packaging/h-denoise.spec"

    $exePath = Join-Path $appDir "h-denoise.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Expected executable was not created: $exePath"
    }

    & $exePath --version
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen executable version check failed with exit code $LASTEXITCODE"
    }

    & $exePath --smoke-test
    if ($LASTEXITCODE -ne 0) {
        throw "Frozen executable smoke test failed with exit code $LASTEXITCODE"
    }

    Compress-Archive -Path $appDir -DestinationPath $zipPath -Force

    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Expected package was not created: $zipPath"
    }

    Write-Host "Package created: $zipPath"
}
finally {
    Pop-Location
}
