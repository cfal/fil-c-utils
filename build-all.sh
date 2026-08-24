#!/usr/bin/env bash

set -euo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly OUT_DIR="${ROOT_DIR}/out"
readonly PLATFORM="${PLATFORM:-linux/amd64}"
readonly UTILITIES=(7z unrar tar gzip bzip2 xz zstd curl wget nano tmux git openssh-server)
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
    ssh
    sshd
    scp
    sftp
    ssh-add
    ssh-agent
    ssh-keygen
    ssh-keyscan
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

# A full build stages multi-gigabyte tar archives and extracted trees. Keep
# them off /tmp, which is commonly RAM-backed on build hosts.
readonly STAGING_DIR="$(mktemp -d "${HOME:?HOME must be set}/fil-c-utils.XXXXXXXX")"

cleanup() {
    rm -rf -- "${STAGING_DIR}"
}

trap cleanup EXIT

build_utility() {
    local name="$1"
    local context="$2"
    local destination="${STAGING_DIR}/${name}"
    local archive="${STAGING_DIR}/${name}.tar"

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
        --output "type=tar,dest=${archive}" \
        "${ROOT_DIR}/${context}"
    # Ownership cannot be preserved by an unprivileged local build, but modes
    # must be: OpenSSH's ssh-keysign is setuid in the staged filesystem.
    tar --no-same-owner --same-permissions -xf "${archive}" -C "${destination}"
    rm -f -- "${archive}"
    if [[ "${name}" == "openssh-server" ]]; then
        test "$(stat -c '%a' "${destination}/libexec/ssh-keysign")" = 4711
        # Root ownership cannot survive unprivileged extraction. Do not leave
        # a setuid-to-builder executable in the local output tree.
        chmod 0711 "${destination}/libexec/ssh-keysign"
    fi
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
test "$(stat -c '%a' "${OUT_DIR}/libexec/ssh-keysign")" = 711

printf 'Fil-C utilities are available in %s\n' "${OUT_DIR}"
