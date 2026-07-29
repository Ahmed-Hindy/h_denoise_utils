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
    ):
        assert expected in source
