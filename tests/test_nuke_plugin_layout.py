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
        NUKE_ROOT / "src" / "HOidnDenoise.cpp",
        NUKE_ROOT / "src" / "HOidnBridge.cpp",
        NUKE_ROOT / "src" / "oidn_bridge_protocol.h",
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

    menu = paths[1].read_text(encoding="utf-8")
    assert '"Filter/HOptixDenoise"' in menu
    assert '"Filter/HOidnDenoise"' in menu

    validator = paths[-1].read_text(encoding="utf-8")
    assert 'nuke.addFormat("520 8 1.0 HOptixDenoiseTiledTest")' in validator
    assert "tile_size, render_format in render_cases" in validator
    assert 'nuke.createNode("HOidnDenoise"' in validator
    assert '"HDU_NUKE_VALIDATE_OIDN"' in validator


def test_cmake_defines_real_and_stub_core_targets() -> None:
    """Ensure hosted checks and production builds use the same adapter."""
    cmake = (NUKE_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "HDU_NUKE_STUB_OPTIX" in cmake
    assert "optix_denoiser_stub.cpp" in cmake
    assert "optix_denoiser.cpp" in cmake
    assert 'set(HDU_NUKE_PACKAGE_DIR "HDenoiseNodes")' in cmake
    assert "add_library(HOptixDenoise SHARED" in cmake
    assert "add_library(HOidnDenoise SHARED" in cmake
    assert "add_executable(HOidnBridge" in cmake
    assert "/DELAYLOAD:OpenImageDenoise.dll" in cmake
    assert "MultiThreaded$<$<CONFIG:Debug>:Debug>" in cmake
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


def test_oidn_node_uses_an_isolated_cuda_helper() -> None:
    """Prevent Intel runtime DLLs from loading directly into Nuke."""
    node_source = (NUKE_ROOT / "src" / "HOidnDenoise.cpp").read_text(
        encoding="utf-8"
    )
    bridge_source = (NUKE_ROOT / "src" / "HOidnBridge.cpp").read_text(
        encoding="utf-8"
    )
    protocol = (NUKE_ROOT / "src" / "oidn_bridge_protocol.h").read_text(
        encoding="utf-8"
    )

    for expected in (
        'kClass = "HOidnDenoise"',
        'return "beauty"',
        'return "albedo"',
        'return "normal"',
        '"gpu_device"',
        '"quality"',
        '"hdr"',
        '"clean_aux"',
        '"normal_encoding"',
        '"passthrough_on_error"',
        '"HOidnBridge.exe"',
        "CreateProcessW",
        "TerminateProcess",
        "CREATE_NO_WINDOW",
    ):
        assert expected in node_source
    assert "OpenImageDenoise/oidn.hpp" not in node_source
    assert "OpenImageDenoise/oidn.hpp" in bridge_source
    assert "oidn::DeviceType::CUDA" in bridge_source
    assert 'SetDllDirectoryW(L"")' in bridge_source
    assert "SetDefaultDllDirectories" in bridge_source
    assert "HDUOIDN1" not in protocol
    assert "kMagic" in protocol
    assert "static_assert(sizeof(Header) == 32)" in protocol


def test_nuke_build_validates_pe_dependencies() -> None:
    """Keep production packages on the CUDA Driver API dependency surface."""
    build_script = (
        REPO_ROOT / "tools" / "build_nuke_optix.ps1"
    ).read_text(encoding="utf-8")

    assert '$packageName = "HDenoiseNodes"' in build_script
    assert "Get-PeDependencies" in build_script
    assert "dumpbin.exe" in build_script
    assert '"DDImage.dll"' in build_script
    assert '"nvcuda.dll"' in build_script
    assert "cudartDependencies" in build_script
    assert "validated = -not $SkipValidation.IsPresent" in build_script
    assert "dependencies = $dependencies" in build_script
    assert '"HOidnDenoise.dll"' in build_script
    assert '"HOidnBridge.exe"' in build_script
    assert "OIDN Nuke plugin must isolate OpenImageDenoise" in build_script
    assert "OpenImageDenoise_device_cuda.dll" in build_script
    assert "OpenImageDenoise_device_cpu.dll" not in build_script
    assert 'oidn_version = if ($buildOidn)' in build_script
    assert "HDU_NUKE_VALIDATE_OIDN" in build_script
    assert "$env:VSCMD_VER" in build_script
    assert "-notcontains $ninjaDirectory" in build_script


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
    assert "nuke-oidn-sdk-windows-2.5.0" in workflow
    assert workflow.count("actions/cache@v5") == 6
    assert "tools/validate_nuke_release_assets.py" in workflow
    assert '--source-commit "${GITHUB_SHA}"' in workflow
    assert 'commits/${RELEASE_TAG}' in workflow
    assert 'tag_commit' in workflow
    assert workflow.count("persist-credentials: false") == 3
    assert "BUILD_SCOPE: ${{ inputs.build_scope }}" in workflow
    assert "RELEASE_TAG: ${{ inputs.release_tag }}" in workflow
    assert '--build-scope "${BUILD_SCOPE}"' in workflow
    assert '--release-tag "${RELEASE_TAG}"' in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "actions/download-artifact@v7" in workflow
