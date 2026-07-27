#!/usr/bin/env bash

set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly OUT_DIR="${ROOT_DIR}/out"
readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly UTILITIES=(7z unrar tar gzip bzip2 xz zstd curl wget nano tmux git)
readonly EXECUTABLES=(
    7z
    7zz
    unrar
    tar
    gzip
    gunzip
    zcat
    bzip2
    bzip2recover
    bunzip2
    bzcat
    xz
    unxz
    xzcat
    lzma
    unlzma
    lzcat
    zstd
    unzstd
    zstdcat
    curl
    wget
    nano
    tmux
    git
)

# Anything that needs these lists should ask for them rather than keeping its
# own copy. CI builds the utilities in parallel instead of calling this script,
# so without this it would carry a second list that could drift.
if [[ "${1:-}" == "--list" ]]; then
    case "${2:-}" in
        utilities)   printf '%s\n' "${UTILITIES[@]}" ;;
        executables) printf '%s\n' "${EXECUTABLES[@]}" ;;
        *)
            printf 'usage: %s --list utilities|executables\n' "${0}" >&2
            exit 2
            ;;
    esac
    exit 0
fi

readonly STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fil-c-utils.XXXXXXXX")"

cleanup() {
    rm -rf -- "${STAGING_DIR}"
}

trap cleanup EXIT

build_utility() {
    local name="$1"
    local context="$2"
    local destination="${STAGING_DIR}/${name}"

    # wget's HTTPS test suite resolves a fixed hostname through glibc's
    # HOSTALIASES, which the musl-built client ignores. Supplying the mapping
    # through /etc/hosts, which musl reads, lets those tests run; the Dockerfile
    # cannot do it itself because /etc/hosts is read-only during a build. The
    # flag is harmless to every other utility, none of which resolve that name.
    local add_host=""
    [[ "${name}" == "wget" ]] && add_host="--add-host=WgetTestingServer:127.0.0.1"

    mkdir -p -- "${destination}"

    printf 'Building %s for %s...\n' "${name}" "${PLATFORM}"
    docker build \
        ${add_host} \
        --platform "${PLATFORM}" \
        --target artifact \
        --output "type=local,dest=${destination}" \
        "${ROOT_DIR}/${context}"
}

for utility in "${UTILITIES[@]}"; do
    build_utility "${utility}" "${utility}"
done

rm -rf -- "${OUT_DIR}"
mkdir -p -- "${OUT_DIR}"

for utility in "${UTILITIES[@]}"; do
    cp -a -- "${STAGING_DIR}/${utility}/." "${OUT_DIR}/"
done

for executable in "${EXECUTABLES[@]}"; do
    test -x "${OUT_DIR}/bin/${executable}"
done

printf 'Fil-C utilities are available in %s\n' "${OUT_DIR}"
