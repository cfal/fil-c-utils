#!/usr/bin/env bash
# Build the valid-archive corpus with the Fil-C binaries themselves, so the
# compression side is exercised before the fuzzer attacks the decoding side.
set -uo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
require_binaries || exit 1

export PATH="${FILC_OUT}:${PATH}"

rm -rf -- "${CORPUS_DIR}"
mkdir -p -- "${CORPUS_DIR}"

python3 "${TESTS_DIR}/make-seed.py" || exit 1
cd -- "${SEED_DIR}" || exit 1

C="${CORPUS_DIR}"
IN="${SEED_DIR}/text/repeat.txt"
BIN="${SEED_DIR}/bin/random.bin"
EMPTY="${WORK_DIR}/empty"
: > "${EMPTY}"

failures=0
mk() {
    local name="$1"; shift
    local log="${WORK_DIR}/mk-${name}.log"
    if ! "$@" > "${log}" 2>&1; then
        printf 'FAILED to build %s\n' "${name}" >&2
        sed -n 1,5p "${log}" >&2
        failures=$((failures + 1))
        return
    fi
    rm -f -- "${log}"
}

ALL="text bin edge names deep perm emptydir"

# ---- tar containers ---------------------------------------------------------
for fmt in gnu posix ustar oldgnu; do
    mk "tar-${fmt}" tar --format="${fmt}" -cf "${C}/seed.${fmt}.tar" ${ALL}
done
# v7 caps member names at 99 bytes, so it gets the shallow subset.
mk tar-v7        tar --format=v7 -cf "${C}/seed.v7.tar" text bin edge names perm
mk tar-links     tar --format=gnu -cf "${C}/links.tar" links
mk tar-many      tar --format=gnu -cf "${C}/many.tar" many
mk tar-sparse    tar --format=gnu --sparse -cf "${C}/sparse.tar" text/zeros.bin
mk tar-pax       tar --format=posix --pax-option='exthdr.name=%d/PaxHeaders/%f' \
                     -cf "${C}/pax.tar" names deep

# ---- single-stream compressors ---------------------------------------------
for lvl in 1 6 9; do
    mk "gz-${lvl}"  sh -c "gzip  -${lvl} -c '${IN}' > '${C}/repeat.${lvl}.gz'"
    mk "bz2-${lvl}" sh -c "bzip2 -${lvl} -c '${IN}' > '${C}/repeat.${lvl}.bz2'"
    mk "xz-${lvl}"  sh -c "xz    -${lvl} -c '${IN}' > '${C}/repeat.${lvl}.xz'"
    mk "zst-${lvl}" sh -c "zstd  -${lvl} -c -q '${IN}' > '${C}/repeat.${lvl}.zst'"
done
mk gz-bin   sh -c "gzip  -9 -c '${BIN}' > '${C}/random.gz'"
mk bz2-bin  sh -c "bzip2 -9 -c '${BIN}' > '${C}/random.bz2'"
mk xz-bin   sh -c "xz    -9 -c '${BIN}' > '${C}/random.xz'"
mk zst-bin  sh -c "zstd -19 -c -q '${BIN}' > '${C}/random.zst'"

# Container variants: checksum kinds, legacy framing, block splitting, threads.
for chk in none crc32 crc64 sha256; do
    mk "xz-chk-${chk}" sh -c "xz --check=${chk} -c '${IN}' > '${C}/repeat.chk-${chk}.xz'"
done
mk xz-lzma    sh -c "xz --format=lzma -c '${IN}' > '${C}/repeat.lzma'"
mk xz-blocks  sh -c "xz -6 --block-size=16384 -c '${BIN}' > '${C}/random.blocks.xz'"
mk xz-threads sh -c "xz -6 -T4 --block-size=32768 -c '${BIN}' > '${C}/random.mt.xz'"
mk zst-long   sh -c "zstd -19 --long=27 -c -q '${BIN}' > '${C}/random.long.zst'"
mk zst-ultra  sh -c "zstd --ultra -22 -c -q '${IN}' > '${C}/repeat.ultra.zst'"
mk zst-nochk  sh -c "zstd -6 --no-check -c -q '${IN}' > '${C}/repeat.nochk.zst'"
mk zst-mt     sh -c "zstd -6 -T4 -c -q '${BIN}' > '${C}/random.mt.zst'"
mk gz-rsync   sh -c "gzip --rsyncable -c '${IN}' > '${C}/repeat.rsync.gz'"

