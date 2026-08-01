#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="Ahmed-Hindy/h_denoise_utils"
TAG="optix-denoiser-v2026.05.21"
CONFIGURATION="Release"
OPTIX_VERSIONS=("8.1" "9.0" "9.1")
ALLOW_SOURCE_KEY_MISMATCH=""

declare -A EXPECTED_OPTIX_COMMITS=(
  ["8.1"]="50021ea0af6d41609a97777ceebbdf1e1d34efe7"
  ["9.0"]="fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd"
  ["9.1"]="f1f6dd803f3159992d248178f6e09421c6eb8b6d"
)

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
    --configuration)
      CONFIGURATION="$2"
      shift 2
      ;;
    --allow-source-key-mismatch)
      ALLOW_SOURCE_KEY_MISMATCH="1"
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLATFORM="linux-x64"
VENDOR_DIR="${REPO_ROOT}/h_denoise_utils/vendor/optix-denoiser/${PLATFORM}"

calculate_source_key() {
  local version="$1"
  local optix_commit="$2"
  python3 "${SCRIPT_DIR}/optix_source_key.py" \
    --repo-root "${REPO_ROOT}" \
    --optix-version "${version}" \
    --optix-commit "${optix_commit}" \
    --platform "${PLATFORM}" \
    --configuration "${CONFIGURATION}"
}

get_optix_asset_name() {
  local version="$1"
  local source_key="$2"
  echo "optix-denoiser-${PLATFORM}-optix-${version}-${source_key:0:12}.zip"
}

get_optix_variant_dir() {
  local version="$1"
  echo "${VENDOR_DIR}/optix-${version}"
}

validate_optix_manifest() {
  local manifest_path="$1"
  local exe_path="$2"
  local version="$3"
  local expected_source_key="$4"
  local expected_optix_commit="${EXPECTED_OPTIX_COMMITS[$version]}"

  python3 -c "
import hashlib
import json
import sys

manifest_path = sys.argv[1]
exe_path = sys.argv[2]
version = sys.argv[3]
expected_optix = sys.argv[4]
expected_platform = sys.argv[5]
expected_source_key = sys.argv[6]
allow_mismatch = sys.argv[7] == '1'

with open(manifest_path, 'r') as stream:
    manifest = json.load(stream)

if manifest.get('name') != 'hdu-optix-denoiser':
    sys.exit('Bundled OptiX manifest name mismatch')
if manifest.get('executable') != 'Denoiser':
    sys.exit('Bundled OptiX manifest executable mismatch')
if manifest.get('optix_version') != version:
    sys.exit(f'Bundled OptiX version mismatch. Expected {version}, got {manifest.get(\"optix_version\")}')
if manifest.get('optix_dev_commit') != expected_optix:
    sys.exit(f'Bundled OptiX SDK commit mismatch for {version}. Expected {expected_optix}, got {manifest.get(\"optix_dev_commit\")}')
if manifest.get('platform') != expected_platform:
    sys.exit(f'Bundled OptiX platform mismatch. Expected {expected_platform}, got {manifest.get(\"platform\")}')
if manifest.get('contract') != 'optix-compatible-multipart-v1':
    sys.exit('Bundled OptiX manifest contract mismatch')

with open(exe_path, 'rb') as stream:
    actual_hash = hashlib.sha256(stream.read()).hexdigest().upper()
if actual_hash != manifest.get('sha256', '').upper():
    sys.exit('Bundled OptiX executable hash mismatch')

actual_source_key = manifest.get('source_key')
if not isinstance(actual_source_key, str) or not actual_source_key:
    sys.exit('Bundled OptiX manifest is missing source_key; rebuild it with the current build script')
if not allow_mismatch and actual_source_key != expected_source_key:
    sys.exit(f'Bundled OptiX source_key mismatch. Expected {expected_source_key}, got {actual_source_key}')
print(actual_source_key)
" "${manifest_path}" "${exe_path}" "${version}" "${expected_optix_commit}" "${PLATFORM}" "${expected_source_key}" "${ALLOW_SOURCE_KEY_MISMATCH}"
}

