"""Structural regression tests for the standalone OptiX CLI build."""

from __future__ import annotations

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools.build_optix_denoiser_windows import sync_cuda_driver_files
from tools.fetch_optix_denoiser_windows import (
    _latest_local_asset,
    acquire_asset,
    remove_legacy_files,
    safe_extract,
    validate_bundle,
    write_summary,
)
from tools.optix_source_key import (
    COMMON_SOURCE_KEY_INPUTS,
    LINUX_PLATFORM,
    OPTIX_COMMITS,
    WINDOWS_PLATFORM,
    sha256_file,
    sha256_source_file,
    source_key,
    source_key_inputs,
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


def test_source_keys_only_include_relevant_platform_build_inputs(
    tmp_path: Path,
) -> None:
    """Avoid invalidating one platform when only the other builder changes."""
    all_inputs = set(source_key_inputs(WINDOWS_PLATFORM)) | set(
        source_key_inputs(LINUX_PLATFORM)
    )
    for relative in all_inputs:
        source = REPO_ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    windows_before = source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        WINDOWS_PLATFORM,
        "Release",
    )
    linux_before = source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        LINUX_PLATFORM,
        "Release",
    )

    windows_builder = tmp_path / "tools" / "build_optix_denoiser_windows.py"
    windows_builder.write_text(
        windows_builder.read_text(encoding="utf-8") + "\n# windows-only change\n",
        encoding="utf-8",
    )

    windows_after = source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        WINDOWS_PLATFORM,
        "Release",
    )
    assert windows_after != windows_before
    assert source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        LINUX_PLATFORM,
        "Release",
    ) == linux_before

    linux_builder = tmp_path / "tools" / "build_optix_denoiser.sh"
    linux_builder.write_text(
        linux_builder.read_text(encoding="utf-8") + "\n# linux-only change\n",
        encoding="utf-8",
    )

    assert source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        WINDOWS_PLATFORM,
        "Release",
    ) == windows_after
    assert source_key(
        tmp_path,
        "9.1",
        OPTIX_COMMITS["9.1"],
        LINUX_PLATFORM,
        "Release",
    ) != linux_before


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


