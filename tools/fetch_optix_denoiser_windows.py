"""Fetch and validate packaged OptiX denoiser variants on Windows."""

from __future__ import annotations

import argparse
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
) -> None:
    """Validate a packaged executable and its manifest."""
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

    if not allow_source_key_mismatch:
        actual_key = manifest.get("source_key")
        if actual_key != expected_key:
            raise RuntimeError(
                f"OptiX {version} source key mismatch: "
                f"expected {expected_key}, got {actual_key}"
            )


def find_extracted_bundle(extract_root: Path) -> Path:
    """Locate the single directory containing the executable and manifest."""
    executable_paths = list(extract_root.rglob("Denoiser.exe"))
    manifest_paths = list(extract_root.rglob("manifest.json"))
    if len(executable_paths) != 1 or len(manifest_paths) != 1:
        raise RuntimeError("Archive must contain one Denoiser.exe and one manifest.json")
    if executable_paths[0].parent != manifest_paths[0].parent:
        raise RuntimeError("Denoiser.exe and manifest.json must share a directory")
    return executable_paths[0].parent


def acquire_asset(
    destination: Path,
    name: str,
    *,
    repository: str,
    tag: str,
) -> None:
    """Copy an injected local asset or download it with GitHub CLI."""
    local_zip_dir = os.environ.get("HDU_OPTIX_DENOISER_ZIP_DIR")
    if local_zip_dir:
        local_asset = Path(local_zip_dir) / name
        if not local_asset.is_file():
            raise FileNotFoundError(f"HDU_OPTIX_DENOISER_ZIP_DIR is missing {name}")
        shutil.copy2(local_asset, destination)
        return

    github_cli = shutil.which("gh.exe") or shutil.which("gh")
    if not github_cli:
        raise FileNotFoundError("GitHub CLI was not found and no local ZIP directory was set")
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
            str(destination.parent),
        ],
        check=True,
    )
    if not destination.is_file():
        raise FileNotFoundError(f"Downloaded denoiser asset was not found: {destination}")


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
    for version in versions:
        variant_dir = vendor_dir / f"optix-{version}"
        try:
            validate_bundle(
                variant_dir,
                version,
                keys[version],
                allow_source_key_mismatch=args.allow_source_key_mismatch,
            )
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            print(f"Existing OptiX {version} bundle requires refresh: {error}")
            installed = False
            break
    if installed:
        remove_legacy_files(vendor_dir)
        print(f"Bundled OptiX denoiser variants already exist under: {vendor_dir}")
        return 0

    vendor_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hdu-optix-denoiser-") as temporary:
        temporary_dir = Path(temporary)
        for version in versions:
            name = asset_name(version, keys[version])
            archive_path = temporary_dir / name
            acquire_asset(
                archive_path,
                name,
                repository=args.repository,
                tag=args.tag,
            )
            extract_root = temporary_dir / f"extract-{version}"
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_root)
            bundle_dir = find_extracted_bundle(extract_root)
            validate_bundle(
                bundle_dir,
                version,
                keys[version],
                allow_source_key_mismatch=args.allow_source_key_mismatch,
            )
            destination = vendor_dir / f"optix-{version}"
            install_bundle(bundle_dir, destination)
            print(f"Bundled OptiX {version} denoiser installed: {destination / 'Denoiser.exe'}")

    remove_legacy_files(vendor_dir)
    write_summary(
        vendor_dir,
        versions,
        keys,
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
