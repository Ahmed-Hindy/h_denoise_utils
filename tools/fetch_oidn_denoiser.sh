#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="Ahmed-Hindy/h_denoise_utils"
TAG=""
VERSION="2.4.1"
PLATFORM="linux-x64"
SOURCE_SHORT_SHA=""
CONFIGURATION="Release"
ALLOW_SOURCE_KEY_MISMATCH=""
COPY_ASSET_TO_DIST=""

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --repo)
      REPOSITORY="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --source-short-sha)
      SOURCE_SHORT_SHA="$2"
      shift 2
      ;;
    --configuration)
      CONFIGURATION="$2"
      shift 2
      ;;
    --allow-source-key-mismatch)
      ALLOW_SOURCE_KEY_MISMATCH="1"
      shift
      ;;
    --copy-asset-to-dist)
      COPY_ASSET_TO_DIST="1"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [ "${PLATFORM}" != "linux-x64" ]; then
  echo "Unsupported OIDN platform '${PLATFORM}'. Expected linux-x64." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/h_denoise_utils/vendor/oidn-denoiser/${PLATFORM}/oidn-${VERSION}"
DIST_ROOT="${REPO_ROOT}/dist"

# Calculate the expected local source key to validate the downloaded binary
EXPECTED_SOURCE_KEY=$(python3 -c "
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

if [ -z "${SOURCE_SHORT_SHA}" ]; then
  SOURCE_SHORT_SHA="${EXPECTED_SOURCE_KEY:0:12}"
fi

validate_manifest() {
  local manifest_path="$1"
  local exe_path="$2"
  python3 -c "
import json, sys, os, hashlib
manifest_path = sys.argv[1]
exe_path = sys.argv[2]
expected_version = sys.argv[3]
expected_platform = sys.argv[4]
expected_source_key = sys.argv[5]
allow_mismatch = sys.argv[6] == '1'

with open(manifest_path, 'r') as f:
    manifest = json.load(f)

if manifest.get('name') != 'hdu-oidn-denoiser':
    sys.exit('OIDN denoiser manifest name mismatch')
if manifest.get('executable') != 'Denoiser':
    sys.exit('OIDN denoiser manifest executable mismatch')
if manifest.get('oidn_version') != expected_version:
    sys.exit('OIDN denoiser manifest version mismatch')
if manifest.get('platform') != expected_platform:
    sys.exit('OIDN denoiser manifest platform mismatch')
if manifest.get('contract') != 'optix-compatible-multipart-v1':
    sys.exit('OIDN denoiser manifest contract mismatch')

with open(exe_path, 'rb') as stream:
    actual_hash = hashlib.sha256(stream.read()).hexdigest().upper()
if actual_hash != manifest.get('sha256', '').upper():
    sys.exit('OIDN denoiser executable hash mismatch')

if not allow_mismatch:
    if manifest.get('source_key') != expected_source_key:
        sys.exit(f'OIDN denoiser source_key mismatch. Expected {expected_source_key}, got {manifest.get(\"source_key\")}')
" "${manifest_path}" "${exe_path}" "${VERSION}" "${PLATFORM}" "${EXPECTED_SOURCE_KEY}" "${ALLOW_SOURCE_KEY_MISMATCH}"
}

# If already installed and correct, skip downloading
if [ -f "${VENDOR_DIR}/Denoiser" ] && [ -f "${VENDOR_DIR}/manifest.json" ]; then
  if validate_manifest "${VENDOR_DIR}/manifest.json" "${VENDOR_DIR}/Denoiser"; then
    echo "Bundled OIDN denoiser already exists and is valid: ${VENDOR_DIR}/Denoiser"
    exit 0
  else
    echo "Existing OIDN denoiser manifest check failed. Will re-fetch."
  fi
fi

# Determine zip file matching patterns
PATTERN="oidn-denoiser-${PLATFORM}-oidn-${VERSION}-${SOURCE_SHORT_SHA}.zip"
FALLBACK_PATTERN="oidn-denoiser-${PLATFORM}-oidn-${VERSION}-*.zip"

DOWNLOAD_DIR=$(mktemp -d -t hdu-oidn-denoiser-XXXXXX)
cleanup() {
  rm -rf "${DOWNLOAD_DIR}"
}
trap cleanup EXIT

ZIP_PATH=""

if [ -n "${HDU_OIDN_DENOISER_ZIP_DIR:-}" ]; then
  # Find matching zip in local folder
  ZIP_FILE=$(find "${HDU_OIDN_DENOISER_ZIP_DIR}" -maxdepth 1 -name "${PATTERN}" -o -name "${FALLBACK_PATTERN}" | head -n 1)
  if [ -z "${ZIP_FILE}" ]; then
    echo "HDU_OIDN_DENOISER_ZIP_DIR is missing asset matching ${PATTERN} or fallback" >&2
    exit 1
  fi
  ZIP_PATH="${DOWNLOAD_DIR}/$(basename "${ZIP_FILE}")"
  cp "${ZIP_FILE}" "${ZIP_PATH}"
else
  # Use gh cli to find release tag
  if [ -z "${TAG}" ]; then
    echo "Resolving OIDN denoiser release tag..."
    # Query recent releases, search for matching asset in their lists
    RELEASES=$(gh release list --repo "${REPOSITORY}" --exclude-drafts --exclude-pre-releases --limit 50 --json tagName -q '.[].tagName')
    for r in ${RELEASES}; do
      if [[ ! "$r" =~ ^v ]]; then
        continue
      fi
      ASSETS=$(gh release view "$r" --repo "${REPOSITORY}" --json assets -q '.assets[].name')
      for a in ${ASSETS}; do
        if [[ "$a" == "$PATTERN" ]] || [[ "$a" =~ ^oidn-denoiser-${PLATFORM}-oidn-${VERSION}-.*\.zip$ ]]; then
          TAG="$r"
          PATTERN="$a"
          break 2
        fi
      done
    done
    if [ -z "${TAG}" ]; then
      echo "No non-draft release contains an OIDN denoiser asset matching ${PATTERN}." >&2
      exit 1
    fi
    echo "Resolved OIDN denoiser release tag: ${TAG}"
  fi

  gh release download "${TAG}" --repo "${REPOSITORY}" --pattern "${PATTERN}" --dir "${DOWNLOAD_DIR}"
  ZIP_PATH="${DOWNLOAD_DIR}/${PATTERN}"
fi

if [ ! -f "${ZIP_PATH}" ]; then
  echo "Downloaded OIDN denoiser asset not found: ${ZIP_PATH}" >&2
  exit 1
fi

EXTRACT_DIR="${DOWNLOAD_DIR}/extract"
mkdir -p "${EXTRACT_DIR}"
unzip -q "${ZIP_PATH}" -d "${EXTRACT_DIR}"

FOUND_EXE=$(find "${EXTRACT_DIR}" -type f -name "Denoiser" | head -n 1)
if [ -z "${FOUND_EXE}" ]; then
  echo "Denoiser binary was not found in ${ZIP_PATH}" >&2
  exit 1
fi

FOUND_MANIFEST=$(find "${EXTRACT_DIR}" -type f -name "manifest.json" | head -n 1)
if [ -z "${FOUND_MANIFEST}" ]; then
  echo "manifest.json was not found in ${ZIP_PATH}" >&2
  exit 1
fi

validate_manifest "${FOUND_MANIFEST}" "${FOUND_EXE}"

rm -rf "${VENDOR_DIR}"
mkdir -p "${VENDOR_DIR}"
cp -a "$(dirname "${FOUND_EXE}")/." "${VENDOR_DIR}/"

if [ -n "${COPY_ASSET_TO_DIST}" ]; then
  mkdir -p "${DIST_ROOT}"
  cp "${ZIP_PATH}" "${DIST_ROOT}/"
fi

echo "Bundled OIDN denoiser installed: ${VENDOR_DIR}/Denoiser"
