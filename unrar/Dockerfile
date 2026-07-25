# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG UNRAR_VERSION=7.2.7
ARG UNRAR_SHA256=01d903a7dcf413cb2925696d7796e48e38d471f79bfe7ef3ad2aebf6c12dbefd
ARG RAR_FIXTURE_COMMIT=09fd4f216ef502e478f1aeb6f0e193b49056eee8
ARG RAR_FIXTURE_SHA256=4449d0e82e09f52af23a11cd84904625de8b15beafcf73e5c30dc3296beae0b2

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG UNRAR_VERSION
ARG UNRAR_SHA256
ARG RAR_FIXTURE_COMMIT
ARG RAR_FIXTURE_SHA256

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
RUN curl -fsSLo /tmp/unrar.tar.gz \
        "https://www.rarlab.com/rar/unrarsrc-${UNRAR_VERSION}.tar.gz" \
    && echo "${UNRAR_SHA256}  /tmp/unrar.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/unrar.tar.gz \
    && rm /tmp/unrar.tar.gz

RUN make -j"$(nproc)" \
        CXX=/opt/filc/build/bin/clang++ \
        CXXFLAGS="-O2 -g -std=c++11 -Wno-logical-op-parentheses -Wno-switch -Wno-dangling-else" \
        LDFLAGS="-static -pthread" \
        STRIP=/bin/true

RUN file ./unrar | grep -Fq "static-pie linked" \
    && ! readelf -l ./unrar | grep -q " INTERP " \
    && readelf -S ./unrar | grep -Fq ".debug_info" \
    && ./unrar >/tmp/unrar-help.txt

RUN curl -fsSLo /tmp/rar5-subdirs.rar \
        "https://raw.githubusercontent.com/markokr/rarfile/${RAR_FIXTURE_COMMIT}/test/files/rar5-subdirs.rar" \
    && echo "${RAR_FIXTURE_SHA256}  /tmp/rar5-subdirs.rar" | sha256sum -c - \
    && ./unrar t -idq /tmp/rar5-subdirs.rar \
    && mkdir -p /tmp/smoke \
    && ./unrar x -idq -o+ /tmp/rar5-subdirs.rar /tmp/smoke/ \
    && echo "ecdc5536f73bdae8816f0ea40726ef5e9b810d914493075903bb90623d97b1d8  /tmp/smoke/sub/dir1/file1.txt" | sha256sum -c - \
    && echo "67ee5478eaadb034ba59944eb977797b49ca6aa8d3574587f36ebcbeeb65f70e  /tmp/smoke/sub/dir2/file2.txt" | sha256sum -c -

RUN install -Dm755 unrar /artifact/unrar \
    && install -Dm644 license.txt /artifact/licenses/unrar/license.txt \
    && install -Dm644 acknow.txt /artifact/licenses/unrar/acknow.txt \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG UNRAR_VERSION

LABEL org.opencontainers.image.title="unRAR compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked RAR extractor with Fil-C memory safety" \
      org.opencontainers.image.version="${UNRAR_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.rarlab.com/rar_add.htm" \
      org.opencontainers.image.licenses="LicenseRef-unRAR"

COPY --from=build /artifact/ /

ENTRYPOINT ["/unrar"]
