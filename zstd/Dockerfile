# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG ZSTD_VERSION=1.5.7
ARG ZSTD_SHA256=eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG ZSTD_VERSION
ARG ZSTD_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        file \
        libc6-dev \
        linux-libc-dev \
        make \
        patch \
        patchelf \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/filc
RUN case "${TARGETARCH}" in \
        amd64) filc_arch=x86_64; filc_sha256="${FILC_X86_64_SHA256}" ;; \
        arm64) filc_arch=aarch64; filc_sha256="${FILC_AARCH64_SHA256}" ;; \
        *) echo "unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL ${FETCH_RETRY} -o /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-${filc_arch}.tar.xz" \
    && echo "${filc_sha256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && rm /tmp/filc.tar.xz

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/zstd.tar.gz \
        "https://github.com/facebook/zstd/releases/download/v${ZSTD_VERSION}/zstd-${ZSTD_VERSION}.tar.gz" \
    && echo "${ZSTD_SHA256}  /tmp/zstd.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/zstd.tar.gz \
    && rm /tmp/zstd.tar.gz

COPY patches/0001-honor-ZSTD_DISABLE_ASM-in-ZSTD_selectAddr.patch /tmp/zstd-fil-c.patch
RUN patch --batch --forward -p1 < /tmp/zstd-fil-c.patch

COPY patches/0002-align-optimal-repcodes-on-fil-c-aarch64.patch /tmp/zstd-fil-c-arm.patch
RUN patch --batch --forward -p1 < /tmp/zstd-fil-c-arm.patch

# Fil-C does not lower the structured NEON loads in Zstd's ARM row matcher and
# leaves them as run-time traps. The upstream flag selects its SWAR matcher on
# ARM only; x86 keeps the supported SIMD paths it already used.
RUN cflags="-O2 -g" \
    && if [ "${TARGETARCH}" = arm64 ]; then \
        cflags="${cflags} -DZSTD_NO_INTRINSICS"; \
    fi \
    && make -j"$(nproc)" zstd \
        CC=/opt/filc/build/bin/clang \
        CXX=/opt/filc/build/bin/clang++ \
        CFLAGS="${cflags}" \
        LDFLAGS="-static" \
        HAVE_ZLIB=0 \
        HAVE_LZMA=0 \
        HAVE_LZ4=0 \
        ZSTD_NO_ASM=1

RUN binary=/src/programs/zstd \
    && file "${binary}" > /tmp/zstd.file \
    && grep -Fq "static-pie linked" /tmp/zstd.file \
    && readelf -lW "${binary}" > /tmp/zstd.segments \
    && ! grep -Fq " INTERP " /tmp/zstd.segments \
    && readelf -SW "${binary}" > /tmp/zstd.sections \
    && grep -Fq ".debug_info" /tmp/zstd.sections \
    && readelf -sW "${binary}" > /tmp/zstd.symbols \
    && grep -Fq "pizlonated" /tmp/zstd.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/zstd.symbols \
    && strings -a "${binary}" > /tmp/zstd.strings \
    && if grep -q "@llvm\." /tmp/zstd.strings; then \
        echo "unhandled LLVM intrinsics in ${binary}:"; \
        grep -oE '@llvm\.[A-Za-z0-9._]+' /tmp/zstd.strings; \
        exit 1; \
    fi \
    && "${binary}" --version > /tmp/zstd.version \
    && grep -Fq "${ZSTD_VERSION}" /tmp/zstd.version \
    && "${binary}" -q -T2 -c README.md > /tmp/smoke.zst \
    && "${binary}" -q -dc /tmp/smoke.zst > /tmp/smoke.out \
    && cmp README.md /tmp/smoke.out

# The project's own test suite is a build gate, as it is for curl. It exercises
# far more of the program than a round-trip smoke test can, and every case runs
# against the Fil-C binary.
RUN set -e; \
    cflags="-O2 -g"; \
    if [ "${TARGETARCH}" = arm64 ]; then \
        cflags="${cflags} -DZSTD_NO_INTRINSICS"; \
    fi; \
    make check \
        CC=/opt/filc/build/bin/clang \
        CXX=/opt/filc/build/bin/clang++ \
        CFLAGS="${cflags}" \
        LDFLAGS="-static" \
        HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 ZSTD_NO_ASM=1 \
        > /tmp/zstd-check.log 2>&1 || { tail -40 /tmp/zstd-check.log; exit 1; }; \
    grep -Fq 'All tests completed successfully' /tmp/zstd-check.log; \
    echo 'zstd: all tests completed successfully'

RUN install -Dm755 programs/zstd /artifact/bin/zstd \
    && ln -s zstd /artifact/bin/unzstd \
    && ln -s zstd /artifact/bin/zstdcat \
    && install -Dm644 LICENSE /artifact/licenses/zstd/LICENSE \
    && install -Dm644 COPYING /artifact/licenses/zstd/COPYING \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

# Executables are built with -g so the checks above can read DWARF. The shipped
# copies drop it: debug information is most of their size and is recoverable by
# rebuilding. Fil-C keeps its own metadata for panic reports, so a stripped
# binary still names the file, line and function that failed.
#
# --strip-debug rather than a full strip, which would also discard .symtab and
# with it the pizlonated and filc_* symbols. Those are how anyone holding the
# artifact can tell it was built with Fil-C at all, and they cost about 7% of
# the size that a full strip would save.
RUN strip --strip-debug /artifact/bin/* \
    && for f in /artifact/bin/*; do \
        test -L "${f}" && continue; \
        readelf -SW "${f}" > /tmp/art.sections; \
        grep -Fq ".debug_info" /tmp/art.sections && exit 1; \
        readelf -sW "${f}" > /tmp/art.symbols; \
        grep -Fq "pizlonated" /tmp/art.symbols || exit 1; \
        grep -Eq "filc_call_user_main|zgc_alloc" /tmp/art.symbols || exit 1; \
        file "${f}" > /tmp/art.desc; \
        grep -Fq "static-pie linked" /tmp/art.desc || exit 1; \
    done \
    && echo "artifact binaries stripped of debug info, Fil-C symbols retained"

# Aliases are symlinks, so creating them proves nothing about whether the
# program still selects its mode from argv[0]. bzip2recover shipped unable to
# work at all because it was built and checked but never run; these are the
# same shape. The shipped, stripped copies are exercised rather than the build
# tree, so this covers the links, the dispatch and the strip in one step.
RUN set -e; \
    printf 'alias dispatch %.0s' $(seq 1 200) > /tmp/alias.txt; \
    /artifact/bin/zstd -q -c /tmp/alias.txt > /tmp/alias.zst; \
    /artifact/bin/unzstd -qc /tmp/alias.zst | cmp - /tmp/alias.txt; \
    /artifact/bin/zstdcat -q /tmp/alias.zst | cmp - /tmp/alias.txt; \
    echo "unzstd and zstdcat dispatch"

FROM scratch AS artifact

ARG FILC_VERSION
ARG ZSTD_VERSION

LABEL org.opencontainers.image.title="Zstandard compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked zstd with Fil-C memory safety" \
      org.opencontainers.image.version="${ZSTD_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/facebook/zstd" \
      org.opencontainers.image.licenses="BSD-3-Clause OR GPL-2.0-only"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/zstd"]
