# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG ZSTD_VERSION=1.5.7
ARG ZSTD_SHA256=eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG ZSTD_VERSION
ARG ZSTD_SHA256

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
RUN curl -fsSLo /tmp/zstd.tar.gz \
        "https://github.com/facebook/zstd/releases/download/v${ZSTD_VERSION}/zstd-${ZSTD_VERSION}.tar.gz" \
    && echo "${ZSTD_SHA256}  /tmp/zstd.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/zstd.tar.gz \
    && rm /tmp/zstd.tar.gz

COPY patches/0001-honor-ZSTD_DISABLE_ASM-in-ZSTD_selectAddr.patch /tmp/zstd-fil-c.patch
RUN patch --batch --forward -p1 < /tmp/zstd-fil-c.patch

RUN make -j"$(nproc)" zstd \
        CC=/opt/filc/build/bin/clang \
        CXX=/opt/filc/build/bin/clang++ \
        CFLAGS="-O2 -g" \
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
    && "${binary}" --version > /tmp/zstd.version \
    && grep -Fq "${ZSTD_VERSION}" /tmp/zstd.version \
    && "${binary}" -q -T2 -c README.md > /tmp/smoke.zst \
    && "${binary}" -q -dc /tmp/smoke.zst > /tmp/smoke.out \
    && cmp README.md /tmp/smoke.out

RUN install -Dm755 programs/zstd /artifact/zstd \
    && ln -s zstd /artifact/unzstd \
    && ln -s zstd /artifact/zstdcat \
    && install -Dm644 LICENSE /artifact/licenses/zstd/LICENSE \
    && install -Dm644 COPYING /artifact/licenses/zstd/COPYING \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG ZSTD_VERSION

LABEL org.opencontainers.image.title="Zstandard compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked zstd with Fil-C memory safety" \
      org.opencontainers.image.version="${ZSTD_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/facebook/zstd" \
      org.opencontainers.image.licenses="BSD-3-Clause OR GPL-2.0-only"

COPY --from=build /artifact/ /

ENTRYPOINT ["/zstd"]
