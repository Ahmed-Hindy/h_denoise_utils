"""Validate combined OptiX and OIDN Nuke packages before publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

SUPPORTED_NUKE_REVISIONS = {
    "14.1": "14.1v8",
    "15.0": "15.0v1",
    "15.1": "15.1v4",
    "17.0": "17.0v3",
}
SUPPORTED_OPTIX_COMMITS = {
    "8.1": "50021ea0af6d41609a97777ceebbdf1e1d34efe7",
    "9.0": "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd",
    "9.1": "f1f6dd803f3159992d248178f6e09421c6eb8b6d",
}
SUPPORTED_NUKE_LINES = tuple(SUPPORTED_NUKE_REVISIONS)
SUPPORTED_OPTIX_VERSIONS = tuple(SUPPORTED_OPTIX_COMMITS)
EXPECTED_OIDN_VERSION = "2.5.0"
EXPECTED_OIDN_RUNTIME_DLLS = {
    "OpenImageDenoise.dll",
    "OpenImageDenoise_core.dll",
    "OpenImageDenoise_device_cuda.dll",
}
EXPECTED_PACKAGE_COUNTS = {
    "single": 1,
    "supported-matrix": len(SUPPORTED_NUKE_LINES) * len(SUPPORTED_OPTIX_VERSIONS),
}


def _read_unique(archive: zipfile.ZipFile, suffix: str, asset: Path) -> bytes:
    """Read exactly one archive member ending with ``suffix``."""
    matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(
            f"{asset.name} contains {len(matches)} entries ending in {suffix}; expected 1"
        )
    return archive.read(matches[0])


def _read_package(asset: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read the manifest and all security-sensitive package binaries."""
    with zipfile.ZipFile(asset) as archive:
        manifest = json.loads(_read_unique(archive, "/manifest.json", asset))
        files = {
            "HOptixDenoise.dll": _read_unique(
                archive, "/HOptixDenoise.dll", asset
            ),
            "HOidnDenoise.dll": _read_unique(archive, "/HOidnDenoise.dll", asset),
            "HOidnBridge.exe": _read_unique(archive, "/HOidnBridge.exe", asset),
        }
        for name in EXPECTED_OIDN_RUNTIME_DLLS:
            files[name] = _read_unique(archive, f"/{name}", asset)
        return manifest, files


def _require_text(manifest: dict[str, Any], key: str, asset: Path) -> str:
    """Return a required non-empty manifest string."""
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{asset.name} has an invalid {key!r} manifest value")
    return value


def _validate_file_record(
    record: dict[str, Any],
    binary: bytes,
    asset: Path,
    label: str,
) -> None:
    """Verify a packaged file against its recorded size and SHA-256."""
    expected_size = record.get("size")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size != len(binary)
    ):
        raise ValueError(f"{asset.name} {label} size does not match its manifest")

    expected_hash = record.get("sha256")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise ValueError(f"{asset.name} has an invalid {label} SHA-256")
    if hashlib.sha256(binary).hexdigest() != expected_hash.lower():
        raise ValueError(f"{asset.name} {label} SHA-256 does not match its manifest")


def _dependency_set(
    record: dict[str, Any],
    asset: Path,
    label: str,
) -> set[str]:
    """Return a normalized dependency set from a manifest record."""
    dependencies = record.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) and item for item in dependencies
    ):
        raise ValueError(f"{asset.name} has an invalid {label} dependency manifest")
    return {dependency.casefold() for dependency in dependencies}


def _validate_optix_binary(
    manifest: dict[str, Any],
    binary: bytes,
    asset: Path,
) -> None:
    """Validate the OptiX plugin binary and PE dependencies."""
    _validate_file_record(manifest, binary, asset, "HOptixDenoise.dll")
    dependencies = _dependency_set(manifest, asset, "OptiX plugin")
    if "ddimage.dll" not in dependencies:
        raise ValueError(f"{asset.name} does not import DDImage.dll")
    if "nvcuda.dll" not in dependencies:
        raise ValueError(f"{asset.name} does not import nvcuda.dll")
    cudart = sorted(
        dependency
        for dependency in dependencies
        if dependency.startswith("cudart") and dependency.endswith(".dll")
    )
    if cudart:
        raise ValueError(f"{asset.name} imports CUDA Runtime DLLs: {cudart}")


