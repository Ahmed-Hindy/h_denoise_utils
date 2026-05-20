#!/usr/bin/env bash
set -euo pipefail

VERSION="2.4.1"
CONFIGURATION="Release"
PLATFORM="linux-x64"
SOURCE_COMMIT=""
SKIP_OIDN_FETCH=""

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --version)
      VERSION="$2"
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
    --source-commit)
      SOURCE_COMMIT="$2"
      shift 2
      ;;
    --skip-oidn-fetch)
      SKIP_OIDN_FETCH="1"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ "${PLATFORM}" != "linux-x64" ]; then
  echo "Unsupported OIDN denoiser platform '${PLATFORM}'. Expected linux-x64." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
NATIVE_DIR="${REPO_ROOT}/native/oidn-denoiser"
OIDN_ROOT="${REPO_ROOT}/h_denoise_utils/vendor/oidn/${PLATFORM}/oidn-${VERSION}"
BUNDLE_ROOT="${REPO_ROOT}/h_denoise_utils/vendor/oidn-denoiser/${PLATFORM}/oidn-${VERSION}"
BUILD_ROOT="${REPO_ROOT}/build/oidn-denoiser/${PLATFORM}/oidn-${VERSION}"
DIST_ROOT="${REPO_ROOT}/dist"

if [ -z "${SKIP_OIDN_FETCH}" ]; then
  "${SCRIPT_DIR}/fetch_oidn.sh" --version "${VERSION}" --platform "${PLATFORM}"
fi

if [ ! -f "${OIDN_ROOT}/include/OpenImageDenoise/oidn.hpp" ]; then
  echo "OIDN headers were not found under ${OIDN_ROOT}. Run tools/fetch_oidn.sh first." >&2
  exit 1
fi
if [ ! -f "${OIDN_ROOT}/lib/libOpenImageDenoise.so" ]; then
  echo "OIDN shared library was not found under ${OIDN_ROOT}. Run tools/fetch_oidn.sh first." >&2
  exit 1
fi

if [ -z "${SOURCE_COMMIT}" ]; then
  SOURCE_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD | tr -d '\n')
fi

