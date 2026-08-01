"""Tests for combined Nuke denoiser release package validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "tools" / "validate_nuke_release_assets.py"


def _load_validator() -> ModuleType:
    """Load the release validator without making tools a Python package."""
    spec = importlib.util.spec_from_file_location(
        "validate_nuke_release_assets",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _record(binary: bytes, **values: object) -> dict[str, object]:
    """Create a binary integrity manifest record."""
    record: dict[str, object] = {
        "sha256": hashlib.sha256(binary).hexdigest(),
        "size": len(binary),
    }
    record.update(values)
    return record


def _write_package(
    directory: Path,
    *,
    nuke_line: str,
    optix_version: str,
    version: str = "2.0.1",
    source_commit: str = "abc123",
    optix_binary: bytes = b"optix-plugin",
    oidn_binary: bytes = b"oidn-plugin",
    helper_binary: bytes = b"oidn-helper",
    include_oidn_binary: bool = True,
    oidn_node_overrides: dict[str, object] | None = None,
    helper_overrides: dict[str, object] | None = None,
    runtime_names: set[str] | None = None,
    **overrides: object,
) -> Path:
    """Create a minimal combined production package ZIP."""
    runtime_names = runtime_names or set(VALIDATOR.EXPECTED_OIDN_RUNTIME_DLLS)
    runtime_binaries = {
        name: f"runtime:{name}".encode() for name in runtime_names
    }
    helper = _record(
        helper_binary,
        name="HOidnBridge.exe",
        dependencies=["OpenImageDenoise.dll", "KERNEL32.dll"],
    )
    if helper_overrides:
        helper.update(helper_overrides)
    oidn_node = _record(
        oidn_binary,
        name="HOidnDenoise",
        dependencies=["DDImage.dll", "KERNEL32.dll"],
        helper=helper,
        runtime_dlls=[
            _record(binary, name=name)
            for name, binary in sorted(runtime_binaries.items())
        ],
    )
    if oidn_node_overrides:
        oidn_node.update(oidn_node_overrides)

    manifest: dict[str, object] = {
        "name": "HDenoiseNodes",
        "version": version,
        "source_commit": source_commit,
        "nuke_version": VALIDATOR.SUPPORTED_NUKE_REVISIONS.get(
            nuke_line,
            f"{nuke_line}v1",
        ),
        "nuke_binary_version": nuke_line,
        "optix_version": optix_version,
        "optix_dev_commit": VALIDATOR.SUPPORTED_OPTIX_COMMITS.get(
            optix_version,
            "unsupported",
        ),
        "platform": "windows-x64",
        "build_configuration": "Release",
        "stub": False,
        "validated": True,
        "dependencies": ["DDImage.dll", "nvcuda.dll", "KERNEL32.dll"],
        "sha256": hashlib.sha256(optix_binary).hexdigest(),
        "size": len(optix_binary),
        "oidn_version": VALIDATOR.EXPECTED_OIDN_VERSION,
        "oidn_node": oidn_node,
    }
    manifest.update(overrides)
    asset = directory / (
        f"h-denoise-nuke-{nuke_line}-windows-x64-"
        f"optix-{optix_version}-v{version}.zip"
    )
    with zipfile.ZipFile(asset, "w") as archive:
        archive.writestr("HDenoiseNodes/manifest.json", json.dumps(manifest))
        archive.writestr("HDenoiseNodes/HOptixDenoise.dll", optix_binary)
        if include_oidn_binary:
            archive.writestr("HDenoiseNodes/HOidnDenoise.dll", oidn_binary)
        archive.writestr("HDenoiseNodes/HOidnBridge.exe", helper_binary)
        for name, binary in runtime_binaries.items():
            archive.writestr(f"HDenoiseNodes/{name}", binary)
    return asset


def _validate(directory: Path, source_commit: str = "abc123") -> list[Path]:
    return VALIDATOR.validate_release_assets(
        assets_dir=directory,
        build_scope="single",
        release_tag="nuke-optix-v2.0.1",
        source_commit=source_commit,
    )


def test_validate_single_release_package(tmp_path: Path) -> None:
    """Accept one correctly named combined package."""
    asset = _write_package(tmp_path, nuke_line="17.0", optix_version="9.1")
    assert _validate(tmp_path) == [asset]


def test_validate_release_rejects_wrong_source_commit(tmp_path: Path) -> None:
    """Reject packages produced from another Git revision."""
    _write_package(tmp_path, nuke_line="17.0", optix_version="9.1")
    with pytest.raises(ValueError, match="another commit"):
        _validate(tmp_path, source_commit="different")


def test_validate_release_rejects_tampered_optix_binary(tmp_path: Path) -> None:
    """Reject an OptiX DLL that does not match its manifest digest."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="HOptixDenoise.*SHA-256"):
        _validate(tmp_path)


def test_validate_release_rejects_tampered_oidn_binary(tmp_path: Path) -> None:
    """Reject an OIDN node DLL that does not match its manifest digest."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        oidn_node_overrides={"sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="HOidnDenoise.*SHA-256"):
        _validate(tmp_path)


def test_validate_release_rejects_missing_oidn_node(tmp_path: Path) -> None:
    """Require the live OIDN node in every production package."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        include_oidn_binary=False,
    )
    with pytest.raises(ValueError, match="HOidnDenoise.dll"):
        _validate(tmp_path)


