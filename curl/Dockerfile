# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.681
ARG FILC_SHA256=84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787
ARG ZLIB_VERSION=1.3.1
ARG ZLIB_SHA256=9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23
ARG OPENSSL_VERSION=3.5.7
ARG OPENSSL_SHA256=a8c0d28a529ca480f9f36cf5792e2cd21984552a3c8e4aa11a24aa31aeac98e8
ARG CURL_VERSION=8.19.0
ARG CURL_SHA256=4eb41489790d19e190d7ac7e18e82857cdd68af8f4e66b292ced562d333f11df

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG ZLIB_VERSION
ARG ZLIB_SHA256
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG CURL_VERSION
ARG CURL_SHA256

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
        perl \
        pkg-config \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/filc
RUN curl -fsSLo /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-x86_64.tar.xz" \
    && echo "${FILC_SHA256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && rm /tmp/filc.tar.xz

# curl needs a TLS backend and a compression library, and Fil-C's release ships
# only libc, libc++ and its runtime. Both dependencies are therefore built here
# with the same compiler, into a single /deps prefix.

WORKDIR /zlib
RUN curl -fsSLo /tmp/zlib.tar.gz \
        "https://zlib.net/fossils/zlib-${ZLIB_VERSION}.tar.gz" \
    && echo "${ZLIB_SHA256}  /tmp/zlib.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/zlib.tar.gz \
    && rm /tmp/zlib.tar.gz

RUN CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    ./configure --static --prefix=/deps \
    && make -j"$(nproc)" \
    && make install

WORKDIR /openssl
RUN curl -fsSLo /tmp/openssl.tar.gz \
        "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" \
    && echo "${OPENSSL_SHA256}  /tmp/openssl.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/openssl.tar.gz \
    && rm /tmp/openssl.tar.gz

# no-asm is required: Fil-C cannot compile OpenSSL's hand-written assembly, so
# every primitive uses the portable C path. That costs throughput on TLS-heavy
# transfers and is the main price of this build.
#
# no-shared and no-module keep the build free of the linker version scripts
# that are the only change Fil-C's own OpenSSL port needed.
#
# --libdir=lib matters: OpenSSL defaults to lib64 on x86-64, while curl derives
# -L<prefix>/lib from --with-openssl, and the mismatch fails the static link
# with a bare "cannot find -lssl".
#
# OPENSSL_NO_SECURE_MEMORY disables the mlock-backed secure heap, the one piece
# Fil-C's port asserts is unused.
RUN ./Configure linux-x86_64 \
        no-shared \
        no-module \
        no-asm \
        no-tests \
        no-docs \
        no-engine \
        --prefix=/deps \
        --openssldir=/deps/ssl \
        --libdir=lib \
        -DOPENSSL_NO_SECURE_MEMORY \
        -O2 -g \
        CC=/opt/filc/build/bin/clang \
    && make -j"$(nproc)" \
    && make install_sw \
    && make install_ssldirs

WORKDIR /src
RUN curl -fsSLo /tmp/curl.tar.xz \
        "https://curl.se/download/curl-${CURL_VERSION}.tar.xz" \
    && echo "${CURL_SHA256}  /tmp/curl.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/curl.tar.xz \
    && rm /tmp/curl.tar.xz

# --with-ca-embed compiles the CA bundle into the executable, so the artifact
# verifies certificates with no files on disk at all. --with-ca-bundle keeps the
# conventional path usable as a runtime override.
RUN PKG_CONFIG_PATH=/deps/lib/pkgconfig \
    CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    LDFLAGS="-static -L/deps/lib" \
    ./configure \
        --disable-shared \
        --enable-static \
        --with-openssl=/deps \
        --with-zlib=/deps \
        --with-ca-bundle=/etc/ssl/certs/ca-certificates.crt \
        --with-ca-embed=/etc/ssl/certs/ca-certificates.crt \
        --without-libpsl \
        --without-libidn2 \
        --without-nghttp2 \
        --without-brotli \
        --without-zstd \
        --without-librtmp \
        --disable-ldap \
        --disable-ldaps \
        --disable-manual \
    && make -j"$(nproc)" LDFLAGS="-Wc,-static -L/deps/lib"

RUN binary=/src/src/curl \
    && file "${binary}" > /tmp/curl.file \
    && grep -Fq "static-pie linked" /tmp/curl.file \
    && readelf -lW "${binary}" > /tmp/curl.segments \
    && ! grep -Fq " INTERP " /tmp/curl.segments \
    && readelf -SW "${binary}" > /tmp/curl.sections \
    && grep -Fq ".debug_info" /tmp/curl.sections \
    && readelf -sW "${binary}" > /tmp/curl.symbols \
    && grep -Fq "pizlonated" /tmp/curl.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/curl.symbols \
    && strings -a "${binary}" > /tmp/curl.strings \
    && ! grep -q "@llvm\." /tmp/curl.strings \
    && "${binary}" --version > /tmp/curl.version \
    && grep -Fq "${CURL_VERSION}" /tmp/curl.version \
    && grep -Fq "OpenSSL/${OPENSSL_VERSION}" /tmp/curl.version \
    && grep -Fq "zlib/${ZLIB_VERSION}" /tmp/curl.version \
    && test "$(grep -c 'BEGIN CERTIFICATE' /tmp/curl.strings)" -ge 100

# The TLS path is tested against a server this build produced, so the check
# needs no network and cannot pass because of an accident of the environment.
# Both directions matter: a trusted chain has to succeed, and an untrusted one
# has to fail, or the artifact would appear to work while verifying nothing.
RUN set -e; \
    /deps/bin/openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
        -subj "/CN=localhost" -keyout /tmp/key.pem -out /tmp/cert.pem 2>/dev/null; \
    /deps/bin/openssl s_server -www -quiet -port 4433 \
        -cert /tmp/cert.pem -key /tmp/key.pem & \
    server=$!; \
    trusted=no; \
    for _ in $(seq 1 40); do \
        if /src/src/curl -sS --cacert /tmp/cert.pem https://localhost:4433/ \
                > /tmp/tls.out 2>/dev/null; then \
            trusted=yes; \
            break; \
        fi; \
        sleep 0.25; \
    done; \
    untrusted=accepted; \
    /src/src/curl -sS https://localhost:4433/ > /dev/null 2>&1 || untrusted=rejected; \
    kill "${server}" 2>/dev/null || true; \
    test "${trusted}" = yes; \
    grep -Fq "s_server" /tmp/tls.out; \
    test "${untrusted}" = rejected; \
    printf 'file protocol\n' > /tmp/local.txt; \
    /src/src/curl -sS "file:///tmp/local.txt" | grep -Fq "file protocol"

RUN install -Dm755 src/curl /artifact/curl \
    && install -Dm644 COPYING /artifact/licenses/curl/COPYING \
    && install -Dm644 /openssl/LICENSE.txt /artifact/licenses/openssl/LICENSE.txt \
    && install -Dm644 /zlib/LICENSE /artifact/licenses/zlib/LICENSE \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

FROM scratch AS artifact

ARG FILC_VERSION
ARG CURL_VERSION

LABEL org.opencontainers.image.title="curl compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked curl with Fil-C memory safety, OpenSSL and an embedded CA bundle" \
      org.opencontainers.image.version="${CURL_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/curl/curl" \
      org.opencontainers.image.licenses="curl AND Apache-2.0 AND Zlib"

COPY --from=build /artifact/ /

ENTRYPOINT ["/curl"]