def _require_mapping(value: Any, asset: Path, label: str) -> dict[str, Any]:
    """Return a required manifest mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{asset.name} has an invalid {label} manifest")
    return value


def _validate_oidn_payload(
    manifest: dict[str, Any],
    files: dict[str, bytes],
    asset: Path,
) -> None:
    """Validate the isolated OIDN node, helper, and CUDA runtime payload."""
    if manifest.get("oidn_version") != EXPECTED_OIDN_VERSION:
        raise ValueError(
            f"{asset.name} must contain OIDN {EXPECTED_OIDN_VERSION}"
        )

    node = _require_mapping(manifest.get("oidn_node"), asset, "OIDN node")
    if node.get("name") != "HOidnDenoise":
        raise ValueError(f"{asset.name} has an unexpected OIDN node name")
    _validate_file_record(
        node,
        files["HOidnDenoise.dll"],
        asset,
        "HOidnDenoise.dll",
    )
    node_dependencies = _dependency_set(node, asset, "OIDN plugin")
    if "ddimage.dll" not in node_dependencies:
        raise ValueError(f"{asset.name} OIDN plugin does not import DDImage.dll")
    if "openimagedenoise.dll" in node_dependencies:
        raise ValueError(
            f"{asset.name} links OIDN directly into Nuke instead of isolating it"
        )

    helper = _require_mapping(node.get("helper"), asset, "OIDN helper")
    if helper.get("name") != "HOidnBridge.exe":
        raise ValueError(f"{asset.name} has an unexpected OIDN helper name")
    _validate_file_record(
        helper,
        files["HOidnBridge.exe"],
        asset,
        "HOidnBridge.exe",
    )
    helper_dependencies = _dependency_set(helper, asset, "OIDN helper")
    if "openimagedenoise.dll" not in helper_dependencies:
        raise ValueError(f"{asset.name} OIDN helper does not import OpenImageDenoise.dll")
    if "ddimage.dll" in helper_dependencies:
        raise ValueError(f"{asset.name} OIDN helper unexpectedly imports DDImage.dll")

    runtime_records = node.get("runtime_dlls")
    if not isinstance(runtime_records, list):
        raise ValueError(f"{asset.name} has an invalid OIDN runtime manifest")
    records_by_name: dict[str, dict[str, Any]] = {}
    for value in runtime_records:
        record = _require_mapping(value, asset, "OIDN runtime")
        name = record.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{asset.name} has an unnamed OIDN runtime DLL")
        if name in records_by_name:
            raise ValueError(f"{asset.name} repeats OIDN runtime DLL {name}")
        records_by_name[name] = record
    if set(records_by_name) != EXPECTED_OIDN_RUNTIME_DLLS:
        raise ValueError(
            f"{asset.name} has an unexpected OIDN runtime set: "
            f"{sorted(records_by_name)}"
        )
    for name, record in records_by_name.items():
        _validate_file_record(record, files[name], asset, name)


def _validate_package_manifest(
    manifest: dict[str, Any],
    asset: Path,
    source_commit: str,
) -> tuple[str, str, str]:
    """Validate production metadata and return compatibility fields."""
    expected_fields = {
        "name": ("HDenoiseNodes", "has an unexpected package name"),
        "source_commit": (source_commit, "was built from another commit"),
        "stub": (False, "is not a production package"),
        "validated": (True, "did not complete Nuke render validation"),
        "platform": ("windows-x64", "is not a Windows x64 package"),
        "build_configuration": ("Release", "is not a Release build"),
    }
    for field, (expected, message) in expected_fields.items():
        if manifest.get(field) != expected:
            raise ValueError(f"{asset.name} {message}")

    version = _require_text(manifest, "version", asset)
    nuke_line = _require_text(manifest, "nuke_binary_version", asset)
    optix_version = _require_text(manifest, "optix_version", asset)
    if nuke_line not in SUPPORTED_NUKE_REVISIONS:
        raise ValueError(f"Unsupported Nuke binary line in {asset.name}: {nuke_line}")
    if optix_version not in SUPPORTED_OPTIX_COMMITS:
        raise ValueError(f"Unsupported OptiX version in {asset.name}: {optix_version}")
    if manifest.get("nuke_version") != SUPPORTED_NUKE_REVISIONS[nuke_line]:
        raise ValueError(f"{asset.name} was built with the wrong Nuke revision")
    if manifest.get("optix_dev_commit") != SUPPORTED_OPTIX_COMMITS[optix_version]:
        raise ValueError(f"{asset.name} was built with the wrong OptiX commit")

    expected_name = (
        f"h-denoise-nuke-{nuke_line}-windows-x64-"
        f"optix-{optix_version}-v{version}.zip"
    )
    if asset.name != expected_name:
        raise ValueError(
            f"Package filename mismatch: expected {expected_name}, got {asset.name}"
        )
    return version, nuke_line, optix_version


def _validate_release_identity(versions: set[str], release_tag: str) -> None:
    """Require one package version and its matching GitHub release tag."""
    if len(versions) != 1:
        raise ValueError(f"Release packages have inconsistent versions: {versions}")
    expected_tag = f"nuke-optix-v{next(iter(versions))}"
    if release_tag != expected_tag:
        raise ValueError(f"Release tag must be {expected_tag}, got {release_tag}")


def _validate_supported_matrix(package_pairs: set[tuple[str, str]]) -> None:
    """Require every supported Nuke and OptiX combination exactly once."""
    expected_pairs = {
        (nuke_line, optix_version)
        for nuke_line in SUPPORTED_NUKE_LINES
        for optix_version in SUPPORTED_OPTIX_VERSIONS
    }
    if package_pairs != expected_pairs:
        missing = sorted(expected_pairs - package_pairs)
        unexpected = sorted(package_pairs - expected_pairs)
        raise ValueError(
            f"Invalid supported matrix; missing={missing}, unexpected={unexpected}"
        )


def validate_release_assets(
    assets_dir: Path,
    build_scope: str,
    release_tag: str,
    source_commit: str,
) -> list[Path]:
    """Validate packages selected for one combined Nuke denoiser release."""
    if build_scope not in EXPECTED_PACKAGE_COUNTS:
        raise ValueError(f"Unsupported build scope: {build_scope}")

    assets = sorted(assets_dir.glob("*.zip"))
    expected_count = EXPECTED_PACKAGE_COUNTS[build_scope]
    if len(assets) != expected_count:
        raise ValueError(
            f"Expected {expected_count} release package(s), found {len(assets)}"
        )

    versions: set[str] = set()
    package_pairs: set[tuple[str, str]] = set()
    for asset in assets:
        manifest, files = _read_package(asset)
        _validate_optix_binary(manifest, files["HOptixDenoise.dll"], asset)
        _validate_oidn_payload(manifest, files, asset)
        version, nuke_line, optix_version = _validate_package_manifest(
            manifest,
            asset,
            source_commit,
        )
        pair = (nuke_line, optix_version)
        if pair in package_pairs:
            raise ValueError(f"Duplicate Nuke/OptiX package pair: {pair}")
        package_pairs.add(pair)
        versions.add(version)

    _validate_release_identity(versions, release_tag)
    if build_scope == "supported-matrix":
        _validate_supported_matrix(package_pairs)
    return assets


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument(
        "--build-scope",
        choices=tuple(EXPECTED_PACKAGE_COUNTS),
        required=True,
    )
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


def main() -> int:
    """Validate downloaded packages and report the accepted count."""
    args = parse_args()
    try:
        assets = validate_release_assets(
            assets_dir=args.assets_dir,
            build_scope=args.build_scope,
            release_tag=args.release_tag,
            source_commit=args.source_commit,
        )
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(f"Validated {len(assets)} release package(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
