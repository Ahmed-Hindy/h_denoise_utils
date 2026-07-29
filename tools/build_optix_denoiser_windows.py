"""Build and package the standalone OptiX denoiser on Windows."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
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

CUDA_MANIFEST_URL = (
    "https://developer.download.nvidia.com/compute/cuda/redist/"
    "redistrib_12.9.1.json"
)
CUDA_REDIST_BASE_URL = "https://developer.download.nvidia.com/compute/cuda/redist"
PLATFORM = WINDOWS_PLATFORM


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    """Run a native command and fail when it exits unsuccessfully."""
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def find_visual_studio() -> Path:
    """Return the latest Visual Studio installation with the x64 C++ toolchain."""
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    vswhere = program_files_x86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise FileNotFoundError("Visual Studio Installer's vswhere.exe was not found")
    result = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    installation_text = result.stdout.strip()
    if not installation_text:
        raise RuntimeError("Visual Studio with the C++ x64 toolchain was not found")
    installation = Path(installation_text)
    if not installation.is_dir():
        raise RuntimeError("Visual Studio with the C++ x64 toolchain was not found")
    return installation


def visual_studio_environment(vs_root: Path) -> dict[str, str]:
    """Return an x64 Visual Studio developer environment."""
    dev_cmd = vs_root / "Common7" / "Tools" / "VsDevCmd.bat"
    command = f'call "{dev_cmd}" -arch=x64 -host_arch=x64 >nul && set'
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        shell=True,
        executable=os.environ.get("COMSPEC", "cmd.exe"),
    )
    environment = dict(os.environ)
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            environment[key] = value

    path_entries = [
        entry
        for entry in environment.get("PATH", "").split(os.pathsep)
        if entry and "msys64" not in entry.lower().replace("/", "\\")
    ]
    environment["PATH"] = os.pathsep.join(path_entries)
    for name in (
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "C_INCLUDE_PATH",
        "CPLUS_INCLUDE_PATH",
        "LIBRARY_PATH",
        "PKG_CONFIG_PATH",
    ):
        environment.pop(name, None)
    return environment


def short_path(path: Path) -> Path:
    """Return a Windows 8.3 short path when available."""
    command = f'for %I in ("{path}") do @echo %~sI'
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        shell=True,
        executable=os.environ.get("COMSPEC", "cmd.exe"),
    )
    resolved = result.stdout.strip()
    if not resolved:
        raise RuntimeError(f"Could not resolve a short path for {path}")
    return Path(resolved)


def sync_optix_headers(destination: Path, commit: str) -> None:
    """Fetch the pinned NVIDIA optix-dev commit."""
    if not (destination / ".git").is_dir():
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/NVIDIA/optix-dev.git",
                str(destination),
            ]
        )
    run(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", commit])
    run(["git", "-C", str(destination), "checkout", "--force", commit])
    if not (destination / "include" / "optix.h").is_file():
        raise FileNotFoundError("OptiX headers were not fetched correctly")


def sync_cuda_driver_files(dependency_root: Path) -> Path:
    """Fetch only cuda.h and cuda.lib from NVIDIA's small CUDART archive."""
    with urllib.request.urlopen(CUDA_MANIFEST_URL) as response:
        manifest = json.load(response)
    package = manifest["cuda_cudart"]["windows-x86_64"]
    relative_path = package["relative_path"]
    archive_path = dependency_root / Path(relative_path).name
    extract_root = dependency_root / archive_path.stem
    dependency_root.mkdir(parents=True, exist_ok=True)

    if not archive_path.is_file():
        url = f"{CUDA_REDIST_BASE_URL}/{relative_path}"
        partial_path = archive_path.with_suffix(archive_path.suffix + ".part")
        partial_path.unlink(missing_ok=True)
        print("Downloading minimal CUDA driver headers and import library...", flush=True)
        try:
            urllib.request.urlretrieve(url, partial_path)
            partial_path.replace(archive_path)
        finally:
            partial_path.unlink(missing_ok=True)
    expected_hash = package.get("sha256", "").lower()
    if expected_hash and sha256_file(archive_path) != expected_hash:
        archive_path.unlink(missing_ok=True)
        shutil.rmtree(extract_root, ignore_errors=True)
        raise RuntimeError(f"CUDA redistributable SHA-256 mismatch: {archive_path}")
    def find_cuda_root() -> Path | None:
        for cuda_header in extract_root.rglob("include/cuda.h"):
            candidate = cuda_header.parent.parent
            if (candidate / "lib" / "x64" / "cuda.lib").is_file():
                return candidate
        return None

    existing_root = find_cuda_root()
    if existing_root is not None:
        return existing_root

    shutil.rmtree(extract_root, ignore_errors=True)
    with zipfile.ZipFile(archive_path) as archive:
        root = extract_root.resolve()
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root):
                raise RuntimeError(
                    f"CUDA archive member escapes destination: {member.filename}"
                )
        archive.extractall(root)

    extracted_root = find_cuda_root()
    if extracted_root is not None:
        return extracted_root
    shutil.rmtree(extract_root, ignore_errors=True)
    raise FileNotFoundError("cuda.h and cuda.lib were not found in the CUDA archive")


def locate_cuda_driver_files(dependency_root: Path) -> Path:
    """Locate a previously fetched CUDA redistributable root."""
    if dependency_root.is_dir():
        for cuda_header in dependency_root.rglob("include/cuda.h"):
            candidate = cuda_header.parent.parent
            if (candidate / "lib" / "x64" / "cuda.lib").is_file():
                return candidate
    raise FileNotFoundError("CUDA driver files are missing; omit --skip-dependency-fetch")


