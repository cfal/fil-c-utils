# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG TAR_VERSION=1.35
ARG TAR_SHA256=4d62ff37342ec7aed748535323930c7cf94acf71c3591882b26a7ea50f3edc16

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG TAR_VERSION
ARG TAR_SHA256

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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/tar.tar.xz \
        "https://ftp.gnu.org/gnu/tar/tar-${TAR_VERSION}.tar.xz" \
    && echo "${TAR_SHA256}  /tmp/tar.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/tar.tar.xz \
    && rm /tmp/tar.tar.xz

COPY patches/0001-preserve-obstack-pointer-provenance.patch /tmp/tar-fil-c.patch
RUN patch --batch --forward -p1 < /tmp/tar-fil-c.patch

RUN FORCE_UNSAFE_CONFIGURE=1 \
    CC=/opt/filc/build/bin/clang \
    CXX=/opt/filc/build/bin/clang++ \
    CFLAGS="-O2 -g" \
    LDFLAGS="-static" \
    ./configure \
        --prefix=/usr \
        --disable-acl \
        --disable-nls \
        --without-posix-acls \
        --without-selinux \
        --without-xattrs \
        --with-gzip=gzip \
        --with-bzip2=bzip2 \
        --with-xz=xz \
        --with-zstd=zstd \
    && make -j"$(nproc)"

RUN binary=/src/src/tar \
    && file "${binary}" > /tmp/tar.file \
    && grep -Fq "static-pie linked" /tmp/tar.file \
    && readelf -lW "${binary}" > /tmp/tar.segments \
    && ! grep -Fq " INTERP " /tmp/tar.segments \
    && readelf -SW "${binary}" > /tmp/tar.sections \
    && grep -Fq ".debug_info" /tmp/tar.sections \
    && readelf -sW "${binary}" > /tmp/tar.symbols \
    && grep -Fq "pizlonated" /tmp/tar.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/tar.symbols \
    && strings -a "${binary}" > /tmp/tar.strings \
    && ! grep -q "@llvm\." /tmp/tar.strings \
    && "${binary}" --version > /tmp/tar.version \
    && grep -Fq "${TAR_VERSION}" /tmp/tar.version \
    && "${binary}" --help > /tmp/tar.help \
    && grep -Fq "Valid arguments for the --quoting-style option are:" /tmp/tar.help \
    && mkdir -p /tmp/smoke/input /tmp/smoke/output \
    && cp README /tmp/smoke/input/readme \
    && ln -s readme /tmp/smoke/input/link \
    && "${binary}" -cf /tmp/smoke/archive.tar -C /tmp/smoke/input . \
    && "${binary}" -tf /tmp/smoke/archive.tar >/tmp/smoke/listing \
    && "${binary}" -xf /tmp/smoke/archive.tar -C /tmp/smoke/output \
    && cmp /tmp/smoke/input/readme /tmp/smoke/output/readme \
    && test "$(readlink /tmp/smoke/output/link)" = readme

# The project's own test suite is a build gate, as it is for curl. It exercises
# far more of the program than a round-trip smoke test can, and every case runs
# against the Fil-C binary.
RUN set -e; \
    make check > /tmp/tar-check.log 2>&1 || { tail -60 /tmp/tar-check.log; exit 1; }; \
    grep -E 'tests were successful|tests were skipped' /tmp/tar-check.log; \
    passed="$(sed -n 's/^\([0-9][0-9]*\) tests were successful.*/\1/p' /tmp/tar-check.log | tail -1)"; \
    test "${passed}" -ge 180

RUN install -Dm755 src/tar /artifact/bin/tar \
    && install -Dm644 COPYING /artifact/licenses/tar/COPYING \
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
ARG TAR_VERSION

LABEL org.opencontainers.image.title="GNU tar compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked GNU tar with Fil-C memory safety" \
      org.opencontainers.image.version="${TAR_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.gnu.org/software/tar/" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/tar"]
