# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG GZIP_VERSION=1.14
ARG GZIP_SHA256=01a7b881bd220bfdf615f97b8718f80bdfd3f6add385b993dcf6efd14e8c0ac6

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG GZIP_VERSION
ARG GZIP_SHA256

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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/gzip.tar.xz \
        "https://ftp.gnu.org/gnu/gzip/gzip-${GZIP_VERSION}.tar.xz" \
    && echo "${GZIP_SHA256}  /tmp/gzip.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/gzip.tar.xz \
    && rm /tmp/gzip.tar.xz

RUN FORCE_UNSAFE_CONFIGURE=1 \
    CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g -DGNU_STANDARD=0" \
    LDFLAGS="-static" \
    ./configure --prefix=/usr \
    && make -j"$(nproc)"

RUN binary=/src/gzip \
    && file "${binary}" > /tmp/gzip.file \
    && grep -Fq "static-pie linked" /tmp/gzip.file \
    && readelf -lW "${binary}" > /tmp/gzip.segments \
    && ! grep -Fq " INTERP " /tmp/gzip.segments \
    && readelf -SW "${binary}" > /tmp/gzip.sections \
    && grep -Fq ".debug_info" /tmp/gzip.sections \
    && readelf -sW "${binary}" > /tmp/gzip.symbols \
    && grep -Fq "pizlonated" /tmp/gzip.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/gzip.symbols \
    && strings -a "${binary}" > /tmp/gzip.strings \
    && ! grep -q "@llvm\." /tmp/gzip.strings \
    && "${binary}" --version > /tmp/gzip.version \
    && grep -Fq "${GZIP_VERSION}" /tmp/gzip.version \
    && "${binary}" -c README > /tmp/smoke.gz \
    && "${binary}" -dc /tmp/smoke.gz > /tmp/smoke.out \
    && cmp README /tmp/smoke.out \
    && ln -s "${binary}" /tmp/gunzip \
    && ln -s "${binary}" /tmp/zcat \
    && /tmp/gunzip -c /tmp/smoke.gz > /tmp/gunzip.out \
    && /tmp/zcat /tmp/smoke.gz > /tmp/zcat.out \
    && cmp README /tmp/gunzip.out \
    && cmp README /tmp/zcat.out

# The project's own test suite is a build gate, as it is for curl. It exercises
# far more of the program than a round-trip smoke test can, and every case runs
# against the Fil-C binary.
RUN set -e; \
    make check > /tmp/gzip-check.log 2>&1 || { tail -40 /tmp/gzip-check.log; exit 1; }; \
    grep -E '^# (TOTAL|PASS|FAIL|SKIP)' /tmp/gzip-check.log; \
    total="$(sed -n 's/^# TOTAL: *//p' /tmp/gzip-check.log | tail -1)"; \
    test "${total}" -ge 25

RUN install -Dm755 gzip /artifact/gzip \
    && ln -s gzip /artifact/gunzip \
    && ln -s gzip /artifact/zcat \
    && install -Dm644 COPYING /artifact/licenses/gzip/COPYING \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG GZIP_VERSION

LABEL org.opencontainers.image.title="GNU gzip compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked GNU gzip with Fil-C memory safety" \
      org.opencontainers.image.version="${GZIP_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.gnu.org/software/gzip/" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

COPY --from=build /artifact/ /

ENTRYPOINT ["/gzip"]
