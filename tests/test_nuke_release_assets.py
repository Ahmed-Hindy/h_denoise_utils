"""Tests for Nuke release package validation."""

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


def _write_package(
    directory: Path,
    *,
    nuke_line: str,
    optix_version: str,
    version: str = "2.0.1",
    source_commit: str = "abc123",
    binary: bytes = b"native-plugin",
    **overrides: object,
) -> Path:
    """Create a minimal package ZIP with a production manifest."""
    manifest: dict[str, object] = {
        "name": "HOptixDenoise",
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
        "sha256": hashlib.sha256(binary).hexdigest(),
        "size": len(binary),
    }
    manifest.update(overrides)
    asset = directory / (
        f"h-denoise-nuke-{nuke_line}-windows-x64-"
        f"optix-{optix_version}-v{version}.zip"
    )
    with zipfile.ZipFile(asset, "w") as archive:
        archive.writestr(
            "HOptixDenoise/manifest.json",
            json.dumps(manifest),
        )
        archive.writestr("HOptixDenoise/HOptixDenoise.dll", binary)
    return asset


def test_validate_single_release_package(tmp_path: Path) -> None:
    """Accept one correctly named package from the requested commit."""
    asset = _write_package(tmp_path, nuke_line="17.0", optix_version="9.1")

    result = VALIDATOR.validate_release_assets(
        assets_dir=tmp_path,
        build_scope="single",
        release_tag="nuke-optix-v2.0.1",
        source_commit="abc123",
    )

    assert result == [asset]


def test_validate_release_rejects_wrong_source_commit(tmp_path: Path) -> None:
    """Reject packages produced from another Git revision."""
    _write_package(tmp_path, nuke_line="17.0", optix_version="9.1")

    with pytest.raises(ValueError, match="another commit"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="single",
            release_tag="nuke-optix-v2.0.1",
            source_commit="different",
        )


def test_validate_release_rejects_tampered_binary(tmp_path: Path) -> None:
    """Reject a package whose DLL does not match the manifest digest."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        sha256="0" * 64,
    )

    with pytest.raises(ValueError, match="SHA-256"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="single",
            release_tag="nuke-optix-v2.0.1",
            source_commit="abc123",
        )


def test_validate_release_rejects_unvalidated_package(tmp_path: Path) -> None:
    """Reject a package built with Nuke render validation disabled."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        validated=False,
    )

    with pytest.raises(ValueError, match="did not complete Nuke render validation"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="single",
            release_tag="nuke-optix-v2.0.1",
            source_commit="abc123",
        )


def test_validate_release_rejects_cudart_dependency(tmp_path: Path) -> None:
    """Reject a package that links the CUDA Runtime DLL."""
    _write_package(
        tmp_path,
        nuke_line="17.0",
        optix_version="9.1",
        dependencies=["DDImage.dll", "nvcuda.dll", "cudart64_12.dll"],
    )

    with pytest.raises(ValueError, match="CUDA Runtime DLLs"):
        VALIDATOR.validate_release_assets(
            assets_dir=tmp_path,
            build_scope="single",
            release_tag="nuke-optix-v2.0.1",
            source_commit="abc123",
        )


def test_validate_supported_matrix(tmp_path: Path) -> None:
    """Accept the complete four-by-three validated compatibility matrix."""
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


def test_validate_supported_matrix_rejects_unsupported_package(
    tmp_path: Path,
) -> None:
    """Reject a 12-file set containing an unsupported Nuke binary line."""
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
