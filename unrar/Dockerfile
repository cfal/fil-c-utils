# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.682
ARG FILC_SHA256=cfa49af8090053dfa1be69656f0ca521f5e5b4e145652f37a33688b096764292
ARG UNRAR_VERSION=7.2.7
ARG UNRAR_SHA256=01d903a7dcf413cb2925696d7796e48e38d471f79bfe7ef3ad2aebf6c12dbefd
ARG RAR_FIXTURE_COMMIT=09fd4f216ef502e478f1aeb6f0e193b49056eee8
ARG RAR_FIXTURE_SHA256=4449d0e82e09f52af23a11cd84904625de8b15beafcf73e5c30dc3296beae0b2
ARG RAR_FIXTURE_ARCHIVE_SHA256=ddcc0da3ee181763a8bc42d1cab55abca2f0f994380a81435c932ab24603f430

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG UNRAR_VERSION
ARG UNRAR_SHA256
ARG RAR_FIXTURE_COMMIT
ARG RAR_FIXTURE_SHA256
ARG RAR_FIXTURE_ARCHIVE_SHA256

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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-x86_64.tar.xz" \
    && echo "${FILC_SHA256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && rm /tmp/filc.tar.xz

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/unrar.tar.gz \
        "https://www.rarlab.com/rar/unrarsrc-${UNRAR_VERSION}.tar.gz" \
    && echo "${UNRAR_SHA256}  /tmp/unrar.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/unrar.tar.gz \
    && rm /tmp/unrar.tar.gz

COPY patches/0001-disable-misaligned-accesses-under-fil-c.patch /tmp/unrar-fil-c.patch
RUN patch --batch --forward -p1 < /tmp/unrar-fil-c.patch

# The patch turns off ALLOW_MISALIGNED, which is what stops unRAR from packing
# its PPMd structures to one byte. Packed, those structures hold pointers at
# offsets 2, 4 and 12; Fil-C keeps a capability beside every pointer slot and
# requires natural alignment, so a RAR3 file that reaches the PPMd decoder
# panics the process. That fails no build check and no valid-archive test, so
# assert the layout directly instead of trusting the patch to have applied.
RUN printf '%s\n' \
        '#include "rar.hpp"' \
        '#include <cstddef>' \
        '#ifdef ALLOW_MISALIGNED' \
        '#error "ALLOW_MISALIGNED must stay off under Fil-C"' \
        '#endif' \
        'static_assert(offsetof(RARPPM_STATE,Successor) % alignof(void*) == 0, "RARPPM_STATE::Successor is unaligned");' \
        'static_assert(offsetof(RARPPM_CONTEXT,Suffix) % alignof(void*) == 0, "RARPPM_CONTEXT::Suffix is unaligned");' \
        'static_assert(offsetof(RARPPM_MEM_BLK,next) % alignof(void*) == 0, "RARPPM_MEM_BLK::next is unaligned");' \
        'static_assert(offsetof(RARPPM_MEM_BLK,prev) % alignof(void*) == 0, "RARPPM_MEM_BLK::prev is unaligned");' \
        > /tmp/alignment-assert.cpp \
    && /opt/filc/build/bin/clang++ -std=c++11 -I/src -Wno-invalid-offsetof \
        -fsyntax-only /tmp/alignment-assert.cpp

RUN make -j"$(nproc)" \
        CXX=/opt/filc/build/bin/clang++ \
        CXXFLAGS="-O2 -g -std=c++11 -Wno-logical-op-parentheses -Wno-switch -Wno-dangling-else" \
        LDFLAGS="-static -pthread" \
        STRIP=/bin/true

RUN file ./unrar > /tmp/unrar.file \
    && grep -Fq "static-pie linked" /tmp/unrar.file \
    && readelf -lW ./unrar > /tmp/unrar.segments \
    && ! grep -Fq " INTERP " /tmp/unrar.segments \
    && readelf -SW ./unrar > /tmp/unrar.sections \
    && grep -Fq ".debug_info" /tmp/unrar.sections \
    && readelf -sW ./unrar > /tmp/unrar.symbols \
    && grep -Fq "pizlonated" /tmp/unrar.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/unrar.symbols \
    && strings -a ./unrar > /tmp/unrar.strings \
    && ! grep -q "@llvm\." /tmp/unrar.strings \
    && ./unrar >/tmp/unrar-help.txt

RUN curl -fsSL ${FETCH_RETRY} -o /tmp/rar5-subdirs.rar \
        "https://raw.githubusercontent.com/markokr/rarfile/${RAR_FIXTURE_COMMIT}/test/files/rar5-subdirs.rar" \
    && echo "${RAR_FIXTURE_SHA256}  /tmp/rar5-subdirs.rar" | sha256sum -c - \
    && ./unrar t -idq /tmp/rar5-subdirs.rar \
    && mkdir -p /tmp/smoke \
    && ./unrar x -idq -o+ /tmp/rar5-subdirs.rar /tmp/smoke/ \
    && echo "ecdc5536f73bdae8816f0ea40726ef5e9b810d914493075903bb90623d97b1d8  /tmp/smoke/sub/dir1/file1.txt" | sha256sum -c - \
    && echo "67ee5478eaadb034ba59944eb977797b49ca6aa8d3574587f36ebcbeeb65f70e  /tmp/smoke/sub/dir2/file2.txt" | sha256sum -c -

RUN curl -fsSL ${FETCH_RETRY} -o /tmp/rarfile-fixtures.tar.gz \
        "https://github.com/markokr/rarfile/archive/${RAR_FIXTURE_COMMIT}.tar.gz" \
    && echo "${RAR_FIXTURE_ARCHIVE_SHA256}  /tmp/rarfile-fixtures.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/rarfile-fixtures \
    && tar -C /tmp/rarfile-fixtures --strip-components=1 -xzf /tmp/rarfile-fixtures.tar.gz \
    && rm /tmp/rarfile-fixtures.tar.gz \
    && test "$(find /tmp/rarfile-fixtures/test/files -maxdepth 1 -type f -name '*.rar' | wc -l)" -ge 50 \
    && for archive in /tmp/rarfile-fixtures/test/files/*.rar; do \
        name="$(basename "${archive}")"; \
        status=0; \
        ./unrar t -idq -ppassword "${archive}" > "/tmp/${name}.log" 2>&1 || status=$?; \
        test "${status}" -lt 128; \
        ! grep -Eqi "filc safety error|filc panic|segmentation fault|core dumped" "/tmp/${name}.log"; \
    done \
    && ./unrar t -idq -ppassword /tmp/rarfile-fixtures/test/files/unicode.rar

RUN install -Dm755 unrar /artifact/bin/unrar \
    && install -Dm644 license.txt /artifact/licenses/unrar/license.txt \
    && install -Dm644 acknow.txt /artifact/licenses/unrar/acknow.txt \
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

FROM scratch AS artifact

ARG FILC_VERSION
ARG UNRAR_VERSION

LABEL org.opencontainers.image.title="unRAR compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked RAR extractor with Fil-C memory safety" \
      org.opencontainers.image.version="${UNRAR_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.rarlab.com/rar_add.htm" \
      org.opencontainers.image.licenses="LicenseRef-unRAR"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/unrar"]
