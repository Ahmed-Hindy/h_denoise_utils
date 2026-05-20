#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="Ahmed-Hindy/NvidiaAIDenoiser"
TAG="optix-denoiser-v2026.05.18"
SOURCE_SHORT_SHA="fc927b7"
OPTIX_VERSIONS=("8.1" "9.0" "9.1")

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
    --source-short-sha)
      SOURCE_SHORT_SHA="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/h_denoise_utils/vendor/optix-denoiser/linux-x64"

EXPECTED_SOURCE_COMMIT="fc927b7eaa5f0c949226f3d23e302ebb0f4e33cf"
declare -A EXPECTED_OPTIX_COMMITS=(
  ["8.1"]="50021ea0af6d41609a97777ceebbdf1e1d34efe7"
  ["9.0"]="fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
  ["9.1"]="f1f6dd803f3159992d248178f6e09421c6eb8b6d"
)

get_optix_asset_name() {
  local version="$1"
  echo "optix-denoiser-linux-x64-optix-${version}-${SOURCE_SHORT_SHA}.zip"
}

get_optix_variant_dir() {
  local version="$1"
  echo "${VENDOR_DIR}/optix-${version}"
}

test_optix_variant_installed() {
  local version="$1"
  local variant_dir
  variant_dir=$(get_optix_variant_dir "${version}")
  [ -f "${variant_dir}/Denoiser" ] && [ -f "${variant_dir}/manifest.json" ]
}

validate_optix_manifest() {
  local manifest_path="$1"
  local version="$2"
  local expected_optix_commit="${EXPECTED_OPTIX_COMMITS[$version]}"
  
  python3 -c "
import json, sys
manifest_path = sys.argv[1]
version = sys.argv[2]
expected_source = sys.argv[3]
expected_optix = sys.argv[4]

with open(manifest_path, 'r') as f:
    manifest = json.load(f)

if manifest.get('source_commit') != expected_source:
    sys.exit(f'Bundled denoiser source commit mismatch for OptiX {version}. Expected {expected_source}, got {manifest.get(\"source_commit\")}')
if manifest.get('optix_version') != version:
    sys.exit(f'Bundled denoiser OptiX version mismatch. Expected {version}, got {manifest.get(\"optix_version\")}')
if manifest.get('optix_dev_commit') != expected_optix:
    sys.exit(f'Bundled denoiser OptiX SDK commit mismatch for OptiX {version}. Expected {expected_optix}, got {manifest.get(\"optix_dev_commit\")}')
" "${manifest_path}" "${version}" "${EXPECTED_SOURCE_COMMIT}" "${expected_optix_commit}"
}

# Verify and/or download variants
all_installed=true
for version in "${OPTIX_VERSIONS[@]}"; do
  if ! test_optix_variant_installed "${version}"; then
    all_installed=false
    break
  fi
done

if [ "${all_installed}" = true ]; then
  # Remove legacy un-nested files if present
  for legacyName in Denoiser manifest.json LICENSE; do
    rm -f "${VENDOR_DIR}/${legacyName}"
  done
  echo "Bundled OptiX denoiser variants already exist under: ${VENDOR_DIR}"
  exit 0
fi

mkdir -p "${VENDOR_DIR}"
DOWNLOAD_DIR=$(mktemp -d -t hdu-optix-denoiser-XXXXXX)
cleanup() {
  rm -rf "${DOWNLOAD_DIR}"
}
trap cleanup EXIT

LOCAL_ZIP_DIR="${HDU_OPTIX_DENOISER_ZIP_DIR:-}"

for version in "${OPTIX_VERSIONS[@]}"; do
  ASSET_NAME=$(get_optix_asset_name "${version}")
  ZIP_PATH="${DOWNLOAD_DIR}/${ASSET_NAME}"

  if [ -n "${LOCAL_ZIP_DIR}" ]; then
    LOCAL_ZIP="${LOCAL_ZIP_DIR}/${ASSET_NAME}"
    if [ ! -f "${LOCAL_ZIP}" ]; then
      echo "HDU_OPTIX_DENOISER_ZIP_DIR is missing ${ASSET_NAME}" >&2
      exit 1
    fi
    cp "${LOCAL_ZIP}" "${ZIP_PATH}"
  else
    gh release download "${TAG}" --repo "${REPOSITORY}" --pattern "${ASSET_NAME}" --dir "${DOWNLOAD_DIR}"
  fi

  if [ ! -f "${ZIP_PATH}" ]; then
    echo "Downloaded denoiser asset not found: ${ZIP_PATH}" >&2
    exit 1
  fi

  EXTRACT_DIR="${DOWNLOAD_DIR}/extract-${version}"
  mkdir -p "${EXTRACT_DIR}"
  unzip -q "${ZIP_PATH}" -d "${EXTRACT_DIR}"

  FOUND_EXE=$(find "${EXTRACT_DIR}" -type f -name "Denoiser" | head -n 1)
  if [ -z "${FOUND_EXE}" ]; then
    echo "Denoiser was not found in ${ZIP_PATH}" >&2
    exit 1
  fi

  FOUND_MANIFEST=$(find "${EXTRACT_DIR}" -type f -name "manifest.json" | head -n 1)
  if [ -z "${FOUND_MANIFEST}" ]; then
    echo "manifest.json was not found in ${ZIP_PATH}" >&2
    exit 1
  fi

  validate_optix_manifest "${FOUND_MANIFEST}" "${version}"

  VARIANT_DIR=$(get_optix_variant_dir "${version}")
  rm -rf "${VARIANT_DIR}"
  mkdir -p "${VARIANT_DIR}"

  cp "${FOUND_EXE}" "${VARIANT_DIR}/Denoiser"
  cp "${FOUND_MANIFEST}" "${VARIANT_DIR}/manifest.json"
  
  # Copy license if present
  FOUND_LICENSE=$(find "${EXTRACT_DIR}" -type f -name "LICENSE" | head -n 1)
  if [ -n "${FOUND_LICENSE}" ]; then
    cp "${FOUND_LICENSE}" "${VARIANT_DIR}/LICENSE"
  fi

  echo "Bundled OptiX ${version} denoiser installed: ${VARIANT_DIR}/Denoiser"
done

# Cleanup legacy files if present
for legacyName in Denoiser manifest.json LICENSE; do
  rm -f "${VENDOR_DIR}/${legacyName}"
done

# Build top-level manifest.json for optix-denoiser base directory
python3 -c "
import json, sys
vendor_dir = sys.argv[1]
repository = sys.argv[2]
tag = sys.argv[3]
source_commit = sys.argv[4]
versions = sys.argv[5].split(',')
commits = sys.argv[6].split(',')

variants = []
for v, c in zip(versions, commits):
    variants.append({
        'optix_version': v,
        'optix_dev_commit': c,
        'executable': f'optix-{v}/Denoiser',
        'manifest': f'optix-{v}/manifest.json'
    })

summary = {
    'release_repository': f'https://github.com/{repository}',
    'release_tag': tag,
    'source_commit': source_commit,
    'default_optix_version': '9.0',
    'variants': variants
}

with open(f'{vendor_dir}/manifest.json', 'w') as f:
    json.dump(summary, f, indent=2)
" "${VENDOR_DIR}" "${REPOSITORY}" "${TAG}" "${EXPECTED_SOURCE_COMMIT}" "$(IFS=,; echo "${OPTIX_VERSIONS[*]}")" "50021ea0af6d41609a97777ceebbdf1e1d34efe7,fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd,f1f6dd803f3159992d248178f6e09421c6eb8b6d"

echo "Bundled OptiX denoiser variants installed under: ${VENDOR_DIR}"