write_vendor_summary() {
  python3 -c "
import json
import sys

vendor_dir = sys.argv[1]
repository = sys.argv[2]
tag = sys.argv[3]
versions = sys.argv[4].split(',')
commits = sys.argv[5].split(',')
source_keys = sys.argv[6].split(',')

variants = []
for version, commit, source_key in zip(versions, commits, source_keys):
    variants.append({
        'optix_version': version,
        'optix_dev_commit': commit,
        'source_key': source_key,
        'executable': f'optix-{version}/Denoiser',
        'manifest': f'optix-{version}/manifest.json',
    })

summary = {
    'release_repository': f'https://github.com/{repository}',
    'release_tag': tag,
    'default_optix_version': '9.0',
    'variants': variants,
}

with open(f'{vendor_dir}/manifest.json', 'w') as stream:
    json.dump(summary, stream, indent=2)
" \
    "${VENDOR_DIR}" \
    "${REPOSITORY}" \
    "${TAG}" \
    "$(IFS=,; echo "${OPTIX_VERSIONS[*]}")" \
    "50021ea0af6d41609a97777ceebbdf1e1d34efe7,fff65c2a7c592f1ea5f1661ad7d2381cf965f9bd,f1f6dd803f3159992d248178f6e09421c6eb8b6d" \
    "${ACTUAL_SOURCE_KEYS["8.1"]},${ACTUAL_SOURCE_KEYS["9.0"]},${ACTUAL_SOURCE_KEYS["9.1"]}"
}

declare -A EXPECTED_SOURCE_KEYS=()
declare -A ACTUAL_SOURCE_KEYS=()
for version in "${OPTIX_VERSIONS[@]}"; do
  EXPECTED_SOURCE_KEYS["${version}"]="$(calculate_source_key "${version}" "${EXPECTED_OPTIX_COMMITS[$version]}")"
done

all_installed=true
for version in "${OPTIX_VERSIONS[@]}"; do
  variant_dir=$(get_optix_variant_dir "${version}")
  exe_path="${variant_dir}/Denoiser"
  manifest_path="${variant_dir}/manifest.json"
  if [[ ! -f "${exe_path}" ]] || [[ ! -f "${manifest_path}" ]]; then
    all_installed=false
    break
  fi
  if actual_source_key=$(validate_optix_manifest "${manifest_path}" "${exe_path}" "${version}" "${EXPECTED_SOURCE_KEYS[$version]}"); then
    ACTUAL_SOURCE_KEYS["${version}"]="${actual_source_key}"
  else
    echo "Existing OptiX ${version} bundle failed validation. Will re-fetch." >&2
    all_installed=false
    break
  fi
done

