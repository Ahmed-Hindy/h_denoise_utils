"""Fetch and validate packaged OptiX denoiser variants on Windows."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__:
    from .optix_source_key import (
        OPTIX_COMMITS,
        WINDOWS_PLATFORM,
        sha256_file,
        source_key,
    )
else:
    from optix_source_key import (  # type: ignore[no-redef]
        OPTIX_COMMITS,
        WINDOWS_PLATFORM,
        sha256_file,
        source_key,
    )

PLATFORM = WINDOWS_PLATFORM
DEFAULT_REPOSITORY = "Ahmed-Hindy/h_denoise_utils"
DEFAULT_TAG = "optix-denoiser-v2026.05.21"
CONTRACT = "optix-compatible-multipart-v1"


def asset_name(version: str, key: str) -> str:
    """Return the source-keyed release asset name."""
    return f"optix-denoiser-{PLATFORM}-optix-{version}-{key[:12]}.zip"


def validate_bundle(
    bundle_dir: Path,
    version: str,
    expected_key: str,
    *,
    allow_source_key_mismatch: bool,
) -> dict[str, object]:
    """Validate a packaged executable and return its manifest."""
    executable_path = bundle_dir / "Denoiser.exe"
    manifest_path = bundle_dir / "manifest.json"
    if not executable_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            f"OptiX {version} bundle must contain Denoiser.exe and manifest.json"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_fields = {
        "name": "hdu-optix-denoiser",
        "executable": "Denoiser.exe",
        "optix_version": version,
        "optix_dev_commit": OPTIX_COMMITS[version],
        "platform": PLATFORM,
        "contract": CONTRACT,
    }
    for field, expected in expected_fields.items():
        actual = manifest.get(field)
        if actual != expected:
            raise RuntimeError(
                f"OptiX {version} manifest {field} mismatch: "
                f"expected {expected!r}, got {actual!r}"
            )

    actual_hash = sha256_file(executable_path)
    if actual_hash.lower() != str(manifest.get("sha256", "")).lower():
        raise RuntimeError(f"OptiX {version} executable SHA-256 mismatch")

    actual_key = manifest.get("source_key")
    if not isinstance(actual_key, str) or not actual_key:
        raise RuntimeError(f"OptiX {version} manifest is missing source_key")
    if not allow_source_key_mismatch and actual_key != expected_key:
        raise RuntimeError(
            f"OptiX {version} source key mismatch: "
            f"expected {expected_key}, got {actual_key}"
        )
    return manifest


def find_extracted_bundle(extract_root: Path) -> Path:
    """Locate the single directory containing the executable and manifest."""
    executable_paths = list(extract_root.rglob("Denoiser.exe"))
    manifest_paths = list(extract_root.rglob("manifest.json"))
    if len(executable_paths) != 1 or len(manifest_paths) != 1:
        raise RuntimeError("Archive must contain one Denoiser.exe and one manifest.json")
    if executable_paths[0].parent != manifest_paths[0].parent:
        raise RuntimeError("Denoiser.exe and manifest.json must share a directory")
    return executable_paths[0].parent


def _latest_local_asset(directory: Path, pattern: str) -> Path:
    """Return the newest local asset matching a filename pattern."""
    matches = [path for path in directory.glob(pattern) if path.is_file()]
    if not matches:
        raise FileNotFoundError(
            f"HDU_OPTIX_DENOISER_ZIP_DIR has no asset matching {pattern}"
        )
    return max(matches, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _latest_release_asset(
    github_cli: str,
    *,
    repository: str,
    tag: str,
    pattern: str,
) -> str:
    """Return the newest release asset name matching a filename pattern."""
    result = subprocess.run(
        [
            github_cli,
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "assets",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assets = json.loads(result.stdout).get("assets", [])
    matches = [
        asset
        for asset in assets
        if fnmatch.fnmatchcase(str(asset.get("name", "")), pattern)
    ]
    if not matches:
        raise FileNotFoundError(
            f"Release {tag} has no denoiser asset matching {pattern}"
        )
    selected = max(
        matches,
        key=lambda asset: (
            str(asset.get("updatedAt") or asset.get("createdAt") or ""),
            str(asset.get("name", "")),
        ),
    )
    return str(selected["name"])


def acquire_asset(
    destination_dir: Path,
    pattern: str,
    *,
    repository: str,
    tag: str,
) -> Path:
    """Copy or download the newest asset matching a filename pattern."""
    local_zip_dir = os.environ.get("HDU_OPTIX_DENOISER_ZIP_DIR")
    if local_zip_dir:
        local_asset = _latest_local_asset(Path(local_zip_dir), pattern)
        destination = destination_dir / local_asset.name
        shutil.copy2(local_asset, destination)
        return destination

    github_cli = shutil.which("gh.exe") or shutil.which("gh")
    if not github_cli:
        raise FileNotFoundError("GitHub CLI was not found and no local ZIP directory was set")
    name = _latest_release_asset(
        github_cli,
        repository=repository,
        tag=tag,
        pattern=pattern,
    )
    subprocess.run(
        [
            github_cli,
            "release",
            "download",
            tag,
            "--repo",
            repository,
            "--pattern",
            name,
            "--dir",
            str(destination_dir),
        ],
        check=True,
    )
    destination = destination_dir / name
    if not destination.is_file():
        raise FileNotFoundError(f"Downloaded denoiser asset was not found: {destination}")
    return destination


def install_bundle(source: Path, destination: Path) -> None:
    """Replace one installed OptiX variant atomically enough for CI packaging."""
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)


def remove_legacy_files(vendor_dir: Path) -> None:
    """Remove obsolete single-variant files from the vendor root."""
    for name in ("Denoiser.exe", "manifest.json", "LICENSE"):
        path = vendor_dir / name
        if path.is_file():
            path.unlink()


def write_summary(
    vendor_dir: Path,
    versions: list[str],
    keys: dict[str, str],
    *,
    repository: str,
    tag: str,
) -> None:
    """Write the multi-variant vendor manifest."""
    summary = {
        "release_repository": f"https://github.com/{repository}",
        "release_tag": tag,
        "default_optix_version": "9.0",
        "variants": [
            {
                "optix_version": version,
                "optix_dev_commit": OPTIX_COMMITS[version],
                "source_key": keys[version],
                "executable": f"optix-{version}/Denoiser.exe",
                "manifest": f"optix-{version}/manifest.json",
            }
            for version in versions
        ],
    }
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / "manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument(
        "--optix-version",
        action="append",
        choices=OPTIX_COMMITS,
        dest="optix_versions",
        help="Fetch one version; repeat for multiple versions. Defaults to all.",
    )
    parser.add_argument(
        "--configuration",
        choices=("Release", "RelWithDebInfo", "Debug"),
        default="Release",
    )
    parser.add_argument("--allow-source-key-mismatch", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Fetch, validate, and install requested Windows OptiX variants."""
    if os.name != "nt":
        raise RuntimeError("This fetch script supports Windows only")
    args = parse_args()
    versions = args.optix_versions or list(OPTIX_COMMITS)
    repo_root = Path(__file__).resolve().parents[1]
    vendor_dir = (
        repo_root / "h_denoise_utils" / "vendor" / "optix-denoiser" / PLATFORM
    )
    keys = {
        version: source_key(
            repo_root,
            version,
            OPTIX_COMMITS[version],
            PLATFORM,
            args.configuration,
        )
        for version in versions
    }

    installed = True
    installed_keys: dict[str, str] = {}
    for version in versions:
        variant_dir = vendor_dir / f"optix-{version}"
        try:
            manifest = validate_bundle(
                variant_dir,
                version,
                keys[version],
                allow_source_key_mismatch=args.allow_source_key_mismatch,
            )
            installed_keys[version] = str(manifest["source_key"])
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            print(f"Existing OptiX {version} bundle requires refresh: {error}")
            installed = False
            break
    if installed:
        remove_legacy_files(vendor_dir)
        write_summary(
            vendor_dir,
            versions,
            installed_keys,
            repository=args.repository,
            tag=args.tag,
        )
        print(f"Bundled OptiX denoiser variants already exist under: {vendor_dir}")
        return 0

    vendor_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hdu-optix-denoiser-") as temporary:
        temporary_dir = Path(temporary)
        installed_keys = {}
        for version in versions:
            name = asset_name(version, keys[version])
            pattern = (
                f"optix-denoiser-{PLATFORM}-optix-{version}-*.zip"
                if args.allow_source_key_mismatch
                else name
            )
            archive_path = acquire_asset(
                temporary_dir,
                pattern,
                repository=args.repository,
                tag=args.tag,
            )
            extract_root = temporary_dir / f"extract-{version}"
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_root)
            bundle_dir = find_extracted_bundle(extract_root)
            manifest = validate_bundle(
                bundle_dir,
                version,
                keys[version],
                allow_source_key_mismatch=args.allow_source_key_mismatch,
            )
            installed_keys[version] = str(manifest["source_key"])
            destination = vendor_dir / f"optix-{version}"
            install_bundle(bundle_dir, destination)
            print(f"Bundled OptiX {version} denoiser installed: {destination / 'Denoiser.exe'}")

    remove_legacy_files(vendor_dir)
    write_summary(
        vendor_dir,
        versions,
        installed_keys,
        repository=args.repository,
        tag=args.tag,
    )
    print(f"Bundled OptiX denoiser variants installed under: {vendor_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