def test_release_fallback_downloads_newest_matching_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select and download the newest compatible GitHub release asset."""
    older = "optix-denoiser-windows-x64-optix-9.1-old.zip"
    newer = "optix-denoiser-windows-x64-optix-9.1-new.zip"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "view" in command:
            payload = {
                "assets": [
                    {"name": newer, "updatedAt": "2026-07-29T12:00:00Z"},
                    {"name": older, "updatedAt": "2026-07-28T12:00:00Z"},
                ]
            }
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(payload),
                stderr="",
            )
        name = command[command.index("--pattern") + 1]
        destination = Path(command[command.index("--dir") + 1]) / name
        destination.write_bytes(b"downloaded")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.delenv("HDU_OPTIX_DENOISER_ZIP_DIR", raising=False)
    monkeypatch.setattr(
        "tools.fetch_optix_denoiser_windows.shutil.which",
        lambda _name: "gh.exe",
    )
    monkeypatch.setattr(
        "tools.fetch_optix_denoiser_windows.subprocess.run",
        fake_run,
    )

    downloaded = acquire_asset(
        tmp_path,
        "optix-denoiser-windows-x64-optix-9.1-*.zip",
        repository="owner/repository",
        tag="support-tag",
    )

    assert downloaded == tmp_path / newer
    assert downloaded.read_bytes() == b"downloaded"
    assert calls[1][calls[1].index("--pattern") + 1] == newer


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


def test_safe_extract_rejects_parent_traversal(tmp_path: Path) -> None:
    """Prevent support archives from writing outside their extraction root."""
    archive_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "blocked")

    with zipfile.ZipFile(archive_path) as archive:
        with pytest.raises(RuntimeError, match="escapes destination"):
            safe_extract(archive, tmp_path / "extract")

    assert not (tmp_path / "escape.txt").exists()


def test_vendor_summary_preserves_other_installed_variants(tmp_path: Path) -> None:
    """Keep partial fetches from dropping already installed runtime variants."""
    old_variant = tmp_path / "optix-8.1"
    old_variant.mkdir()
    old_executable = old_variant / "Denoiser.exe"
    old_executable.write_bytes(b"old")
    (old_variant / "manifest.json").write_text(
        json.dumps(
            {
                "name": "hdu-optix-denoiser",
                "executable": "Denoiser.exe",
                "optix_version": "8.1",
                "optix_dev_commit": OPTIX_COMMITS["8.1"],
                "platform": PLATFORM,
                "contract": "optix-compatible-multipart-v1",
                "source_key": "old-key",
                "sha256": sha256_file(old_executable),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "default_optix_version": "8.1",
                "variants": [
                    {
                        "optix_version": "8.1",
                        "optix_dev_commit": OPTIX_COMMITS["8.1"],
                        "source_key": "old-key",
                        "executable": "optix-8.1/Denoiser.exe",
                        "manifest": "optix-8.1/manifest.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (tmp_path / "Denoiser.exe").write_bytes(b"legacy")
    (tmp_path / "LICENSE").write_text("legacy", encoding="utf-8")
    remove_legacy_files(tmp_path)
    assert (tmp_path / "manifest.json").is_file()

    write_summary(
        tmp_path,
        ["9.1"],
        {"9.1": "new-key"},
        repository="owner/repository",
        tag="support-tag",
    )

    summary = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert summary["default_optix_version"] == "8.1"
    assert {
        variant["optix_version"]: variant["source_key"]
        for variant in summary["variants"]
    } == {"8.1": "old-key", "9.1": "new-key"}


def test_corrupt_cuda_archive_is_removed_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Make a failed cached CUDA download recoverable on the next build."""
    manifest = {
        "cuda_cudart": {
            "windows-x86_64": {
                "relative_path": "cuda/test.zip",
                "sha256": "0" * 64,
            }
        }
    }

    monkeypatch.setattr(
        "tools.build_optix_denoiser_windows.urllib.request.urlopen",
        lambda _url: io.BytesIO(json.dumps(manifest).encode()),
    )

    def fake_retrieve(_url: str, destination: Path) -> tuple[str, None]:
        Path(destination).write_bytes(b"corrupt")
        return str(destination), None

    monkeypatch.setattr(
        "tools.build_optix_denoiser_windows.urllib.request.urlretrieve",
        fake_retrieve,
    )
    stale_extract = tmp_path / "test"
    stale_extract.mkdir()
    (stale_extract / "stale.txt").write_text("stale", encoding="utf-8")

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        sync_cuda_driver_files(tmp_path)

    assert not (tmp_path / "test.zip").exists()
    assert not (tmp_path / "test.zip.part").exists()
    assert not stale_extract.exists()


