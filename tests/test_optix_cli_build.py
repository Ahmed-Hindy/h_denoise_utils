"""Structural regression tests for the standalone OptiX CLI build."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.fetch_optix_denoiser_windows import (
    _latest_local_asset,
    validate_bundle,
    write_summary,
)
from tools.optix_source_key import (
    OPTIX_COMMITS,
    SOURCE_KEY_INPUTS,
    WINDOWS_PLATFORM,
    sha256_file,
    sha256_source_file,
    source_key,
)

PLATFORM = WINDOWS_PLATFORM

REPO_ROOT = Path(__file__).resolve().parents[1]
OPTIX_ROOT = REPO_ROOT / "native" / "optix-denoiser"
WINDOWS_BUILDER = REPO_ROOT / "tools" / "build_optix_denoiser_windows.py"
WINDOWS_FETCHER = REPO_ROOT / "tools" / "fetch_optix_denoiser_windows.py"


def test_windows_optix_scripts_are_python_and_parse() -> None:
    """Keep Windows build and fetch entry points compatible with Python 3.11."""
    builder_source = WINDOWS_BUILDER.read_text(encoding="utf-8")
    fetcher_source = WINDOWS_FETCHER.read_text(encoding="utf-8")
    ast.parse(builder_source, filename=str(WINDOWS_BUILDER))
    ast.parse(fetcher_source, filename=str(WINDOWS_FETCHER))
    assert "--system-certs" in builder_source
    assert "cuda_cudart" in builder_source
    assert "cuda_nvcc" not in builder_source
    assert "HDU_OPTIX_DENOISER_ZIP_DIR" in fetcher_source
    assert "source_key" in fetcher_source


def test_source_hash_normalizes_line_endings(tmp_path: Path) -> None:
    """Keep release asset keys stable across Windows and Linux checkouts."""
    lf_path = tmp_path / "lf.txt"
    crlf_path = tmp_path / "crlf.txt"
    lf_path.write_bytes(b"first\nsecond\n")
    crlf_path.write_bytes(b"first\r\nsecond\r\n")

    assert sha256_source_file(lf_path) == sha256_source_file(crlf_path)


def test_source_key_cli_matches_library() -> None:
    """Keep Linux shell callers aligned with the shared Python implementation."""
    expected = source_key(
        REPO_ROOT,
        "9.1",
        OPTIX_COMMITS["9.1"],
        WINDOWS_PLATFORM,
        "Release",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "optix_source_key.py"),
            "--repo-root",
            str(REPO_ROOT),
            "--optix-version",
            "9.1",
            "--optix-commit",
            OPTIX_COMMITS["9.1"],
            "--platform",
            WINDOWS_PLATFORM,
            "--configuration",
            "Release",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == expected


def test_fetcher_validates_manifest_and_executable(tmp_path: Path) -> None:
    """Reject altered executables before packaging them with the app."""
    executable = tmp_path / "Denoiser.exe"
    executable.write_bytes(b"validated-optix-binary")
    key = "source-key"
    manifest = {
        "name": "hdu-optix-denoiser",
        "executable": "Denoiser.exe",
        "optix_version": "9.1",
        "optix_dev_commit": OPTIX_COMMITS["9.1"],
        "platform": PLATFORM,
        "contract": "optix-compatible-multipart-v1",
        "source_key": key,
        "sha256": sha256_file(executable),
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    assert validate_bundle(
        tmp_path,
        "9.1",
        key,
        allow_source_key_mismatch=False,
    ) == manifest
    executable.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="SHA-256"):
        validate_bundle(
            tmp_path,
            "9.1",
            key,
            allow_source_key_mismatch=False,
        )


def test_fetcher_mismatch_mode_uses_actual_manifest_key(tmp_path: Path) -> None:
    """Allow compatible released assets without falsifying their source key."""
    executable = tmp_path / "Denoiser.exe"
    executable.write_bytes(b"compatible-release-binary")
    manifest = {
        "name": "hdu-optix-denoiser",
        "executable": "Denoiser.exe",
        "optix_version": "9.1",
        "optix_dev_commit": OPTIX_COMMITS["9.1"],
        "platform": PLATFORM,
        "contract": "optix-compatible-multipart-v1",
        "source_key": "released-key",
        "sha256": sha256_file(executable),
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    result = validate_bundle(
        tmp_path,
        "9.1",
        "current-tree-key",
        allow_source_key_mismatch=True,
    )

    assert result["source_key"] == "released-key"
    with pytest.raises(RuntimeError, match="source key mismatch"):
        validate_bundle(
            tmp_path,
            "9.1",
            "current-tree-key",
            allow_source_key_mismatch=False,
        )


def test_fetcher_selects_newest_compatible_local_asset(tmp_path: Path) -> None:
    """Choose one deterministic fallback when multiple released keys exist."""
    older = tmp_path / "optix-denoiser-windows-x64-optix-9.1-old.zip"
    newer = tmp_path / "optix-denoiser-windows-x64-optix-9.1-new.zip"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

    selected = _latest_local_asset(
        tmp_path,
        "optix-denoiser-windows-x64-optix-9.1-*.zip",
    )

    assert selected == newer


def test_vendor_summary_records_installed_source_keys(tmp_path: Path) -> None:
    """Keep package metadata honest when a compatible fallback is selected."""
    installed_keys = {
        "8.1": "released-81",
        "9.0": "released-90",
        "9.1": "released-91",
    }

    write_summary(
        tmp_path,
        list(installed_keys),
        installed_keys,
        repository="owner/repository",
        tag="support-tag",
    )

    summary = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert {
        variant["optix_version"]: variant["source_key"]
        for variant in summary["variants"]
    } == installed_keys


def test_cli_uses_cuda_driver_api_only() -> None:
    """Prevent the legacy temporal and AOV path from restoring CUDART."""
    source = (OPTIX_ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
    cmake = (OPTIX_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")

    assert "#include <cuda.h>" in source
    assert "#include <cuda_runtime.h>" not in source
    for runtime_call in (
        "cudaSetDevice",
        "cudaMalloc",
        "cudaMemcpy",
        "cudaFree",
        "cudaStreamCreate",
    ):
        assert runtime_call not in source
    for driver_call in (
        "cuDevicePrimaryCtxRetain",
        "cuMemAlloc",
        "cuMemcpyHtoD",
        "cuMemcpyDtoH",
        "cuStreamCreate",
    ):
        assert driver_call in source

    assert "cuda_runtime.h" not in cmake
    assert "cudart" not in cmake.lower()
    assert "cuda.lib" in cmake
    assert source.index("denoiser_options.denoiseAlpha") < source.index(
        "optixDenoiserCreate"
    )


def test_source_key_inputs_match_fetchers() -> None:
    """Ensure builders and fetchers agree on source-keyed asset names."""
    windows_fetcher = WINDOWS_FETCHER.read_text(encoding="utf-8")
    linux_builder = (REPO_ROOT / "tools" / "build_optix_denoiser.sh").read_text(
        encoding="utf-8"
    )
    linux_fetcher = (REPO_ROOT / "tools" / "fetch_optix_denoiser.sh").read_text(
        encoding="utf-8"
    )
    workflow = (REPO_ROOT / ".github" / "workflows" / "build-optix.yml").read_text(
        encoding="utf-8"
    )

    assert "native/optix-denoiser/include" in SOURCE_KEY_INPUTS
    assert "native/optix-denoiser/profiles" in SOURCE_KEY_INPUTS
    for text in (linux_builder, linux_fetcher):
        assert "optix_source_key.py" in text
    assert "optix_source_key" in windows_fetcher
    assert "tools/optix_source_key.py" in SOURCE_KEY_INPUTS
    assert "optix_source_key.py" in workflow
    assert "build_optix_denoiser_windows.py" in workflow
    assert "fetch_optix_denoiser_windows.py" in workflow
    assert "windows-cmake-3.28" in workflow
    assert "fetch_optix_denoiser.ps1" not in workflow
    assert "ACTUAL_SOURCE_KEYS" in linux_fetcher
    assert "gh release view" in linux_fetcher
    assert "installed_keys" in windows_fetcher
    assert "_latest_release_asset" in windows_fetcher


def test_pull_request_packaging_allows_compatible_optix_assets() -> None:
    """Keep PR packaging unblocked while main and release fetches stay strict."""
    nuitka_workflow = (
        REPO_ROOT / ".github" / "workflows" / "nuitka-package.yml"
    ).read_text(encoding="utf-8")
    oidn_workflow = (
        REPO_ROOT / ".github" / "workflows" / "oidn-denoiser.yml"
    ).read_text(encoding="utf-8")
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    release_workflow = (
        REPO_ROOT / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")

    assert "--allow-source-key-mismatch" in nuitka_workflow
    assert 'github.event_name }}" -eq "pull_request"' in oidn_workflow
    assert 'github.event_name }}" == "pull_request"' in oidn_workflow
    assert "--allow-source-key-mismatch" not in ci_workflow
    assert "--allow-source-key-mismatch" not in release_workflow


def test_windows_conan_profile_uses_ninja() -> None:
    """Keep dependency builds independent of MSBuild's SDK search paths."""
    profile = (
        OPTIX_ROOT / "profiles" / "windows-cmake-3.28"
    ).read_text(encoding="utf-8")
    assert "cmake/3.28.6" in profile
    assert "generator=Ninja" in profile
