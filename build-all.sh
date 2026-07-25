#!/usr/bin/env bash

set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly OUT_DIR="${ROOT_DIR}/out"
readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fil-c-utils.XXXXXXXX")"

cleanup() {
    rm -rf -- "${STAGING_DIR}"
}

trap cleanup EXIT

build_utility() {
    local name="$1"
    local context="$2"
    local destination="${STAGING_DIR}/${name}"

    mkdir -p -- "${destination}"

    printf 'Building %s for %s...\n' "${name}" "${PLATFORM}"
    docker build \
        --platform "${PLATFORM}" \
        --target artifact \
        --output "type=local,dest=${destination}" \
        "${ROOT_DIR}/${context}"
}

build_utility 7z 7z
build_utility unrar unrar

rm -rf -- "${OUT_DIR}"
mkdir -p -- "${OUT_DIR}"
cp -a -- "${STAGING_DIR}/7z/." "${OUT_DIR}/"
cp -a -- "${STAGING_DIR}/unrar/." "${OUT_DIR}/"

test -x "${OUT_DIR}/7z"
test -x "${OUT_DIR}/unrar"

printf 'Fil-C utilities are available in %s\n' "${OUT_DIR}"
