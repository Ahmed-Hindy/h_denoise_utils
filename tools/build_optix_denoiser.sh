#!/usr/bin/env bash
set -euo pipefail

OPTIX_VERSION="9.0"
CONFIGURATION="Release"
PLATFORM="linux-x64"
OPTIX_DEV_COMMIT=""
SKIP_OPTIX_FETCH=""

declare -A OPTIX_SDK_COMMITS=(
  ["8.1"]="50021ea0af6d41609a97777ceebbdf1e1d34efe7"
  ["9.0"]="fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
  ["9.1"]="f1f6dd803f3159992d248178f6e09421c6eb8b6d"
)

while [[ $# -gt 0 ]]; do
  case $1 in
    --optix-version)
      OPTIX_VERSION="$2"
      shift 2
      ;;
    --configuration)
      CONFIGURATION="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --optix-dev-commit)
      OPTIX_DEV_COMMIT="$2"
      shift 2
      ;;
    --skip-optix-fetch)
      SKIP_OPTIX_FETCH="1"
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${PLATFORM}" != "linux-x64" ]]; then
  echo "Unsupported OptiX denoiser platform '${PLATFORM}'. Expected linux-x64." >&2
  exit 1
fi
if [[ -z "${OPTIX_SDK_COMMITS[${OPTIX_VERSION}]+x}" ]]; then
  echo "Unsupported OptiX version '${OPTIX_VERSION}'. Expected 8.1, 9.0, or 9.1." >&2
  exit 1
fi
if [[ -z "${OPTIX_DEV_COMMIT}" ]]; then
  OPTIX_DEV_COMMIT="${OPTIX_SDK_COMMITS[${OPTIX_VERSION}]}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NATIVE_DIR="${REPO_ROOT}/native/optix-denoiser"
OPTIX_DIR="${NATIVE_DIR}/contrib/optix"
BUILD_ROOT="${REPO_ROOT}/build/optix-denoiser/${PLATFORM}/optix-${OPTIX_VERSION}"
BUNDLE_ROOT="${REPO_ROOT}/h_denoise_utils/vendor/optix-denoiser/${PLATFORM}/optix-${OPTIX_VERSION}"
DIST_ROOT="${REPO_ROOT}/dist"

sync_optix_dev() {
  local destination="$1"
  local commit="$2"

  if [[ -d "${destination}/.git" ]]; then
    git -C "${destination}" fetch origin "${commit}"
    git -C "${destination}" checkout --force "${commit}"
    git -C "${destination}" clean -fdx
  else
    rm -rf "${destination}"
    mkdir -p "$(dirname "${destination}")"
    git clone --no-checkout https://github.com/NVIDIA/optix-dev.git "${destination}"
    git -C "${destination}" fetch origin "${commit}"
    git -C "${destination}" checkout --force "${commit}"
  fi

  if [[ ! -f "${destination}/include/optix.h" ]]; then
    echo "OptiX SDK checkout is missing include/optix.h: ${destination}" >&2
    exit 1
  fi
}

calculate_source_key() {
  python3 -c "
import hashlib
import os
import sys

repo_root = sys.argv[1]
optix_version = sys.argv[2]
optix_dev_commit = sys.argv[3]
platform = sys.argv[4]
configuration = sys.argv[5]

payload = [
    f'optix_version={optix_version}',
    f'optix_dev_commit={optix_dev_commit}',
    f'platform={platform}',
    f'configuration={configuration}',
]
inputs = [
    'native/optix-denoiser/CMakeLists.txt',
    'native/optix-denoiser/conanfile.txt',
    'native/optix-denoiser/cmake',
    'native/optix-denoiser/src',
    'tools/build_optix_denoiser.ps1',
    'tools/build_optix_denoiser.sh',
]

for inp in inputs:
    path = os.path.join(repo_root, inp)
    if not os.path.exists(path):
        print(f'Input missing: {path}', file=sys.stderr)
        sys.exit(1)
    if os.path.isdir(path):
        files = []
        for root, _dirs, names in os.walk(path):
            for name in names:
                files.append(os.path.join(root, name))
    else:
        files = [path]
    for file_path in sorted(files):
        rel = os.path.relpath(file_path, repo_root).replace(os.sep, '/')
        with open(file_path, 'rb') as stream:
            digest = hashlib.sha256(stream.read()).hexdigest().lower()
        payload.append(f'{rel}={digest}')

joined = '\n'.join(payload)
print(hashlib.sha256(joined.encode('utf-8')).hexdigest().lower())
" "${REPO_ROOT}" "${OPTIX_VERSION}" "${OPTIX_DEV_COMMIT}" "${PLATFORM}" "${CONFIGURATION}"
}

