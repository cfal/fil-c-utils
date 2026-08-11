# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG ZLIB_VERSION=1.3.2
ARG ZLIB_SHA256=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
ARG OPENSSL_VERSION=4.0.1
ARG OPENSSL_SHA256=2db3f3a0d6ea4b59e1f094ace2c8cd536dffb87cdc39084c5afa1e6f7f37dd09
ARG CURL_VERSION=8.21.0
ARG CURL_SHA256=aa1b66a70eace83dc624508745646c08ae561de512ab403adffb93ac87fc72e6

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG ZLIB_VERSION
ARG ZLIB_SHA256
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG CURL_VERSION
ARG CURL_SHA256

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
        perl \
        pkg-config \
        stunnel4 \
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

# curl needs a TLS backend and a compression library, and Fil-C's release ships
# only libc, libc++ and its runtime. Both dependencies are therefore built here
# with the same compiler, into a single /deps prefix.

# The release comes from GitHub rather than zlib.net: zlib.net returns HTTP 415
# to some GitHub Actions runners, which fails the build on a host that is
# otherwise reachable, while the madler/zlib release asset is byte-identical
# (same SHA-256) and served reliably.
WORKDIR /zlib
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/zlib.tar.gz \
        "https://github.com/madler/zlib/releases/download/v${ZLIB_VERSION}/zlib-${ZLIB_VERSION}.tar.gz" \
    && echo "${ZLIB_SHA256}  /tmp/zlib.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/zlib.tar.gz \
    && rm /tmp/zlib.tar.gz

RUN CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    ./configure --static --prefix=/deps \
    && make -j"$(nproc)" \
    && make install

WORKDIR /openssl
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/openssl.tar.gz \
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
# --libdir=lib matters: OpenSSL defaults to lib64 on these 64-bit targets,
# while curl derives -L<prefix>/lib from --with-openssl, and the mismatch fails
# the static link with a bare "cannot find -lssl".
#
# OPENSSL_NO_SECURE_MEMORY disables the mlock-backed secure heap, the one piece
# Fil-C's port asserts is unused.
RUN ./Configure "linux-$(uname -m)" \
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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/curl.tar.xz \
        "https://curl.se/download/curl-${CURL_VERSION}.tar.xz" \
    && echo "${CURL_SHA256}  /tmp/curl.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/curl.tar.xz \
    && rm /tmp/curl.tar.xz

# The CA bundle is read from the platform rather than embedded. curl's
# --with-ca-embed would compile a copy into the executable and then prefer it
# over the system store instead of falling back to it, so a host's certificate
# updates would stop applying. The cost is that an environment without a bundle
# at this path, such as a scratch container, has to be given one with --cacert,
# CURL_CA_BUNDLE, or a mounted file.
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
    && grep -Fq "zlib/${ZLIB_VERSION}" /tmp/curl.version

# curl's own test suite is the gate: no artifact is produced unless it passes.
# The suite's servers are built with the same compiler, so Fil-C sits on both
# ends of every connection rather than only on the client.
#
# stunnel is what makes the TLS cases runnable. Without it curl's suite skips
# 62 HTTPS tests and still reports success, which for a network client would
# leave the most important paths untested while looking healthy.
#
# The run is checked two ways. runtests.pl must succeed, and a floor is placed
# under the number of cases that actually ran, because a configuration change
# that quietly skips most of the suite would otherwise pass this step.
RUN set -e; \
    make -C tests LDFLAGS="-Wc,-static -L/deps/lib" > /tmp/curl-tests-build.log 2>&1; \
    cd tests; \
    if ! ./runtests.pl -n -a -j"$(nproc)" > /tmp/curl-tests.log 2>&1; then \
        failed="$(sed -n 's/^TESTFAIL: These test cases failed: *//p' \
            /tmp/curl-tests.log | tail -1)"; \
        if [ -n "${failed}" ]; then \
            echo "re-running failed tests serially for diagnostics: ${failed}"; \
            ./runtests.pl -n -a ${failed} || true; \
        fi; \
        tail -40 /tmp/curl-tests.log; \
        exit 1; \
    fi; \
    tail -2 /tmp/curl-tests.log; \
    ran="$(sed -n 's/^TESTDONE: \([0-9][0-9]*\) tests out of.*/\1/p' /tmp/curl-tests.log | tail -1)"; \
    echo "curl test cases run: ${ran}"; \
    test "${ran}" -ge 1600

RUN install -Dm755 src/curl /artifact/bin/curl \
    && install -Dm644 COPYING /artifact/licenses/curl/COPYING \
    && install -Dm644 /openssl/LICENSE.txt /artifact/licenses/openssl/LICENSE.txt \
    && install -Dm644 /zlib/LICENSE /artifact/licenses/zlib/LICENSE \
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

# A tool that cannot verify a real certificate is close to useless, and this
# breaks silently: the default trust path is compiled into OpenSSL, so nothing
# in the build output reveals it is wrong. wget shipped with exactly that fault,
# reaching for a directory that exists only inside this image. The check runs
# the installed binary with no flags and no environment, so it fails if the
# default is wrong rather than if the caller forgot an option.
#
# A certificate error is deterministic, so it fails immediately; only a network
# error is retried, which keeps a flaky runner from being reported as a trust
# problem.
RUN set -e; \
    ok=no; \
    for _ in 1 2 3; do \
        if /artifact/bin/curl -sS -o /dev/null https://github.com/ 2>/tmp/tls.err; then \
            ok=yes; break; \
        fi; \
        grep -qiE 'certificate|SSL peer|CA cert' /tmp/tls.err && break; \
        sleep 3; \
    done; \
    if [ "${ok}" != yes ]; then echo "HTTPS check failed:"; cat /tmp/tls.err; exit 1; fi; \
    echo "curl verifies a public certificate from the system trust store"

FROM scratch AS artifact

ARG FILC_VERSION
ARG CURL_VERSION

LABEL org.opencontainers.image.title="curl compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked curl with Fil-C memory safety and OpenSSL" \
      org.opencontainers.image.version="${CURL_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/curl/curl" \
      org.opencontainers.image.licenses="curl AND Apache-2.0 AND Zlib"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/curl"]
