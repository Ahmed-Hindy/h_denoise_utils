"""Structural tests for the native Nuke OptiX integration."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NUKE_ROOT = REPO_ROOT / "native" / "nuke-optix"
OPTIX_ROOT = REPO_ROOT / "native" / "optix-denoiser"


def test_nuke_plugin_sources_are_present() -> None:
    """Keep all required source and package files under version control."""
    expected = (
        NUKE_ROOT / "CMakeLists.txt",
        NUKE_ROOT / "src" / "HOptixDenoise.cpp",
        NUKE_ROOT / "stub" / "optix_denoiser_stub.cpp",
        NUKE_ROOT / "package" / "init.py",
        NUKE_ROOT / "package" / "menu.py",
        NUKE_ROOT / "package" / "README.md",
        OPTIX_ROOT / "include" / "hdu" / "optix_denoiser.h",
        OPTIX_ROOT / "src" / "optix_denoiser.cpp",
        REPO_ROOT / "tools" / "build_nuke_optix.ps1",
        REPO_ROOT / "tools" / "validate_nuke_optix_plugin.py",
        REPO_ROOT / "tools" / "validate_nuke_release_assets.py",
    )

    missing = [path.relative_to(REPO_ROOT) for path in expected if not path.is_file()]
    assert not missing, f"Missing Nuke plugin files: {missing}"


def test_nuke_python_hooks_parse() -> None:
    """Catch syntax errors without requiring Nuke's embedded Python runtime."""
    paths = (
        NUKE_ROOT / "package" / "init.py",
        NUKE_ROOT / "package" / "menu.py",
        REPO_ROOT / "tools" / "validate_nuke_optix_plugin.py",
    )
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_cmake_defines_real_and_stub_core_targets() -> None:
    """Ensure hosted checks and production builds use the same adapter."""
    cmake = (NUKE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "HDU_NUKE_STUB_OPTIX" in cmake
    assert "optix_denoiser_stub.cpp" in cmake
    assert "optix_denoiser.cpp" in cmake
    assert "add_library(HOptixDenoise SHARED" in cmake
    assert "DDImage.lib" in cmake


def test_native_core_uses_cuda_driver_api_only() -> None:
    """Avoid introducing a CUDA Toolkit or runtime DLL dependency."""
    source = (OPTIX_ROOT / "src" / "optix_denoiser.cpp").read_text(
        encoding="utf-8"
    )
    assert "#include <cuda.h>" in source
    assert "#include <cuda_runtime.h>" not in source
    assert "cuDevicePrimaryCtxRetain" in source
    assert "cuMemcpyHtoDAsync" in source
    assert "optixDenoiserInvoke" in source
    assert "class DenoiserSession::Impl" in source
    assert "ensure_buffers(request)" in source


def test_nuke_node_exposes_expected_contract() -> None:
    """Protect the node name, inputs, and production controls."""
    source = (NUKE_ROOT / "src" / "HOptixDenoise.cpp").read_text(
        encoding="utf-8"
    )
    for expected in (
        'kClass = "HOptixDenoise"',
        'return "beauty"',
        'return "albedo"',
        'return "normal"',
        '"blend"',
        '"tile_size"',
        '"gpu_device"',
        '"normal_encoding"',
        '"passthrough_on_error"',
        "hdu::optix::DenoiserSession denoiser_session_",
        "denoiser_session_.denoise(request)",
        "denoiser_session_.reset()",
        "abort_requested",
    ):
        assert expected in source


def test_nuke_workflow_supports_single_matrix_and_release_builds() -> None:
    """Protect the validated build matrix and opt-in release path."""
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "nuke-optix.yml"
    ).read_text(encoding="utf-8")

    for nuke_version in ("14.1v8", "15.0v1", "15.1v4", "17.0v3"):
        assert nuke_version in workflow
    for optix_version in ('"8.1"', '"9.0"', '"9.1"'):
        assert optix_version in workflow

    assert "supported-matrix" in workflow
    assert "max-parallel: 1" in workflow
    assert "publish_release" in workflow
    assert "gh release upload" in workflow
    assert "Remove stale packages" in workflow
    assert "nuke-optix-cuda-windows-12.9.1" in workflow
    assert "nuke-optix-sdk-${{ matrix.optix_version }}" in workflow
    assert "tools/validate_nuke_release_assets.py" in workflow
    assert '--source-commit "${GITHUB_SHA}"' in workflow
    assert 'commits/${RELEASE_TAG}' in workflow
    assert 'tag_commit' in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "actions/download-artifact@v7" in workflow
