# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG XZ_VERSION=5.8.3
ARG XZ_SHA256=fff1ffcf2b0da84d308a14de513a1aa23d4e9aa3464d17e64b9714bfdd0bbfb6

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG XZ_VERSION
ARG XZ_SHA256

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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/xz.tar.xz \
        "https://github.com/tukaani-project/xz/releases/download/v${XZ_VERSION}/xz-${XZ_VERSION}.tar.xz" \
    && echo "${XZ_SHA256}  /tmp/xz.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/xz.tar.xz \
    && rm /tmp/xz.tar.xz

RUN CC=/opt/filc/build/bin/clang \
    CXX=/opt/filc/build/bin/clang++ \
    CFLAGS="-O2 -g" \
    LDFLAGS="-static" \
    ./configure \
        --prefix=/usr \
        --disable-shared \
        --enable-static \
        --disable-nls \
        --disable-scripts \
        --disable-doc \
        --enable-sandbox=no \
        --disable-assembler \
    && make -j"$(nproc)" \
        CPPFLAGS="-DLZMA_RANGE_DECODER_CONFIG=0" \
        LDFLAGS="-Wc,-static"

RUN binary=/src/src/xz/xz \
    && file "${binary}" > /tmp/xz.file \
    && grep -Fq "static-pie linked" /tmp/xz.file \
    && readelf -lW "${binary}" > /tmp/xz.segments \
    && ! grep -Fq " INTERP " /tmp/xz.segments \
    && readelf -SW "${binary}" > /tmp/xz.sections \
    && grep -Fq ".debug_info" /tmp/xz.sections \
    && readelf -sW "${binary}" > /tmp/xz.symbols \
    && grep -Fq "pizlonated" /tmp/xz.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/xz.symbols \
    && strings -a "${binary}" > /tmp/xz.strings \
    && ! grep -q "@llvm\." /tmp/xz.strings \
    && "${binary}" --version > /tmp/xz.version \
    && grep -Fq "${XZ_VERSION}" /tmp/xz.version \
    && "${binary}" -T2 -c README > /tmp/smoke.xz \
    && "${binary}" -dc /tmp/smoke.xz > /tmp/smoke.out \
    && cmp README /tmp/smoke.out

# The project's own test suite is a build gate, as it is for curl. It exercises
# far more of the program than a round-trip smoke test can, and every case runs
# against the Fil-C binary.
RUN set -e; \
    make check > /tmp/xz-check.log 2>&1 || { tail -40 /tmp/xz-check.log; exit 1; }; \
    grep -E '^# (TOTAL|PASS|FAIL|SKIP)' /tmp/xz-check.log; \
    total="$(sed -n 's/^# TOTAL: *//p' /tmp/xz-check.log | tail -1)"; \
    test "${total}" -ge 15

RUN install -Dm755 src/xz/xz /artifact/xz \
    && ln -s xz /artifact/unxz \
    && ln -s xz /artifact/xzcat \
    && ln -s xz /artifact/lzma \
    && ln -s xz /artifact/unlzma \
    && ln -s xz /artifact/lzcat \
    && install -Dm644 COPYING /artifact/licenses/xz/COPYING \
    && install -Dm644 COPYING.0BSD /artifact/licenses/xz/COPYING.0BSD \
    && install -Dm644 COPYING.GPLv2 /artifact/licenses/xz/COPYING.GPLv2 \
    && install -Dm644 COPYING.GPLv3 /artifact/licenses/xz/COPYING.GPLv3 \
    && install -Dm644 COPYING.LGPLv2.1 /artifact/licenses/xz/COPYING.LGPLv2.1 \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG XZ_VERSION

LABEL org.opencontainers.image.title="XZ Utils compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked xz with Fil-C memory safety" \
      org.opencontainers.image.version="${XZ_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/tukaani-project/xz" \
      org.opencontainers.image.licenses="0BSD AND LGPL-2.1-or-later AND GPL-2.0-or-later AND GPL-3.0-or-later"

COPY --from=build /artifact/ /

ENTRYPOINT ["/xz"]