# Calculate Source Key via Python to match the exact Windows hashing strategy
echo "Calculating OIDN denoiser source key..."
SOURCE_KEY=$(python3 -c "
import sys, os, hashlib
repo_root = sys.argv[1]
version = sys.argv[2]
platform = sys.argv[3]
configuration = sys.argv[4]

payload = [f'version={version}', f'platform={platform}', f'configuration={configuration}']
inputs = ['native/oidn-denoiser', 'tools/build_oidn_denoiser.sh', 'tools/fetch_oidn.sh']

for inp in inputs:
    path = os.path.join(repo_root, inp)
    if not os.path.exists(path):
        print(f'Input missing: {path}', file=sys.stderr)
        sys.exit(1)
    if os.path.isdir(path):
        files = []
        for r, _, fs in os.walk(path):
            for f in fs:
                files.append(os.path.join(r, f))
        for f in sorted(files):
            rel = os.path.relpath(f, repo_root).replace('\\\\', '/')
            with open(f, 'rb') as stream:
                h = hashlib.sha256(stream.read()).hexdigest().lower()
            payload.append(f'{rel}={h}')
    else:
        rel = os.path.relpath(path, repo_root).replace('\\\\', '/')
        with open(path, 'rb') as stream:
            h = hashlib.sha256(stream.read()).hexdigest().lower()
        payload.append(f'{rel}={h}')

joined = '\n'.join(payload)
print(hashlib.sha256(joined.encode('utf-8')).hexdigest().lower())
" "${REPO_ROOT}" "${VERSION}" "${PLATFORM}" "${CONFIGURATION}")

SOURCE_KEY_SHORT="${SOURCE_KEY:0:12}"
echo "Source Key: ${SOURCE_KEY}"
echo "Source Key (Short): ${SOURCE_KEY_SHORT}"

# Prepare directories
rm -rf "${BUILD_ROOT}" "${BUNDLE_ROOT}"
mkdir -p "${BUILD_ROOT}" "${BUNDLE_ROOT}" "${DIST_ROOT}"

# Run Conan and CMake Build
cd "${NATIVE_DIR}"
uv run --native-tls --with conan conan profile detect --force
uv run --native-tls --with conan conan install . --output-folder "${BUILD_ROOT}" --build=missing -s build_type="${CONFIGURATION}" -s compiler.cppstd=20 -c tools.system.package_manager:mode=install -c tools.system.package_manager:sudo=True

TOOLCHAIN=$(find "${BUILD_ROOT}" -name conan_toolchain.cmake | head -n 1)
if [ -z "${TOOLCHAIN}" ] || [ ! -f "${TOOLCHAIN}" ]; then
  echo "Conan toolchain file was not created under ${BUILD_ROOT}" >&2
  exit 1
fi

cmake -S "${NATIVE_DIR}" -B "${BUILD_ROOT}" \
    -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
    -DOIDN_ROOT="${OIDN_ROOT}" \
    -DCMAKE_INSTALL_PREFIX="${BUNDLE_ROOT}" \
    -DCMAKE_BUILD_TYPE="${CONFIGURATION}"
cmake --build "${BUILD_ROOT}" --config "${CONFIGURATION}"
cmake --install "${BUILD_ROOT}" --config "${CONFIGURATION}"

EXE_PATH="${BUNDLE_ROOT}/Denoiser"
if [ ! -f "${EXE_PATH}" ]; then
  echo "OIDN Denoiser binary was not created: ${EXE_PATH}" >&2
  exit 1
fi

# Bundle official OIDN shared libraries (preserve symlinks with cp -P)
echo "Bundling OIDN shared libraries..."
cp -P "${OIDN_ROOT}"/lib/libOpenImageDenoise.so* "${BUNDLE_ROOT}/"
cp -P "${OIDN_ROOT}"/lib/libtbb.so* "${BUNDLE_ROOT}/"

# Copy Licenses
for licenseName in LICENSE.txt third-party-programs.txt third-party-programs-DPCPP.txt third-party-programs-oneTBB.txt; do
  licensePath="${OIDN_ROOT}/doc/${licenseName}"
  if [ -f "${licensePath}" ]; then
    cp "${licensePath}" "${BUNDLE_ROOT}/${licenseName}"
  fi
done

# Write manifest.json
python3 -c "
import json, sys, os, hashlib
from datetime import datetime

exe_path = sys.argv[1]
bundle_root = sys.argv[2]
version = sys.argv[3]
platform = sys.argv[4]
source_commit = sys.argv[5]
source_key = sys.argv[6]

with open(exe_path, 'rb') as stream:
    sha256 = hashlib.sha256(stream.read()).hexdigest().upper()

size = os.path.getsize(exe_path)

manifest = {
    'name': 'hdu-oidn-denoiser',
    'executable': 'Denoiser',
    'source_commit': source_commit,
    'source_key': source_key,
    'oidn_version': version,
    'oidn_release': f'v{version}',
    'platform': platform,
    'build_time_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'sha256': sha256,
    'size': size,
    'contract': 'optix-compatible-multipart-v1'
}

with open(os.path.join(bundle_root, 'manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=2)
" "${EXE_PATH}" "${BUNDLE_ROOT}" "${VERSION}" "${PLATFORM}" "${SOURCE_COMMIT}" "${SOURCE_KEY}"

# Run preservation validation
echo "Validating OIDN wrapper preservation rules..."
# Explicitly add bundle root to LD_LIBRARY_PATH so dynamic linker can find OpenImageDenoise shared libraries
export LD_LIBRARY_PATH="${BUNDLE_ROOT}:${LD_LIBRARY_PATH:-}"
uv run --native-tls --with OpenEXR --with numpy python "${SCRIPT_DIR}/validate_oidn_uint_preservation.py" --denoiser "${EXE_PATH}"

# Archive package
ASSET_NAME="oidn-denoiser-${PLATFORM}-oidn-${VERSION}-${SOURCE_KEY_SHORT}.zip"
ASSET_PATH="${DIST_ROOT}/${ASSET_NAME}"
rm -f "${ASSET_PATH}"

cd "${BUNDLE_ROOT}"
zip -r "${ASSET_PATH}" .

echo "OIDN denoiser bundle created: ${BUNDLE_ROOT}"
echo "OIDN denoiser asset created: ${ASSET_PATH}"
