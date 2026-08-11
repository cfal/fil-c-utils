# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG SEVENZIP_VERSION=26.02
ARG SEVENZIP_ARCHIVE_VERSION=2602
ARG SEVENZIP_SHA256=cf967c98bca02a4b8b16375f441825a8e141362f14be1969bbec8e1ca0bff9dd

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG SEVENZIP_VERSION
ARG SEVENZIP_ARCHIVE_VERSION
ARG SEVENZIP_SHA256

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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/7zip.tar.xz \
        "https://github.com/ip7z/7zip/releases/download/${SEVENZIP_VERSION}/7z${SEVENZIP_ARCHIVE_VERSION}-src.tar.xz" \
    && echo "${SEVENZIP_SHA256}  /tmp/7zip.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/7zip.tar.xz \
    && rm /tmp/7zip.tar.xz

COPY patches/0001-use-fil-c-cpu-intrinsics.patch /tmp/7zip-fil-c.patch
RUN sed -i 's/\r$//' C/CpuArch.c \
    && chmod u+w C/CpuArch.c \
    && patch --batch --forward -p1 < /tmp/7zip-fil-c.patch

COPY patches/0002-no-avx-paths-under-fil-c.patch /tmp/7zip-no-avx.patch
RUN for source in C/AesOpt.c C/Aes.c C/Blake2s.c C/LzFind.c C/SwapBytes.c \
                  C/Sha512Opt.c C/Sha512.c CPP/7zip/Crypto/MyAes.cpp; do \
        chmod u+w "${source}" && sed -i 's/\r$//' "${source}"; \
    done \
    && patch --batch --forward -p1 < /tmp/7zip-no-avx.patch

COPY patches/0003-use-portable-bit-reversal-on-fil-c-aarch64.patch /tmp/7zip-fil-c-arm.patch
RUN chmod u+w CPP/7zip/Compress/BitlDecoder.h \
    && sed -i 's/\r$//' CPP/7zip/Compress/BitlDecoder.h \
    && patch --batch --forward -p1 < /tmp/7zip-fil-c-arm.patch

WORKDIR /src/CPP/7zip/Bundles/Alone2
RUN make -f makefile.gcc -j"$(nproc)" \
        CC=/opt/filc/build/bin/clang \
        CXX=/opt/filc/build/bin/clang++ \
        CFLAGS_DEBUG="-DNDEBUG -g" \
        CFLAGS_BASE2="-DZ7_NO_LARGE_PAGES" \
        CXXFLAGS_BASE2="-DZ7_NO_LARGE_PAGES" \
        LFLAGS_STRIP= \
        LDFLAGS_STATIC_3=-static

# The `@llvm.` check is the one that matters here. Fil-C compiles an intrinsic
# it cannot lower into a trap, embedding the LLVM IR text as the panic message,
# so an unsupported intrinsic is invisible until a CPU that selects that path
# runs it. 7-Zip dispatches on CPUID at run time, which means a build can look
# perfect on one machine and abort on another. Grepping the binary for those
# embedded strings finds them without needing the CPU that would trigger them.
WORKDIR /src
RUN binary=/src/CPP/7zip/Bundles/Alone2/_o/7zz \
    && file "${binary}" > /tmp/7z.file \
    && grep -Fq "static-pie linked" /tmp/7z.file \
    && readelf -lW "${binary}" > /tmp/7z.segments \
    && ! grep -Fq " INTERP " /tmp/7z.segments \
    && readelf -SW "${binary}" > /tmp/7z.sections \
    && grep -Fq ".debug_info" /tmp/7z.sections \
    && readelf -sW "${binary}" > /tmp/7z.symbols \
    && grep -Fq "pizlonated" /tmp/7z.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/7z.symbols \
    && strings -a "${binary}" > /tmp/7z.strings \
    && ! grep -q "@llvm\." /tmp/7z.strings \
    && ! grep -Fq "cannot handle inline asm" /tmp/7z.strings \
    && "${binary}" i >/dev/null \
    && mkdir -p /tmp/smoke/input /tmp/smoke/output \
    && cp DOC/readme.txt /tmp/smoke/input/readme.txt \
    && "${binary}" a /tmp/smoke/archive.7z /tmp/smoke/input/readme.txt \
    && "${binary}" t /tmp/smoke/archive.7z \
    && "${binary}" x -o/tmp/smoke/output /tmp/smoke/archive.7z \
    && cmp /tmp/smoke/input/readme.txt /tmp/smoke/output/readme.txt \
    && "${binary}" a -t7z -m0=Deflate /tmp/smoke/deflate.7z /tmp/smoke/input/readme.txt \
    && "${binary}" t /tmp/smoke/deflate.7z \
    && "${binary}" a -tzip /tmp/smoke/archive.zip /tmp/smoke/input/readme.txt \
    && "${binary}" t /tmp/smoke/archive.zip

RUN install -Dm755 CPP/7zip/Bundles/Alone2/_o/7zz /artifact/bin/7z \
    && ln -s 7z /artifact/bin/7zz \
    && install -Dm644 DOC/License.txt /artifact/licenses/7zip/License.txt \
    && install -Dm644 DOC/unRarLicense.txt /artifact/licenses/7zip/unRarLicense.txt \
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
    /artifact/bin/7zz i > /dev/null; \
    /artifact/bin/7zz a -bso0 -bsp0 /tmp/alias.7z /tmp/alias.txt; \
    /artifact/bin/7zz t -bso0 -bsp0 /tmp/alias.7z; \
    echo "7zz dispatches"

FROM scratch AS artifact

ARG FILC_VERSION
ARG SEVENZIP_VERSION

LABEL org.opencontainers.image.title="7-Zip compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked 7-Zip with Fil-C memory safety" \
      org.opencontainers.image.version="${SEVENZIP_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/ip7z/7zip" \
      org.opencontainers.image.licenses="LicenseRef-7-Zip"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/7z"]
