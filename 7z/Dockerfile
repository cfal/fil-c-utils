# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG SEVENZIP_VERSION=26.02
ARG SEVENZIP_ARCHIVE_VERSION=2602
ARG SEVENZIP_SHA256=cf967c98bca02a4b8b16375f441825a8e141362f14be1969bbec8e1ca0bff9dd

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG SEVENZIP_VERSION
ARG SEVENZIP_ARCHIVE_VERSION
ARG SEVENZIP_SHA256

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
RUN curl -fsSLo /tmp/7zip.tar.xz \
        "https://github.com/ip7z/7zip/releases/download/${SEVENZIP_VERSION}/7z${SEVENZIP_ARCHIVE_VERSION}-src.tar.xz" \
    && echo "${SEVENZIP_SHA256}  /tmp/7zip.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/7zip.tar.xz \
    && rm /tmp/7zip.tar.xz

COPY patches/0001-use-fil-c-cpu-intrinsics.patch /tmp/7zip-fil-c.patch
RUN sed -i 's/\r$//' C/CpuArch.c \
    && chmod u+w C/CpuArch.c \
    && patch --batch --forward -p1 < /tmp/7zip-fil-c.patch

WORKDIR /src/CPP/7zip/Bundles/Alone2
RUN make -f makefile.gcc -j"$(nproc)" \
        CC=/opt/filc/build/bin/clang \
        CXX=/opt/filc/build/bin/clang++ \
        CFLAGS_DEBUG="-DNDEBUG -g" \
        CFLAGS_BASE2="-DZ7_NO_LARGE_PAGES" \
        CXXFLAGS_BASE2="-DZ7_NO_LARGE_PAGES" \
        LFLAGS_STRIP= \
        LDFLAGS_STATIC_3=-static

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
    && "${binary}" i >/dev/null \
    && mkdir -p /tmp/smoke/input /tmp/smoke/output \
    && cp DOC/readme.txt /tmp/smoke/input/readme.txt \
    && "${binary}" a /tmp/smoke/archive.7z /tmp/smoke/input/readme.txt \
    && "${binary}" t /tmp/smoke/archive.7z \
    && "${binary}" x -o/tmp/smoke/output /tmp/smoke/archive.7z \
    && cmp /tmp/smoke/input/readme.txt /tmp/smoke/output/readme.txt

RUN install -Dm755 CPP/7zip/Bundles/Alone2/_o/7zz /artifact/7z \
    && ln -s 7z /artifact/7zz \
    && install -Dm644 DOC/License.txt /artifact/licenses/7zip/License.txt \
    && install -Dm644 DOC/unRarLicense.txt /artifact/licenses/7zip/unRarLicense.txt \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG SEVENZIP_VERSION

LABEL org.opencontainers.image.title="7-Zip compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked 7-Zip with Fil-C memory safety" \
      org.opencontainers.image.version="${SEVENZIP_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/ip7z/7zip" \
      org.opencontainers.image.licenses="LicenseRef-7-Zip"

COPY --from=build /artifact/ /

ENTRYPOINT ["/7z"]
