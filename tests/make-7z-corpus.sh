#!/usr/bin/env bash
# Build the 7-Zip-specific part of the corpus.
#
# 7-Zip is the widest attack surface in this repository by a large margin: it
# compiles in about sixty container handlers and two dozen codecs, and its
# published vulnerability history sits mostly in the filesystem, disk-image and
# installer handlers rather than in .7z or .zip. Fuzzing only the containers
# 7-Zip can write would leave nearly all of that untested.
#
# Three sources feed the corpus:
#   1. the codec and filter matrix, written by 7-Zip itself
#   2. real containers built by tests/formats (needs Docker, skipped without it)
#   3. hand-written containers for formats no Linux tool still produces
#
# Every file is recorded in 7z-manifest.tsv with the handler it targets, so the
# fuzzer can force that handler with -t instead of relying on magic bytes that
# a mutation may have destroyed.
set -uo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

C="${CORPUS_DIR}"
MANIFEST="${C}/7z-manifest.tsv"
SEVENZ="${FILC_OUT}/7z"
IMAGE="${FILC_FORMATS_IMAGE:-filc-formats}"
PLATFORM="${PLATFORM:-linux/amd64}"

mkdir -p -- "${C}"
: > "${MANIFEST}"

test -x "${SEVENZ}" || { printf 'no 7z at %s\n' "${SEVENZ}" >&2; exit 1; }

failures=0
note() { printf '%s\t%s\n' "$1" "$2" >> "${MANIFEST}"; }

mk() {  # mk <name> <7z-type> <command...>
    local name="$1" type="$2"; shift 2
    if "$@" > "${WORK_DIR}/mk7z-${name}.log" 2>&1 && [ -s "${C}/${name}" ]; then
        note "${name}" "${type}"
        rm -f -- "${WORK_DIR}/mk7z-${name}.log"
    else
        printf 'FAILED to build %s\n' "${name}" >&2
        sed -n 1,4p "${WORK_DIR}/mk7z-${name}.log" >&2
        failures=$((failures + 1))
    fi
}

sevenz() { "${SEVENZ}" "$@" -bso0 -bsp0; }

# ---------------------------------------------------------------------------
# 1. Codec and filter matrix
#
# The branch filters are the interesting part: BCJ2 is a four-stream coder, and
# each architecture filter rewrites call targets in place, so all of them touch
# the decoded buffer directly.
# ---------------------------------------------------------------------------
SRC="${WORK_DIR}/7z-src"
rm -rf -- "${SRC}"
mkdir -p -- "${SRC}"
cp -- "${FILC_OUT}/bzip2" "${SRC}/exe.bin" 2>/dev/null || cp /bin/sh "${SRC}/exe.bin"
head -c 200000 "${SEED_DIR}/bin/random.bin" > "${SRC}/random.bin" 2>/dev/null \
    || head -c 200000 /dev/urandom > "${SRC}/random.bin"
cp -- "${SEED_DIR}/text/repeat.txt" "${SRC}/text.txt" 2>/dev/null \
    || printf 'compressible text\n%.0s' $(seq 1 2000) > "${SRC}/text.txt"

# Branch filters want executable input to have anything to transform.
for filter in BCJ BCJ2 ARM ARM64 ARMT PPC SPARC IA64 RISCV Delta:4 Swap2 Swap4; do
    tag="$(printf '%s' "${filter}" | tr -d ':')"
    mk "codec-${tag}.7z" 7z sevenz a -t7z "-m0=${filter}" "-m1=LZMA2" \
        "${C}/codec-${tag}.7z" "${SRC}/exe.bin" "${SRC}/text.txt"
done

for method in LZMA LZMA2 PPMd BZip2 Deflate Deflate64 Copy; do
    mk "codec-${method}.7z" 7z sevenz a -t7z "-m0=${method}" \
        "${C}/codec-${method}.7z" "${SRC}/text.txt" "${SRC}/random.bin"
done

# Encryption: payload only, then payload plus header.
mk codec-aes.7z      7z sevenz a -t7z -ppassword          "${C}/codec-aes.7z" "${SRC}/text.txt"
mk codec-aes-hdr.7z  7z sevenz a -t7z -ppassword -mhe=on  "${C}/codec-aes-hdr.7z" "${SRC}/text.txt"
mk codec-zip-aes.zip zip sevenz a -tzip -ppassword -mem=AES256 "${C}/codec-zip-aes.zip" "${SRC}/text.txt"
mk codec-zip-zipcrypto.zip zip sevenz a -tzip -ppassword -mem=ZipCrypto \
    "${C}/codec-zip-zipcrypto.zip" "${SRC}/text.txt"

# Deep solid blocks and a large dictionary exercise different allocation paths.
mk codec-solid-big.7z 7z sevenz a -t7z -m0=LZMA2:d64k -ms=on -mqs=on \
    "${C}/codec-solid-big.7z" "${SRC}"

# wim is the one extra container 7-Zip can write, and it has its own handler.
mk fmt-wim.wim wim sevenz a -twim "${C}/fmt-wim.wim" "${SRC}/text.txt" "${SRC}/exe.bin"

# Multi-volume: the Split handler plus 7z's own volume chaining.
rm -f -- "${C}"/codec-multivol.7z.*
if sevenz a -t7z -v20k "${C}/codec-multivol.7z" "${SRC}/exe.bin" \
        > "${WORK_DIR}/mk7z-multivol.log" 2>&1 \
        && [ -s "${C}/codec-multivol.7z.001" ]; then
    note "codec-multivol.7z.001" "7z"
    rm -f -- "${WORK_DIR}/mk7z-multivol.log"