# Concatenated members and streams: a distinct parsing path from a single one.
mk gz-multi  sh -c "cat '${C}/repeat.1.gz'  '${C}/repeat.9.gz'  '${C}/random.gz'  > '${C}/multi.gz'"
mk bz2-multi sh -c "cat '${C}/repeat.1.bz2' '${C}/repeat.9.bz2' '${C}/random.bz2' > '${C}/multi.bz2'"
mk xz-multi  sh -c "cat '${C}/repeat.1.xz'  '${C}/repeat.9.xz'  '${C}/random.xz'  > '${C}/multi.xz'"
mk zst-multi sh -c "cat '${C}/repeat.1.zst' '${C}/repeat.9.zst' '${C}/random.zst' > '${C}/multi.zst'"

mk gz-empty  sh -c "gzip  -c '${EMPTY}' > '${C}/empty.gz'"
mk bz2-empty sh -c "bzip2 -c '${EMPTY}' > '${C}/empty.bz2'"
mk xz-empty  sh -c "xz    -c '${EMPTY}' > '${C}/empty.xz'"
mk zst-empty sh -c "zstd -c -q '${EMPTY}' > '${C}/empty.zst'"

# ---- compressed tarballs (tar drives the helper by name) --------------------
mk tgz  tar -czf "${C}/seed.tar.gz"  ${ALL}
mk tbz2 tar -cjf "${C}/seed.tar.bz2" ${ALL}
mk txz  tar -cJf "${C}/seed.tar.xz"  ${ALL}
mk tzst tar --zstd -cf "${C}/seed.tar.zst" ${ALL}

# ---- 7-Zip: one archive per codec, plus the containers it can also write ----
sevenz() { 7z "$@" -bso0 -bsp0; }
for m in LZMA LZMA2 BZip2 Deflate PPMd Copy; do
    mk "7z-${m}" sevenz a -t7z -m0="${m}" "${C}/seed.${m}.7z" text bin edge names deep perm
done
mk 7z-nosolid   sevenz a -t7z -ms=off "${C}/seed.nosolid.7z" many
mk 7z-solid     sevenz a -t7z -ms=on  "${C}/seed.solid.7z"   many
mk 7z-enc       sevenz a -t7z -ppassword         "${C}/seed.enc.7z"  text names
mk 7z-enchdr    sevenz a -t7z -ppassword -mhe=on "${C}/seed.ehdr.7z" text names
mk 7z-links     sevenz a -t7z -snl "${C}/links.7z" links
mk 7z-empty     sevenz a -t7z "${C}/empty.7z" edge/empty emptydir
mk 7z-zip       sevenz a -tzip "${C}/seed.zip" text bin edge names deep perm
mk 7z-zip-enc   sevenz a -tzip -ppassword "${C}/seed.enc.zip" text names
mk 7z-zip-store sevenz a -tzip -mm=Copy   "${C}/seed.store.zip" text names
mk 7z-tar       sevenz a -ttar   "${C}/seed.7ztar.tar" text names
mk 7z-gzip      sevenz a -tgzip  "${C}/repeat.7z.gz"  text/repeat.txt
mk 7z-bzip2     sevenz a -tbzip2 "${C}/repeat.7z.bz2" text/repeat.txt
mk 7z-xz        sevenz a -txz    "${C}/repeat.7z.xz"  text/repeat.txt

# ---- RAR: unrar cannot create archives, so synthesise RAR 5 headers ---------
python3 "${TESTS_DIR}/make-rar-corpus.py" "${C}" || failures=$((failures + 1))

printf 'corpus: %s archives, %s bytes in %s\n' \
    "$(find "${C}" -type f | wc -l)" "$(du -sb "${C}" | cut -f1)" "${C}"
exit $((failures > 0))