def executable(preferred: Path, fallback_name: str) -> str:
    """Resolve a preferred executable path or fall back to PATH."""
    if preferred.is_file():
        return str(preferred)
    resolved = shutil.which(fallback_name)
    if not resolved:
        raise FileNotFoundError(f"Required executable was not found: {fallback_name}")
    return resolved


def create_archive(bundle_root: Path, asset_path: Path) -> None:
    """Create a ZIP containing the packaged denoiser files."""
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.unlink(missing_ok=True)
    with zipfile.ZipFile(asset_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(bundle_root.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(bundle_root).as_posix())


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--optix-version", choices=OPTIX_COMMITS, default="9.1")
    parser.add_argument(
        "--configuration",
        choices=("Release", "RelWithDebInfo", "Debug"),
        default="Release",
    )
    parser.add_argument("--skip-dependency-fetch", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Build, install, and package the Windows OptiX denoiser."""
    if os.name != "nt":
        raise RuntimeError("This build script supports Windows only")
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    native_dir = repo_root / "native" / "optix-denoiser"
    optix_root = native_dir / "contrib" / "optix"
    dependency_root = repo_root / "build" / "deps"
    build_root = (
        repo_root
        / "build"
        / "optix-denoiser"
        / PLATFORM
        / f"optix-{args.optix_version}"
    )
    bundle_root = (
        repo_root
        / "h_denoise_utils"
        / "vendor"
        / "optix-denoiser"
        / PLATFORM
        / f"optix-{args.optix_version}"
    )
    profile = native_dir / "profiles" / "windows-cmake-3.28"
    optix_commit = OPTIX_COMMITS[args.optix_version]

    if args.skip_dependency_fetch:
        cuda_root = locate_cuda_driver_files(dependency_root / "cuda-redist")
    else:
        sync_optix_headers(optix_root, optix_commit)
        cuda_root = sync_cuda_driver_files(dependency_root / "cuda-redist")

    vs_root = find_visual_studio()
    environment = visual_studio_environment(vs_root)
    environment["CONAN_HOME"] = str(short_path(Path.home()) / ".conan2")
    cmake = executable(
        vs_root
        / "Common7"
        / "IDE"
        / "CommonExtensions"
        / "Microsoft"
        / "CMake"
        / "CMake"
        / "bin"
        / "cmake.exe",
        "cmake.exe",
    )
    ninja = executable(
        vs_root
        / "Common7"
        / "IDE"
        / "CommonExtensions"
        / "Microsoft"
        / "CMake"
        / "Ninja"
        / "ninja.exe",
        "ninja.exe",
    )
    uv = shutil.which("uv.exe") or shutil.which("uv")
    if not uv:
        raise FileNotFoundError("uv was not found")
    environment["PATH"] = os.pathsep.join(
        [str(Path(cmake).parent), str(Path(ninja).parent), environment["PATH"]]
    )

    shutil.rmtree(build_root, ignore_errors=True)
    shutil.rmtree(bundle_root, ignore_errors=True)
    build_root.mkdir(parents=True)
    bundle_root.mkdir(parents=True)

    run(
        [uv, "--system-certs", "run", "--with", "conan", "conan", "profile", "detect", "--force"],
        cwd=native_dir,
        env=environment,
    )
    run(
        [
            uv,
            "--system-certs",
            "run",
            "--with",
            "conan",
            "conan",
            "install",
            ".",
            "--output-folder",
            str(build_root),
            "--profile:host=default",
            f"--profile:host={profile}",
            "--profile:build=default",
            f"--profile:build={profile}",
            "--build=missing",
            "-s",
            f"build_type={args.configuration}",
            "-s",
            "compiler.cppstd=20",
        ],
        cwd=native_dir,
        env=environment,
    )
    toolchains = list(build_root.rglob("conan_toolchain.cmake"))
    if not toolchains:
        raise FileNotFoundError("Conan toolchain was not created")
    toolchain = toolchains[0]
    run(
        [
            cmake,
            "-S",
            str(native_dir),
            "-B",
            str(build_root),
            "-G",
            "Ninja",
            f"-DCMAKE_MAKE_PROGRAM={ninja}",
            f"-DCMAKE_BUILD_TYPE={args.configuration}",
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
            "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
            f"-DCUDA_REDIST_ROOT={cuda_root}",
            f"-DCMAKE_INSTALL_PREFIX={bundle_root}",
        ],
        env=environment,
    )
    run([cmake, "--build", str(build_root), "--target", "install"], env=environment)

    installed_exe = bundle_root / "bin" / "Denoiser.exe"
    executable_path = bundle_root / "Denoiser.exe"
    if installed_exe.is_file():
        installed_exe.replace(executable_path)
    if not executable_path.is_file():
        raise FileNotFoundError("Denoiser.exe was not installed")

    key = source_key(
        repo_root,
        args.optix_version,
        optix_commit,
        PLATFORM,
        args.configuration,
    )
    source_commit = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest = {
        "name": "hdu-optix-denoiser",
        "executable": "Denoiser.exe",
        "source_commit": source_commit,
        "source_key": key,
        "optix_version": args.optix_version,
        "optix_dev_commit": optix_commit,
        "platform": PLATFORM,
        "sha256": sha256_file(executable_path),
        "size": executable_path.stat().st_size,
        "contract": "optix-compatible-multipart-v1",
    }
    (bundle_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    license_path = native_dir / "LICENSE"
    if license_path.is_file():
        shutil.copy2(license_path, bundle_root / "LICENSE")

    asset_path = (
        repo_root
        / "dist"
        / f"optix-denoiser-{PLATFORM}-optix-{args.optix_version}-{key[:12]}.zip"
    )
    create_archive(bundle_root, asset_path)
    print(f"OptiX denoiser bundle created: {bundle_root}")
    print(f"OptiX denoiser asset created: {asset_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