else
    printf 'FAILED to build codec-multivol\n' >&2
    failures=$((failures + 1))
fi

# ---------------------------------------------------------------------------
# 2. Real containers from the Docker generator
# ---------------------------------------------------------------------------
# Always rebuild rather than reusing whatever image happens to carry this tag:
# Docker's layer cache makes that nearly free when nothing changed, and an
# image left over from an older generate.sh would silently test the wrong thing.
if docker build --platform "${PLATFORM}" -t "${IMAGE}" "${TESTS_DIR}/formats" \
        > "${WORK_DIR}/formats-build.log" 2>&1; then
    staging="${WORK_DIR}/formats-out"
    rm -rf -- "${staging}"
    mkdir -p -- "${staging}"
    if docker run --rm --platform "${PLATFORM}" -v "${staging}:/out" "${IMAGE}" \
            > "${WORK_DIR}/formats-run.log" 2>&1 \
            && [ -s "${staging}/manifest.tsv" ]; then
        while IFS=$'\t' read -r name type; do
            [ -n "${name}" ] || continue
            cp -- "${staging}/${name}" "${C}/${name}"
            note "${name}" "${type}"
        done < "${staging}/manifest.tsv"
        # Continuation volumes carry no manifest entry; they are siblings.
        for extra in "${staging}"/fmt-split.0*; do
            [ -e "${extra}" ] && cp -n -- "${extra}" "${C}/" 2>/dev/null
        done
        printf 'formats: %s real containers\n' "$(wc -l < "${staging}/manifest.tsv")"
    else
        printf 'formats: generator run failed, see %s\n' "${WORK_DIR}/formats-run.log" >&2
        failures=$((failures + 1))
    fi
else
    printf 'formats: Docker unavailable, skipping real container generation\n'
    printf '         (filesystem and disk-image handlers will not be covered)\n'
fi

# ---------------------------------------------------------------------------
# 2b. Self-extracting shapes: an executable with an archive appended.
#
# 7-Zip scans executables for an embedded archive rather than requiring it at a
# fixed offset, so this reaches a scanning path that neither a plain executable
# nor a plain archive touches.
# ---------------------------------------------------------------------------
for host in fmt-pe64.exe fmt-elf.elf; do
    base="${C}/${host}"
    [ -s "${base}" ] || continue
    for payload in codec-LZMA2.7z seed.zip; do
        [ -s "${C}/${payload}" ] || continue
        name="sfx-${host%.*}-${payload%.*}.${host##*.}"
        cat -- "${base}" "${C}/${payload}" > "${C}/${name}"
        note "${name}" "$([ "${payload##*.}" = zip ] && echo zip || echo 7z)"
    done
done

# ---------------------------------------------------------------------------
# 3. Hand-written containers
# ---------------------------------------------------------------------------
syn="${WORK_DIR}/synthetic"
rm -rf -- "${syn}"
if python3 "${TESTS_DIR}/make-7z-synthetic.py" "${syn}" > "${WORK_DIR}/synthetic.log" 2>&1; then
    while IFS=$'\t' read -r name type; do
        [ -n "${name}" ] || continue
        cp -- "${syn}/${name}" "${C}/${name}"
        note "${name}" "${type}"
    done < "${syn}/manifest-synthetic.tsv"
    printf 'synthetic: %s containers\n' "$(wc -l < "${syn}/manifest-synthetic.tsv")"
else
    printf 'synthetic: generation failed\n' >&2
    failures=$((failures + 1))
fi

# ---------------------------------------------------------------------------
# Record every handler 7-Zip compiles in. The fuzzer forces each mutated file
# through handlers it was not built for as well as its own, which is the only
# way the formats with no Linux writer see structured input at all.
# ---------------------------------------------------------------------------
"${SEVENZ}" i 2>/dev/null \
    | awk '/^Formats:/{f=1;next} /^Codecs:/{f=0} f&&NF{s=substr($0,29); split(s,a," ");
           if(a[1]!="") print a[1]}' \
    | sort -u > "${C}/7z-handlers.txt"

# Record whether each container actually opens. A few hand-written ones carry
# the right magic but not a structure the handler accepts; they stay in the
# corpus as fuzz seeds, and this column stops the roundtrip stage from
# demanding a clean test from them.
tmp="${WORK_DIR}/7z-manifest.verified"
: > "${tmp}"
opened=0
while IFS=$'\t' read -r name type; do
    [ -n "${name}" ] || continue
    if "${SEVENZ}" t -y -ppassword "-t${type}" "${C}/${name}" >/dev/null 2>&1; then
        printf '%s\t%s\tyes\n' "${name}" "${type}" >> "${tmp}"
        opened=$((opened + 1))
    else
        printf '%s\t%s\tno\n' "${name}" "${type}" >> "${tmp}"
    fi
done < "${MANIFEST}"
mv -- "${tmp}" "${MANIFEST}"

printf '7z corpus: %s files (%s open cleanly), %s handlers known\n' \
    "$(wc -l < "${MANIFEST}")" "${opened}" "$(wc -l < "${C}/7z-handlers.txt")"
printf '           handlers with a real container: %s\n' \
    "$(cut -f2,3 "${MANIFEST}" | awk -F'\t' '$2=="yes"{print $1}' | sort -u | wc -l)"
exit $((failures > 0))
