# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG BZIP2_VERSION=1.0.8
ARG BZIP2_SHA256=ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG BZIP2_VERSION
ARG BZIP2_SHA256

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
RUN curl -fsSLo /tmp/bzip2.tar.gz \
        "https://sourceware.org/pub/bzip2/bzip2-${BZIP2_VERSION}.tar.gz" \
    && echo "${BZIP2_SHA256}  /tmp/bzip2.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/bzip2.tar.gz \
    && rm /tmp/bzip2.tar.gz

RUN make -j"$(nproc)" bzip2 bzip2recover \
        CC=/opt/filc/build/bin/clang \
        AR=/usr/bin/ar \
        RANLIB=/usr/bin/ranlib \
        CFLAGS="-Wall -Winline -O2 -g -D_FILE_OFFSET_BITS=64" \
        LDFLAGS="-static"

RUN for binary in bzip2 bzip2recover; do \
        file "${binary}" > "/tmp/${binary}.file"; \
        grep -Fq "static-pie linked" "/tmp/${binary}.file"; \
        readelf -lW "${binary}" > "/tmp/${binary}.segments"; \
        ! grep -Fq " INTERP " "/tmp/${binary}.segments"; \
        readelf -SW "${binary}" > "/tmp/${binary}.sections"; \
        grep -Fq ".debug_info" "/tmp/${binary}.sections"; \
        readelf -sW "${binary}" > "/tmp/${binary}.symbols"; \
        grep -Fq "pizlonated" "/tmp/${binary}.symbols"; \
        grep -Eq "filc_call_user_main|zgc_alloc" "/tmp/${binary}.symbols"; \
    done \
    && ./bzip2 --help >/tmp/bzip2-help.txt 2>&1 \
    && ./bzip2 -c README > /tmp/smoke.bz2 \
    && ./bzip2 -dc /tmp/smoke.bz2 > /tmp/smoke.out \
    && cmp README /tmp/smoke.out

RUN install -Dm755 bzip2 /artifact/bzip2 \
    && install -Dm755 bzip2recover /artifact/bzip2recover \
    && ln -s bzip2 /artifact/bunzip2 \
    && ln -s bzip2 /artifact/bzcat \
    && install -Dm644 LICENSE /artifact/licenses/bzip2/LICENSE \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG BZIP2_VERSION

LABEL org.opencontainers.image.title="bzip2 compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked bzip2 with Fil-C memory safety" \
      org.opencontainers.image.version="${BZIP2_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://sourceware.org/bzip2/" \
      org.opencontainers.image.licenses="bzip2-1.0.6"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bzip2"]
