#!/usr/bin/env bash
# Robustness suite for the executables in out/.
#
#   ./tests/run-tests.sh              # default depth, a few minutes
#   ./tests/run-tests.sh --iters 24   # deeper fuzzing
#   ./tests/run-tests.sh --quick      # smoke depth
#   ./tests/run-tests.sh alignment    # one stage only
#
# Stages: alignment, corpus, roundtrip, safety, fuzz.
set -uo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

# Mutations per archive per strategy. The corpus is ~345 archives and 11
# strategies, so one iteration is roughly 3800 mutated files and about three
# minutes on eight cores. Six is a reasonable post-build check; use --iters 24
# or more when the point is to go looking for something.
ITERS=6
JOBS="$(nproc 2>/dev/null || echo 4)"
FUZZ_SEED="0"
STAGES=()

while (($#)); do
    case "$1" in
        --iters) ITERS="$2"; shift 2 ;;
        --jobs) JOBS="$2"; shift 2 ;;
        --seed) FUZZ_SEED="$2"; shift 2 ;;
        --quick) ITERS=1; shift ;;
        --help|-h) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 0 ;;
        -*) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
        *) STAGES+=("$1"); shift ;;
    esac
done
((${#STAGES[@]})) || STAGES=(alignment corpus roundtrip safety fuzz)

require_binaries || exit 1
mkdir -p -- "${WORK_DIR}/home" "${WORK_DIR}/work"

declare -A RESULT=()
ORDER=()

stage() {
    local name="$1"; shift
    printf '\n\033[1m== %s ==\033[0m\n' "${name}"
    if "$@"; then RESULT[$name]=pass; else RESULT[$name]=FAIL; fi
    ORDER+=("${name}")
}

wanted() {
    local s
    for s in "${STAGES[@]}"; do [[ "$s" == "$1" ]] && return 0; done
    return 1
}

do_alignment() {
    # Two defects that compile cleanly and only abort later: a pointer field at
    # an unaligned offset, and an intrinsic Fil-C could not lower. Both are
    # visible in the binary without the input, or the CPU, that would hit them.
    local bins=()
    local b
    for b in "${FILC_OUT}"/*; do
        [[ -f "$b" && -x "$b" && ! -L "$b" ]] && bins+=("$b")
    done
    local report="${WORK_DIR}/alignment.txt"
    local status=0
    python3 "${TESTS_DIR}/scan-alignment.py" "${bins[@]}" > "${report}" || status=$?
    cat "${report}"
    # Exit 2 means the binaries carry no DWARF, which shipped artifacts do not:
    # they are stripped of debug info. Reporting that as a pass would be the
    # worst outcome, since the scan would have examined nothing, so it is called
    # out instead. The intrinsic half of the scan still ran.
    if [[ "${status}" -eq 2 ]]; then
        printf 'NOT SCANNED: these binaries are stripped, so the alignment half of\n'
        printf '             this stage examined nothing. Build with --target build\n'
        printf '             and point FILC_OUT at it to run it for real.\n'
    elif [[ "${status}" -ne 0 ]]; then
        printf 'FAIL: the scan could not run\n'
        return 1
    fi
    if grep -q 'misaligned pointer field' "${report}"; then
        printf 'FAIL: rebuild the affected utility; its Fil-C patch is not in effect\n'
        return 1
    fi
    if grep -q 'unhandled intrinsic' "${report}"; then
        printf 'FAIL: an intrinsic Fil-C cannot lower is compiled in. It aborts on\n'
        printf '      any CPU whose features select that path, whatever this one does.\n'
        return 1
    fi
    if [[ "${status}" -eq 2 ]]; then
        printf 'PARTIAL: no unhandled intrinsics; alignment needs an unstripped build\n'
        return 0
    fi
    printf 'PASS: no unaligned pointer fields, no unhandled intrinsics\n'
}

do_corpus() {
    bash "${TESTS_DIR}/make-corpus.sh" || return 1
    bash "${TESTS_DIR}/make-7z-corpus.sh" || return 1
    python3 "${TESTS_DIR}/make-hostile.py" "${HOSTILE_DIR}" || return 1
}

do_roundtrip() { python3 "${TESTS_DIR}/roundtrip.py"; }
do_safety()    { python3 "${TESTS_DIR}/extraction-safety.py"; }

do_fuzz() {
    python3 "${TESTS_DIR}/fuzz.py" --iters "${ITERS}" --jobs "${JOBS}" \
        --seed "${FUZZ_SEED}" --out "${WORK_DIR}/fuzz.jsonl"
}

printf 'executables: %s\nwork dir:    %s\n' "${FILC_OUT}" "${WORK_DIR}"

wanted alignment && stage alignment do_alignment
wanted corpus    && stage corpus    do_corpus
wanted roundtrip && stage roundtrip do_roundtrip
wanted safety    && stage safety    do_safety
wanted fuzz      && stage fuzz      do_fuzz

printf '\n\033[1m== summary ==\033[0m\n'
failed=0
for s in "${ORDER[@]}"; do
    printf '%-12s %s\n' "${s}" "${RESULT[$s]}"
    [[ "${RESULT[$s]}" == FAIL ]] && failed=1
done
((failed)) && printf '\nartifacts and reproducers: %s\n' "${WORK_DIR}"
exit "${failed}"
