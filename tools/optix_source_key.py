"""Calculate stable source keys for standalone OptiX denoiser assets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

OPTIX_COMMITS = {
    "8.1": "50021ea0af6d41609a97777ceebbdf1e1d34efe7",
    "9.0": "fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd",
    "9.1": "f1f6dd803f3159992d248178f6e09421c6eb8b6d",
}
WINDOWS_PLATFORM = "windows-x64"
LINUX_PLATFORM = "linux-x64"
COMMON_SOURCE_KEY_INPUTS = (
    "native/optix-denoiser/CMakeLists.txt",
    "native/optix-denoiser/conanfile.txt",
    "native/optix-denoiser/cmake",
    "native/optix-denoiser/include",
    "native/optix-denoiser/src",
    "tools/optix_source_key.py",
)
PLATFORM_SOURCE_KEY_INPUTS = {
    WINDOWS_PLATFORM: (
        "native/optix-denoiser/profiles",
        "tools/build_optix_denoiser_windows.py",
    ),
    LINUX_PLATFORM: ("tools/build_optix_denoiser.sh",),
}


def source_key_inputs(platform: str) -> tuple[str, ...]:
    """Return common and platform-specific inputs for one native asset key."""
    try:
        platform_inputs = PLATFORM_SOURCE_KEY_INPUTS[platform]
    except KeyError as error:
        raise ValueError(f"Unsupported source-key platform: {platform}") from error
    return COMMON_SOURCE_KEY_INPUTS + platform_inputs


def sha256_file(path: Path) -> str:
    """Return the lowercase byte-exact SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_source_file(path: Path) -> str:
    """Hash source text consistently across LF and CRLF checkouts."""
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def source_key(
    repo_root: Path,
    optix_version: str,
    optix_commit: str,
    platform: str,
    configuration: str,
) -> str:
    """Calculate a deterministic key for all native denoiser source inputs."""
    payload = [
        f"optix_version={optix_version}",
        f"optix_dev_commit={optix_commit}",
        f"platform={platform}",
        f"configuration={configuration}",
    ]
    for relative in source_key_inputs(platform):
        input_path = repo_root / relative
        if not input_path.exists():
            raise FileNotFoundError(f"Source-key input is missing: {input_path}")
        files = sorted(input_path.rglob("*")) if input_path.is_dir() else [input_path]
        for file_path in files:
            if not file_path.is_file():
                continue
            file_relative = file_path.relative_to(repo_root).as_posix()
            payload.append(f"{file_relative}={sha256_source_file(file_path)}")
    return hashlib.sha256("\n".join(payload).encode()).hexdigest()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--optix-version", choices=OPTIX_COMMITS, required=True)
    parser.add_argument("--optix-commit", required=True)
    parser.add_argument(
        "--platform", choices=(WINDOWS_PLATFORM, LINUX_PLATFORM), required=True
    )
    parser.add_argument("--configuration", required=True)
    return parser.parse_args()


def main() -> int:
    """Print one source key for shell build and fetch scripts."""
    args = parse_args()
    print(
        source_key(
            args.repo_root.resolve(),
            args.optix_version,
            args.optix_commit,
            args.platform,
            args.configuration,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
