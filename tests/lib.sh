#!/usr/bin/env bash
# Shared locations for the robustness tests.  Source this, do not run it.

TESTS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname -- "${TESTS_DIR}")"

: "${FILC_OUT:=${ROOT_DIR}/out}"
: "${WORK_DIR:=${TMPDIR:-/tmp}/fil-c-utils-tests}"

SEED_DIR="${WORK_DIR}/seed"
CORPUS_DIR="${WORK_DIR}/corpus"
HOSTILE_DIR="${WORK_DIR}/hostile"
FINDINGS_DIR="${WORK_DIR}/findings"

export FILC_OUT WORK_DIR SEED_DIR CORPUS_DIR HOSTILE_DIR FINDINGS_DIR

require_binaries() {
    local missing=()
    local b
    for b in 7z unrar tar gzip bzip2 xz zstd; do
        test -x "${FILC_OUT}/${b}" || missing+=("${b}")
    done
    if ((${#missing[@]})); then
        printf 'missing executables in %s: %s\n' "${FILC_OUT}" "${missing[*]}" >&2
        printf 'run ./build-all.sh first, or set FILC_OUT.\n' >&2
        return 1
    fi
}