if [[ "${all_installed}" == true ]]; then
  for legacyName in Denoiser LICENSE; do
    rm -f "${VENDOR_DIR}/${legacyName}"
  done
  write_vendor_summary
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
  ASSET_NAME=$(get_optix_asset_name "${version}" "${EXPECTED_SOURCE_KEYS[$version]}")
  ASSET_PATTERN="${ASSET_NAME}"
  if [[ -n "${ALLOW_SOURCE_KEY_MISMATCH}" ]]; then
    ASSET_PATTERN="optix-denoiser-${PLATFORM}-optix-${version}-*.zip"
  fi

  if [[ -n "${LOCAL_ZIP_DIR}" ]]; then
    LOCAL_ZIP=$(python3 -c "
import glob
import os
import sys

matches = [path for path in glob.glob(os.path.join(sys.argv[1], sys.argv[2])) if os.path.isfile(path)]
if not matches:
    sys.exit(f'HDU_OPTIX_DENOISER_ZIP_DIR has no asset matching {sys.argv[2]}')
print(max(matches, key=lambda path: (os.stat(path).st_mtime_ns, os.path.basename(path))))
" "${LOCAL_ZIP_DIR}" "${ASSET_PATTERN}")
    ASSET_NAME=$(basename "${LOCAL_ZIP}")
    ZIP_PATH="${DOWNLOAD_DIR}/${ASSET_NAME}"
    cp "${LOCAL_ZIP}" "${ZIP_PATH}"
  else
    if [[ -n "${ALLOW_SOURCE_KEY_MISMATCH}" ]]; then
      ASSET_NAME=$(gh release view "${TAG}" --repo "${REPOSITORY}" --json assets | python3 -c "
import fnmatch
import json
import sys

assets = json.load(sys.stdin).get('assets', [])
matches = [asset for asset in assets if fnmatch.fnmatchcase(str(asset.get('name', '')), sys.argv[1])]
if not matches:
    sys.exit(f'Release has no denoiser asset matching {sys.argv[1]}')
selected = max(matches, key=lambda asset: (str(asset.get('updatedAt') or asset.get('createdAt') or ''), str(asset.get('name', ''))))
print(selected['name'])
" "${ASSET_PATTERN}")
    fi
    ZIP_PATH="${DOWNLOAD_DIR}/${ASSET_NAME}"
    gh release download "${TAG}" --repo "${REPOSITORY}" --pattern "${ASSET_NAME}" --dir "${DOWNLOAD_DIR}"
  fi

  if [[ ! -f "${ZIP_PATH}" ]]; then
    echo "Downloaded denoiser asset not found: ${ZIP_PATH}" >&2
    exit 1
  fi

  EXTRACT_DIR="${DOWNLOAD_DIR}/extract-${version}"
  python3 -c "
import pathlib
import sys
import zipfile

archive_path = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2]).resolve()
with zipfile.ZipFile(archive_path) as archive:
    for member in archive.infolist():
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root):
            sys.exit(f'Archive member escapes destination: {member.filename}')
    archive.extractall(root)
" "${ZIP_PATH}" "${EXTRACT_DIR}"

  FOUND_EXE=$(find "${EXTRACT_DIR}" -type f -name "Denoiser" | head -n 1)
  if [[ -z "${FOUND_EXE}" ]]; then
    echo "Denoiser was not found in ${ZIP_PATH}" >&2
    exit 1
  fi

  FOUND_MANIFEST=$(find "${EXTRACT_DIR}" -type f -name "manifest.json" | head -n 1)
  if [[ -z "${FOUND_MANIFEST}" ]]; then
    echo "manifest.json was not found in ${ZIP_PATH}" >&2
    exit 1
  fi
  FOUND_EXE_DIR="$(cd "$(dirname "${FOUND_EXE}")" && pwd)"
  FOUND_MANIFEST_DIR="$(cd "$(dirname "${FOUND_MANIFEST}")" && pwd)"
  if [[ "${FOUND_EXE_DIR}" != "${FOUND_MANIFEST_DIR}" ]]; then
    echo "Denoiser and manifest.json must be in the same bundle directory." >&2
    exit 1
  fi

  ACTUAL_SOURCE_KEYS["${version}"]="$(validate_optix_manifest "${FOUND_MANIFEST}" "${FOUND_EXE}" "${version}" "${EXPECTED_SOURCE_KEYS[$version]}")"

  VARIANT_DIR=$(get_optix_variant_dir "${version}")
  rm -rf "${VARIANT_DIR}"
  mkdir -p "${VARIANT_DIR}"
  cp -a "${FOUND_EXE_DIR}/." "${VARIANT_DIR}/"

  echo "Bundled OptiX ${version} denoiser installed: ${VARIANT_DIR}/Denoiser"
done

for legacyName in Denoiser LICENSE; do
  rm -f "${VENDOR_DIR}/${legacyName}"
done

write_vendor_summary

echo "Bundled OptiX denoiser variants installed under: ${VENDOR_DIR}"