def test_validate_release_rejects_direct_oidn_linkage(tmp_path: Path) -> None:
    """Keep OIDN isolated from Nuke's private C++ runtime."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        oidn_node_overrides={
            "dependencies": ["DDImage.dll", "OpenImageDenoise.dll"]
        },
    )
    with pytest.raises(ValueError, match="isolating"):
        _validate(tmp_path)


def test_validate_release_rejects_missing_oidn_cuda_runtime(tmp_path: Path) -> None:
    """Require the exact CUDA-only OIDN runtime set."""
    runtime_names = set(VALIDATOR.EXPECTED_OIDN_RUNTIME_DLLS)
    runtime_names.remove("OpenImageDenoise_device_cuda.dll")
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        runtime_names=runtime_names,
    )
    with pytest.raises(ValueError, match="OpenImageDenoise_device_cuda.dll"):
        _validate(tmp_path)


def test_validate_release_rejects_unvalidated_package(tmp_path: Path) -> None:
    """Reject a package built with Nuke render validation disabled."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        validated=False,
    )
    with pytest.raises(ValueError, match="did not complete Nuke render validation"):
        _validate(tmp_path)


def test_validate_release_rejects_cudart_dependency(tmp_path: Path) -> None:
    """Reject an OptiX node linked to the CUDA Runtime DLL."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        dependencies=["DDImage.dll", "nvcuda.dll", "cudart64_12.dll"],
    )
    with pytest.raises(ValueError, match="CUDA Runtime DLLs"):
        _validate(tmp_path)


def test_validate_release_rejects_missing_optix_dependencies(tmp_path: Path) -> None:
    """Reject packages missing the Nuke or CUDA Driver import."""
    for dependencies, expected in (
        (["nvcuda.dll", "KERNEL32.dll"], "DDImage.dll"),
        (["DDImage.dll", "KERNEL32.dll"], "nvcuda.dll"),
    ):
        package_dir = tmp_path / expected
        package_dir.mkdir()
        _write_package(
            package_dir,
            nuke_line="17.0",
            optix_version="9.1",
            dependencies=dependencies,
        )
        with pytest.raises(ValueError, match=expected):
            _validate(package_dir)


def test_validate_release_rejects_binary_size_mismatch(tmp_path: Path) -> None:
    """Reject an OptiX DLL size that differs from its manifest."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        size=999,
    )
    with pytest.raises(ValueError, match="size"):
        _validate(tmp_path)


def test_validate_supported_matrix(tmp_path: Path) -> None:
    """Accept the complete four-by-three combined package matrix."""
    for nuke_line in VALIDATOR.SUPPORTED_NUKE_LINES:
        for optix_version in VALIDATOR.SUPPORTED_OPTIX_VERSIONS:
            _write_package(
                tmp_path,
                nuke_line=nuke_line,
                optix_version=optix_version,
            )

    result = VALIDATOR.validate_release_assets(
        assets_dir=tmp_path,
        build_scope="supported-matrix",
        release_tag="nuke-optix-v2.0.1",
        source_commit="abc123",
    )
    assert len(result) == 12


def test_validate_supported_matrix_rejects_duplicate_pair(tmp_path: Path) -> None:
    """Reject two packages targeting the same Nuke and OptiX pair."""
    for nuke_line in VALIDATOR.SUPPORTED_NUKE_LINES:
        for optix_version in VALIDATOR.SUPPORTED_OPTIX_VERSIONS:
            if (nuke_line, optix_version) != ("14.1", "8.1"):
                _write_package(
                    tmp_path,
                    nuke_line=nuke_line,
                    optix_version=optix_version,
                )
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        version="2.0.2",
    )

    with pytest.raises(ValueError, match="Duplicate Nuke/OptiX package pair"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="supported-matrix",
            release_tag="nuke-optix-v2.0.1",
            source_commit="abc123",
        )


def test_validate_supported_matrix_rejects_unsupported_package(
    tmp_path: Path,
) -> None:
    """Reject a matrix containing an unsupported Nuke binary line."""
    for nuke_line in VALIDATOR.SUPPORTED_NUKE_LINES:
        for optix_version in VALIDATOR.SUPPORTED_OPTIX_VERSIONS:
            if (nuke_line, optix_version) != ("14.1", "8.1"):
                _write_package(
                    tmp_path,
                    nuke_line=nuke_line,
                    optix_version=optix_version,
                )
    _write_package(tmp_path, nuke_line="16.0", optix_version="8.1")

    with pytest.raises(ValueError, match="Unsupported Nuke binary line"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="supported-matrix",
            release_tag="nuke-optix-v2.0.1",
            source_commit="abc123",
        )


def test_validate_release_rejects_version_tag_mismatch(tmp_path: Path) -> None:
    """Keep release tags aligned with the embedded project version."""
    _write_package(tmp_path, nuke_line="17.0", optix_version="9.1")
    with pytest.raises(ValueError, match="Release tag must be"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="single",
            release_tag="nuke-optix-v9.9.9",
            source_commit="abc123",
        )
