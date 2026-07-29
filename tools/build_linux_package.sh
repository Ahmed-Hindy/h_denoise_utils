#!/usr/bin/env bash
set -euo pipefail

VARIANT=""

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --variant)
      VARIANT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ -z "${VARIANT}" ]; then
  VARIANT="${HDU_PACKAGE_VARIANT:-}"
fi
if [ -z "${VARIANT}" ]; then
  VARIANT="bundled"
fi
if [ "${VARIANT}" != "bundled" ]; then
  echo "Invalid package variant '${VARIANT}'. Expected 'bundled'." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

invoke_frozen_executable_check() {
  local exe_path="$1"
  local check_name="$2"
  shift 2
  local args=("$@")

  if [ ! -f "${exe_path}" ]; then
    echo "Expected executable was not found for ${check_name}: ${exe_path}" >&2
    exit 1
  fi

  local stdout_path
  stdout_path=$(mktemp)
  local stderr_path
  stderr_path=$(mktemp)

  echo "Running ${check_name}..."
  set +e
  # Headless CI environment requires offscreen platform for Qt imports
  QT_QPA_PLATFORM=offscreen timeout 60 "${exe_path}" "${args[@]}" > "${stdout_path}" 2> "${stderr_path}"
  local exit_code=$?
  set -e

  if [ -f "${stdout_path}" ]; then
    cat "${stdout_path}"
  fi
  if [ -f "${stderr_path}" ]; then
    cat "${stderr_path}" >&2
  fi

  rm -f "${stdout_path}" "${stderr_path}"

  if [ ${exit_code} -eq 124 ]; then
    echo "${check_name} timed out after 60 seconds: ${exe_path} ${args[*]}" >&2
    exit 1
  fi

  if [ ${exit_code} -ne 0 ]; then
    echo "${check_name} failed with exit code ${exit_code}: ${exe_path} ${args[*]}" >&2
    exit 1
  fi
}

VERSION=$(grep -E '^version[[:space:]]*=[[:space:]]*"[^"]+"' pyproject.toml | head -n 1 | cut -d'"' -f2)
if [ -z "${VERSION}" ]; then
  echo "Could not read project version from pyproject.toml" >&2
  exit 1
fi

DIST_DIR="${REPO_ROOT}/dist"
APP_DIR="${DIST_DIR}/h-denoise"
BUILD_DIR="${REPO_ROOT}/build"
TAR_PATH="${DIST_DIR}/h-denoise-${VARIANT}-linux-x64-v${VERSION}.tar.gz"
SMOKE_ARGS=("--smoke-test" "--smoke-runtime" "all")
export HDU_PACKAGE_VARIANT="${VARIANT}"

OPTIX_DENOISER="${REPO_ROOT}/h_denoise_utils/vendor/optix-denoiser/linux-x64/optix-9.0/Denoiser"
if [ ! -f "${OPTIX_DENOISER}" ]; then
  echo "Bundled package requires the OptiX 9.0 Denoiser binary. Expected: ${OPTIX_DENOISER}" >&2
  exit 1
fi

OIDN_DENOISER="${REPO_ROOT}/h_denoise_utils/vendor/oidn-denoiser/linux-x64/oidn-2.5.0/Denoiser"
if [ ! -f "${OIDN_DENOISER}" ]; then
  echo "Bundled package requires the custom OIDN Denoiser binary. Expected: ${OIDN_DENOISER}" >&2
  exit 1
fi

# Clean prior builds
rm -rf "${APP_DIR}" "${BUILD_DIR}/pyinstaller"
find "${DIST_DIR}" -maxdepth 1 -name "h-denoise-${VARIANT}-linux-x64-v*.tar.gz" -exec rm -f {} +

# Run PyInstaller compilation
uv run --system-certs --frozen --extra pyside6 --extra package pyinstaller --noconfirm --clean "packaging/h-denoise.spec"

EXE_PATH="${APP_DIR}/h-denoise"
if [ ! -f "${EXE_PATH}" ]; then
  echo "Expected executable was not created: ${EXE_PATH}" >&2
  exit 1
fi

# Run smoke tests on the frozen build
invoke_frozen_executable_check "${EXE_PATH}" "dist-version" "--version"
invoke_frozen_executable_check "${EXE_PATH}" "dist-smoke-test" "${SMOKE_ARGS[@]}"

# Pack the portable directory into tar.gz
echo "Archiving to ${TAR_PATH}..."
rm -f "${TAR_PATH}"
cd "${DIST_DIR}"
tar -czf "${TAR_PATH}" h-denoise
cd "${REPO_ROOT}"

if [ ! -f "${TAR_PATH}" ]; then
  echo "Expected package was not created: ${TAR_PATH}" >&2
  exit 1
fi

# Extract and smoke-test the archive to verify package integrity
EXTRACT_DIR="${BUILD_DIR}/package-smoke-${VARIANT}-${VERSION}"
rm -rf "${EXTRACT_DIR}"
mkdir -p "${EXTRACT_DIR}"

tar -xzf "${TAR_PATH}" -C "${EXTRACT_DIR}"
EXTRACTED_EXE="${EXTRACT_DIR}/h-denoise/h-denoise"

invoke_frozen_executable_check "${EXTRACTED_EXE}" "tar-version" "--version"
invoke_frozen_executable_check "${EXTRACTED_EXE}" "tar-smoke-test" "${SMOKE_ARGS[@]}"

rm -rf "${EXTRACT_DIR}"
echo "Package successfully created and verified: ${TAR_PATH}"
