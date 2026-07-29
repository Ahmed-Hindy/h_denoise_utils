"""Validate HOptixDenoise packages before GitHub release publication."""

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
EXPECTED_PACKAGE_COUNTS = {
    "single": 1,
    "supported-matrix": len(SUPPORTED_NUKE_LINES) * len(SUPPORTED_OPTIX_VERSIONS),
}


def _read_package(asset: Path) -> tuple[dict[str, Any], bytes]:
    """Read the manifest and plugin binary from a release ZIP.

    Args:
        asset: Path to an HOptixDenoise release ZIP.

    Returns:
        Parsed manifest data and packaged DLL bytes.

    Raises:
        ValueError: If the archive does not contain exactly one manifest and
            one plugin DLL.
    """
    with zipfile.ZipFile(asset) as archive:
        manifests = [
            name for name in archive.namelist() if name.endswith("/manifest.json")
        ]
        binaries = [
            name
            for name in archive.namelist()
            if name.endswith("/HOptixDenoise.dll")
        ]
        if len(manifests) != 1:
            raise ValueError(
                f"{asset.name} contains {len(manifests)} manifests; expected 1"
            )
        if len(binaries) != 1:
            raise ValueError(
                f"{asset.name} contains {len(binaries)} plugin DLLs; expected 1"
            )
        return json.loads(archive.read(manifests[0])), archive.read(binaries[0])


def _require_text(manifest: dict[str, Any], key: str, asset: Path) -> str:
    """Return a required non-empty manifest string.

    Args:
        manifest: Parsed package manifest.
        key: Manifest key to retrieve.
        asset: Package path used in error messages.

    Returns:
        Non-empty manifest value.

    Raises:
        ValueError: If the value is absent or not a non-empty string.
    """
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{asset.name} has an invalid {key!r} manifest value")
    return value


def _validate_binary(
    manifest: dict[str, Any],
    binary: bytes,
    asset: Path,
) -> None:
    """Verify the packaged DLL against its manifest digest and size.

    Args:
        manifest: Parsed package manifest.
        binary: Packaged plugin DLL bytes.
        asset: Package path used in error messages.

    Raises:
        ValueError: If the recorded size or SHA-256 digest is invalid.
    """
    expected_size = manifest.get("size")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size != len(binary)
    ):
        raise ValueError(f"{asset.name} DLL size does not match its manifest")

    expected_hash = _require_text(manifest, "sha256", asset).lower()
    actual_hash = hashlib.sha256(binary).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"{asset.name} DLL SHA-256 does not match its manifest")


def validate_release_assets(
    assets_dir: Path,
    build_scope: str,
    release_tag: str,
    source_commit: str,
) -> list[Path]:
    """Validate packages selected for one HOptixDenoise release.

    Args:
        assets_dir: Directory containing downloaded ZIP artifacts.
        build_scope: Either ``single`` or ``supported-matrix``.
        release_tag: Requested GitHub release tag.
        source_commit: Commit expected in every package manifest.

    Returns:
        Sorted validated package paths.

    Raises:
        ValueError: If package count, metadata, filename, binary integrity, or
            matrix coverage is invalid.
    """
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
        manifest, binary = _read_package(asset)
        _validate_binary(manifest, binary, asset)

        if manifest.get("name") != "HOptixDenoise":
            raise ValueError(f"{asset.name} has an unexpected package name")
        if manifest.get("source_commit") != source_commit:
            raise ValueError(f"{asset.name} was built from another commit")
        if manifest.get("stub") is not False:
            raise ValueError(f"{asset.name} is not a production package")
        if manifest.get("platform") != "windows-x64":
            raise ValueError(f"{asset.name} is not a Windows x64 package")
        if manifest.get("build_configuration") != "Release":
            raise ValueError(f"{asset.name} is not a Release build")

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

        pair = (nuke_line, optix_version)
        if pair in package_pairs:
            raise ValueError(f"Duplicate Nuke/OptiX package pair: {pair}")
        package_pairs.add(pair)
        versions.add(version)

    if len(versions) != 1:
        raise ValueError(f"Release packages have inconsistent versions: {versions}")
    expected_tag = f"nuke-optix-v{next(iter(versions))}"
    if release_tag != expected_tag:
        raise ValueError(f"Release tag must be {expected_tag}, got {release_tag}")

    if build_scope == "supported-matrix":
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
