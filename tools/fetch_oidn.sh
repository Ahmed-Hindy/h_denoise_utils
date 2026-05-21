#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="RenderKit/oidn"
VERSION="2.4.1"
TAG="v2.4.1"
PLATFORM="linux-x64"
ASSET_NAME="oidn-${VERSION}.x86_64.linux.tar.gz"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --asset-name)
      ASSET_NAME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ "$PLATFORM" != "linux-x64" ]; then
  echo "Unsupported OIDN platform '$PLATFORM'. This fetcher currently supports linux-x64." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENDOR_ROOT="${REPO_ROOT}/h_denoise_utils/vendor/oidn/${PLATFORM}"
INSTALL_DIR="${VENDOR_ROOT}/oidn-${VERSION}"

has_file_match() {
  compgen -G "$1" > /dev/null
}

# Check if already installed
if [ -f "${INSTALL_DIR}/bin/oidnDenoise" ] && \
   [ -f "${INSTALL_DIR}/lib/libOpenImageDenoise.so" ] && \
   has_file_match "${INSTALL_DIR}/lib/libOpenImageDenoise_core.so*" && \
   has_file_match "${INSTALL_DIR}/lib/libOpenImageDenoise_device_cpu.so*" && \
   [ -f "${INSTALL_DIR}/doc/LICENSE.txt" ]; then
  echo "Bundled OIDN runtime already exists under: ${INSTALL_DIR}"
  exit 0
fi

mkdir -p "${VENDOR_ROOT}"
DOWNLOAD_DIR=$(mktemp -d -t hdu-oidn-XXXXXX)

cleanup() {
  rm -rf "${DOWNLOAD_DIR}"
}
trap cleanup EXIT

ZIP_PATH="${DOWNLOAD_DIR}/${ASSET_NAME}"

if [ -n "${HDU_OIDN_ZIP_DIR:-}" ]; then
  if [ ! -f "${HDU_OIDN_ZIP_DIR}/${ASSET_NAME}" ]; then
    echo "HDU_OIDN_ZIP_DIR is missing ${ASSET_NAME}" >&2
    exit 1
  fi
  cp "${HDU_OIDN_ZIP_DIR}/${ASSET_NAME}" "${ZIP_PATH}"
else
  URL="https://github.com/${REPOSITORY}/releases/download/${TAG}/${ASSET_NAME}"
  echo "Downloading OIDN SDK from: ${URL}"
  curl -L -H "User-Agent: h_denoise_utils" -o "${ZIP_PATH}" "${URL}"
fi

if [ ! -f "${ZIP_PATH}" ]; then
  echo "Downloaded OIDN asset not found: ${ZIP_PATH}" >&2
  exit 1
fi

EXTRACT_DIR="${DOWNLOAD_DIR}/extract"
mkdir -p "${EXTRACT_DIR}"
tar -xzf "${ZIP_PATH}" -C "${EXTRACT_DIR}"

PACKAGE_ROOT=$(find "${EXTRACT_DIR}" -maxdepth 1 -type d -name "oidn-${VERSION}*" | head -n 1)
if [ -z "${PACKAGE_ROOT}" ]; then
  echo "Could not find extracted OIDN package root in ${ASSET_NAME}" >&2
  exit 1
fi

# Assert required files exist in SDK package
REQUIRED_FILES=(
  "bin/oidnDenoise"
  "lib/libOpenImageDenoise.so"
  "doc/LICENSE.txt"
  "include/OpenImageDenoise/oidn.h"
)
for rel in "${REQUIRED_FILES[@]}"; do
  # On Linux, libOpenImageDenoise.so is a symlink, so use -e to verify its existence
  if [ ! -e "${PACKAGE_ROOT}/${rel}" ]; then
    echo "OIDN package is missing required file: ${rel}" >&2
    exit 1
  fi
done

REQUIRED_GLOBS=(
  "lib/libOpenImageDenoise_core.so*"
  "lib/libOpenImageDenoise_device_cpu.so*"
)
for rel in "${REQUIRED_GLOBS[@]}"; do
  if ! has_file_match "${PACKAGE_ROOT}/${rel}"; then
    echo "OIDN package is missing required file matching: ${rel}" >&2
    exit 1
  fi
done

rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cp -a "${PACKAGE_ROOT}/." "${INSTALL_DIR}/"

# Write manifest.json
cat <<EOF > "${INSTALL_DIR}/manifest.json"
{
  "release_repository": "https://github.com/${REPOSITORY}",
  "release_tag": "${TAG}",
  "version": "${VERSION}",
  "platform": "${PLATFORM}",
  "asset": "${ASSET_NAME}",
  "executable": "bin/oidnDenoise",
  "license": "doc/LICENSE.txt",
  "note": "Official oidnDenoise is a sample app; production multipart EXR support uses the HDU OIDN Denoiser wrapper."
}
EOF

echo "Bundled OIDN runtime installed: ${INSTALL_DIR}/bin/oidnDenoise"
