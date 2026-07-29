"""Validate HOptixDenoise packages before GitHub release publication."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

SUPPORTED_NUKE_LINES = ("14.1", "15.0", "15.1", "17.0")
SUPPORTED_OPTIX_VERSIONS = ("8.1", "9.0", "9.1")
EXPECTED_PACKAGE_COUNTS = {
    "single": 1,
    "supported-matrix": len(SUPPORTED_NUKE_LINES) * len(SUPPORTED_OPTIX_VERSIONS),
}


def _read_manifest(asset: Path) -> dict[str, Any]:
    """Read the single package manifest from a release ZIP.

    Args:
        asset: Path to an HOptixDenoise release ZIP.

    Returns:
        Parsed manifest data.

    Raises:
        ValueError: If the archive does not contain exactly one manifest.
    """
    with zipfile.ZipFile(asset) as archive:
        manifests = [
            name for name in archive.namelist() if name.endswith("/manifest.json")
        ]
        if len(manifests) != 1:
            raise ValueError(
                f"{asset.name} contains {len(manifests)} manifests; expected 1"
            )
        return json.loads(archive.read(manifests[0]))


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
        ValueError: If package count, metadata, filename, or matrix coverage is
            invalid.
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
        manifest = _read_manifest(asset)
        if manifest.get("source_commit") != source_commit:
            raise ValueError(f"{asset.name} was built from another commit")
        if manifest.get("stub") is not False:
            raise ValueError(f"{asset.name} is not a production package")
        if manifest.get("platform") != "windows-x64":
            raise ValueError(f"{asset.name} is not a Windows x64 package")

        version = _require_text(manifest, "version", asset)
        nuke_line = _require_text(manifest, "nuke_binary_version", asset)
        optix_version = _require_text(manifest, "optix_version", asset)
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