def test_partial_cuda_extraction_is_rebuilt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-extract a valid cached archive when its directory is incomplete."""
    archive_path = tmp_path / "test.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("cuda/include/cuda.h", "header")
        archive.writestr("cuda/lib/x64/cuda.lib", "library")
    manifest = {
        "cuda_cudart": {
            "windows-x86_64": {
                "relative_path": "cuda/test.zip",
                "sha256": sha256_file(archive_path),
            }
        }
    }
    monkeypatch.setattr(
        "tools.build_optix_denoiser_windows.urllib.request.urlopen",
        lambda _url: io.BytesIO(json.dumps(manifest).encode()),
    )
    stale_extract = tmp_path / "test"
    stale_extract.mkdir()
    (stale_extract / "partial.txt").write_text("partial", encoding="utf-8")

    cuda_root = sync_cuda_driver_files(tmp_path)

    assert cuda_root == stale_extract / "cuda"
    assert (cuda_root / "include" / "cuda.h").is_file()
    assert (cuda_root / "lib" / "x64" / "cuda.lib").is_file()
    assert not (stale_extract / "partial.txt").exists()


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
    assert "project(Denoiser LANGUAGES CXX)" in cmake
    assert "target_include_directories" in cmake
    assert "/W4" in cmake
    assert "-Wall -Wextra -Wpedantic" in cmake
    assert source.index("denoiser_options.denoiseAlpha") < source.index(
        "optixDenoiserCreate"
    )
    assert "hdu::optix::DenoiserSession denoiser_session" in source
    assert "denoiser_session.denoise(request)" in source
    assert "std::min(in_size, out_size)" in source
    assert "outputPathFor(a.filename, a.output_filename, out_suffix)" in source


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

    assert "native/optix-denoiser/include" in COMMON_SOURCE_KEY_INPUTS
    assert "native/optix-denoiser/profiles" in source_key_inputs(WINDOWS_PLATFORM)
    assert "native/optix-denoiser/profiles" not in source_key_inputs(LINUX_PLATFORM)
    for text in (linux_builder, linux_fetcher):
        assert "optix_source_key.py" in text
    assert "optix_source_key" in windows_fetcher
    assert "tools/optix_source_key.py" in COMMON_SOURCE_KEY_INPUTS
    assert "optix_source_key.py" in workflow
    assert "build_optix_denoiser_windows.py" in workflow
    assert "fetch_optix_denoiser_windows.py" in workflow
    assert "windows-cmake-3.28" in workflow
    assert "fetch_optix_denoiser.ps1" not in workflow
    assert "ACTUAL_SOURCE_KEYS" in linux_fetcher
    assert "gh release view" in linux_fetcher
    assert "target.is_relative_to(root)" in linux_fetcher
    assert "installed_keys" in windows_fetcher


def test_native_conan_options_include_static_link_dependencies() -> None:
    """Prevent system libraries from leaking into static OpenImageIO builds."""
    conanfile = (OPTIX_ROOT / "conanfile.txt").read_text(encoding="utf-8")
    assert "openimageio/*:shared=False" in conanfile
    assert "openimageio/*:with_libpng=True" in conanfile


def test_native_optix_workflow_builds_source_changes() -> None:
    """Compile every supported native variant before source changes merge."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "build-optix.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert '"native/optix-denoiser/**"' in workflow
    assert workflow.count("persist-credentials: false") == 3
    assert "permissions:\n  contents: read" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "RELEASE_TAG: ${{ inputs.release_tag }}" in workflow
    assert '$tag = "${{ github.event.inputs.release_tag }}"' not in workflow
    assert "'tools/build_optix_denoiser_windows.py') }}" in workflow
    assert "'tools/build_optix_denoiser.sh') }}" in workflow
    assert "'native/optix-denoiser/profiles/**'" not in workflow
    assert workflow.count("max-parallel: 1") == 2
    assert workflow.count("actions/cache@v5") == 2
    assert "Jimver/cuda-toolkit@v0.2.35" in workflow
    assert "key: optix-conan-${{ runner.os }}-${{ hashFiles" in workflow
    assert "optix-conan-${{ runner.os }}-${{ matrix.optix-version }}" not in workflow


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
    assert "--native-tls" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO_ROOT / ".github" / "workflows" / "full-validation.yml",
            REPO_ROOT / ".github" / "workflows" / "oidn-denoiser.yml",
            REPO_ROOT / "tools" / "build_linux_package.sh",
            REPO_ROOT / "tools" / "build_oidn_denoiser.sh",
            REPO_ROOT / "tools" / "build_windows_package.ps1",
        )
    )


def test_windows_conan_profile_uses_ninja() -> None:
    """Keep dependency builds independent of MSBuild's SDK search paths."""
    profile = (
        OPTIX_ROOT / "profiles" / "windows-cmake-3.28"
    ).read_text(encoding="utf-8")
    assert "cmake/3.28.6" in profile
    assert "generator=Ninja" in profile
