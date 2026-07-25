# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG TAR_VERSION=1.35
ARG TAR_SHA256=4d62ff37342ec7aed748535323930c7cf94acf71c3591882b26a7ea50f3edc16

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG TAR_VERSION
ARG TAR_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

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
RUN curl -fsSLo /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-x86_64.tar.xz" \
    && echo "${FILC_SHA256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && rm /tmp/filc.tar.xz

WORKDIR /src
RUN curl -fsSLo /tmp/tar.tar.xz \
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

RUN install -Dm755 src/tar /artifact/tar \
    && install -Dm644 COPYING /artifact/licenses/tar/COPYING \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG TAR_VERSION

LABEL org.opencontainers.image.title="GNU tar compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked GNU tar with Fil-C memory safety" \
      org.opencontainers.image.version="${TAR_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.gnu.org/software/tar/" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

COPY --from=build /artifact/ /

ENTRYPOINT ["/tar"]