if [[ -z "${SKIP_OPTIX_FETCH}" ]]; then
  sync_optix_dev "${OPTIX_DIR}" "${OPTIX_DEV_COMMIT}"
fi
if [[ ! -f "${OPTIX_DIR}/include/optix.h" ]]; then
  echo "OptiX SDK headers were not found under ${OPTIX_DIR}. Run without --skip-optix-fetch first." >&2
  exit 1
fi

SOURCE_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD | tr -d '\n')
SOURCE_KEY=$(calculate_source_key)
SOURCE_KEY_SHORT="${SOURCE_KEY:0:12}"

rm -rf "${BUILD_ROOT}" "${BUNDLE_ROOT}"
mkdir -p "${BUILD_ROOT}" "${BUNDLE_ROOT}" "${DIST_ROOT}"

cd "${NATIVE_DIR}"
uv run --native-tls --with conan conan profile detect --force
uv run --native-tls --with conan conan install . --output-folder "${BUILD_ROOT}" --build=missing -s build_type="${CONFIGURATION}" -s compiler.cppstd=20 -o openimageio/*:with_ffmpeg=False -c tools.system.package_manager:mode=install -c tools.system.package_manager:sudo=True

TOOLCHAIN=$(find "${BUILD_ROOT}" -name conan_toolchain.cmake | head -n 1)
if [[ -z "${TOOLCHAIN}" ]] || [[ ! -f "${TOOLCHAIN}" ]]; then
  echo "Conan toolchain file was not created under ${BUILD_ROOT}" >&2
  exit 1
fi

cmake -S "${NATIVE_DIR}" -B "${BUILD_ROOT}" \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_INSTALL_PREFIX="${BUNDLE_ROOT}" \
  -DCMAKE_BUILD_TYPE="${CONFIGURATION}"
cmake --build "${BUILD_ROOT}" --config "${CONFIGURATION}" --target install

EXE_PATH="${BUNDLE_ROOT}/Denoiser"
if [[ -f "${BUNDLE_ROOT}/bin/Denoiser" ]] && [[ ! -f "${EXE_PATH}" ]]; then
  mv "${BUNDLE_ROOT}/bin/Denoiser" "${EXE_PATH}"
fi
if [[ ! -f "${EXE_PATH}" ]]; then
  echo "OptiX Denoiser binary was not created: ${EXE_PATH}" >&2
  exit 1
fi

if [[ -f "${NATIVE_DIR}/LICENSE" ]]; then
  cp "${NATIVE_DIR}/LICENSE" "${BUNDLE_ROOT}/LICENSE"
fi

python3 -c "
import hashlib
import json
import os
import sys
from datetime import datetime

exe_path = sys.argv[1]
bundle_root = sys.argv[2]
source_commit = sys.argv[3]
source_key = sys.argv[4]
optix_version = sys.argv[5]
optix_dev_commit = sys.argv[6]
platform = sys.argv[7]

with open(exe_path, 'rb') as stream:
    sha256 = hashlib.sha256(stream.read()).hexdigest().upper()

manifest = {
    'name': 'hdu-optix-denoiser',
    'executable': 'Denoiser',
    'source_commit': source_commit,
    'source_key': source_key,
    'optix_version': optix_version,
    'optix_dev_commit': optix_dev_commit,
    'platform': platform,
    'build_time_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'sha256': sha256,
    'size': os.path.getsize(exe_path),
    'contract': 'optix-compatible-multipart-v1',
}

with open(os.path.join(bundle_root, 'manifest.json'), 'w') as stream:
    json.dump(manifest, stream, indent=2)
" "${EXE_PATH}" "${BUNDLE_ROOT}" "${SOURCE_COMMIT}" "${SOURCE_KEY}" "${OPTIX_VERSION}" "${OPTIX_DEV_COMMIT}" "${PLATFORM}"

ASSET_NAME="optix-denoiser-${PLATFORM}-optix-${OPTIX_VERSION}-${SOURCE_KEY_SHORT}.zip"
ASSET_PATH="${DIST_ROOT}/${ASSET_NAME}"
rm -f "${ASSET_PATH}"

cd "${BUNDLE_ROOT}"
zip -r "${ASSET_PATH}" .

echo "OptiX denoiser bundle created: ${BUNDLE_ROOT}"
echo "OptiX denoiser asset created: ${ASSET_PATH}"
