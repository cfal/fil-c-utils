# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG ZLIB_VERSION=1.3.2
ARG ZLIB_SHA256=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
# Held on OpenSSL 3.x while curl and git use 4.x. wget 1.25.0, the current
# release, does not support OpenSSL 4: it calls SSLv3_client_method, which 4.0
# removed, so it does not even compile. Guarding that call gets it to build, but
# five of wget's own TLS tests then fail (pfs, tlsv1, tlsv1x, clientcert, crl),
# and lowering the floor to accept that would be weakening a test to make a
# build pass. 3.5 is a supported LTS branch, so waiting for upstream costs
# nothing, and check-versions.py tracks this pin against the 3.x line so its
# security releases are still reported. Revisit when a wget release supports
# OpenSSL 4.
ARG OPENSSL_VERSION=3.6.3
ARG OPENSSL_SHA256=243a86649cf6f23eeb6a2ff2456e09e5d77dd9018a54d3d96b0c6bdd6ba6c7f1
ARG LIBUNISTRING_VERSION=1.4.2
ARG LIBUNISTRING_SHA256=5b46e74377ed7409c5b75e7a96f95377b095623b689d8522620927964a41499c
ARG LIBIDN2_VERSION=2.3.8
ARG LIBIDN2_SHA256=f557911bf6171621e1f72ff35f5b1825bb35b52ed45325dcdee931e5d3c0787a
ARG PCRE2_VERSION=10.47
ARG PCRE2_SHA256=c08ae2388ef333e8403e670ad70c0a11f1eed021fd88308d7e02f596fcd9dc16
ARG LIBPSL_VERSION=0.23.2
ARG LIBPSL_SHA256=f2ea0e59bffb36597a872f6ef89893ffa4c30196c87eff7aeb2c47e4e8c98133
ARG CARES_VERSION=1.34.8
ARG CARES_SHA256=c222b6d681096f9444d2c4863d2c1174019e27cacca0a4a5c114d36dd7d7bf78
ARG WGET_VERSION=1.25.0
ARG WGET_SHA256=766e48423e79359ea31e41db9e5c289675947a7fcf2efdcedb726ac9d0da3784

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG ZLIB_VERSION
ARG ZLIB_SHA256
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG LIBUNISTRING_VERSION
ARG LIBUNISTRING_SHA256
ARG LIBIDN2_VERSION
ARG LIBIDN2_SHA256
ARG PCRE2_VERSION
ARG PCRE2_SHA256
ARG LIBPSL_VERSION
ARG LIBPSL_SHA256
ARG CARES_VERSION
ARG CARES_SHA256
ARG WGET_VERSION
ARG WGET_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

# python3 builds libpsl's suffix-list data. perl, the HTTP/SSL Perl modules and
# python3 also run wget's own test suites, which gate the build. None of them
# end up in the artifact.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        file \
        libc6-dev \
        libhttp-daemon-perl \
        libio-socket-ssl-perl \
        libwww-perl \
        linux-libc-dev \
        make \
        patch \
        patchelf \
        perl \
        pkg-config \
        python3 \
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

# wget with all features needs a TLS backend, a compression library, IDN, the
# Public Suffix List, regular expressions and asynchronous DNS. Fil-C's release
# ships only libc, libc++ and its runtime, so each of these is built here with
# the same compiler into a single /deps prefix. Order matters: libidn2 needs
# libunistring, and libpsl needs libidn2.
ENV CC=/opt/filc/build/bin/clang
ENV PKG_CONFIG_PATH=/deps/lib/pkgconfig

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
RUN CFLAGS="-O2 -g" ./configure --static --prefix=/deps \
    && make -j"$(nproc)" \
    && make install

WORKDIR /libunistring
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/libunistring.tar.xz \
        "https://ftp.gnu.org/gnu/libunistring/libunistring-${LIBUNISTRING_VERSION}.tar.xz" \
    && echo "${LIBUNISTRING_SHA256}  /tmp/libunistring.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/libunistring.tar.xz \
    && rm /tmp/libunistring.tar.xz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
    && make -j"$(nproc)" \
    && make install

WORKDIR /libidn2
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/libidn2.tar.gz \
        "https://ftp.gnu.org/gnu/libidn/libidn2-${LIBIDN2_VERSION}.tar.gz" \
    && echo "${LIBIDN2_SHA256}  /tmp/libidn2.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/libidn2.tar.gz \
    && rm /tmp/libidn2.tar.gz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
        --with-libunistring-prefix=/deps --disable-doc \
    && make -j"$(nproc)" \
    && make install

# pcre2 is fetched as .tar.gz rather than the smaller .tar.bz2 the project also
# publishes, so the build image needs no bzip2 decompressor.
WORKDIR /pcre2
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/pcre2.tar.gz \
        "https://github.com/PCRE2Project/pcre2/releases/download/pcre2-${PCRE2_VERSION}/pcre2-${PCRE2_VERSION}.tar.gz" \
    && echo "${PCRE2_SHA256}  /tmp/pcre2.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/pcre2.tar.gz \
    && rm /tmp/pcre2.tar.gz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
        --enable-pcre2-8 --enable-unicode \
    && make -j"$(nproc)" \
    && make install

WORKDIR /libpsl
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/libpsl.tar.gz \
        "https://github.com/rockdaboot/libpsl/releases/download/${LIBPSL_VERSION}/libpsl-${LIBPSL_VERSION}.tar.gz" \
    && echo "${LIBPSL_SHA256}  /tmp/libpsl.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/libpsl.tar.gz \
    && rm /tmp/libpsl.tar.gz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
        --enable-runtime=libidn2 --enable-builtin=libidn2 --disable-gtk-doc \
    && make -j"$(nproc)" \
    && make install
# libpsl uses libunistring directly for UTF-8 case folding, but its installed
# pkg-config file records no dependency at all, so a static link that follows
# it puts libunistring before libpsl and fails to resolve uninorm_nfkc and
# u8_tolower. Declaring the libidn2 requirement, which itself pulls in
# libunistring, makes pkg-config emit the libraries in an order the static
# linker can satisfy in one pass, for wget and for its unit-test binary alike.
RUN echo "Requires.private: libidn2" >> /deps/lib/pkgconfig/libpsl.pc

WORKDIR /cares
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/cares.tar.gz \
        "https://github.com/c-ares/c-ares/releases/download/v${CARES_VERSION}/c-ares-${CARES_VERSION}.tar.gz" \
    && echo "${CARES_SHA256}  /tmp/cares.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/cares.tar.gz \
    && rm /tmp/cares.tar.gz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
        --disable-tests \
    && make -j"$(nproc)" \
    && make install

# no-asm is required: Fil-C cannot compile OpenSSL's hand-written assembly, so
# every primitive uses the portable C path. That costs throughput on TLS-heavy
# transfers and is the main price of this build.
#
# no-shared and no-module keep the build free of the linker version scripts
# that are the only change Fil-C's own OpenSSL port needed.
#
# --libdir=lib matters: OpenSSL defaults to lib64 on x86-64, while wget derives
# -L<prefix>/lib from the prefix, and the mismatch fails the static link with a
# bare "cannot find -lssl".
#
# OPENSSL_NO_SECURE_MEMORY disables the mlock-backed secure heap, the one piece
# Fil-C's port asserts is unused.
WORKDIR /openssl
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/openssl.tar.gz \
        "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" \
    && echo "${OPENSSL_SHA256}  /tmp/openssl.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/openssl.tar.gz \
    && rm /tmp/openssl.tar.gz
RUN ./Configure "linux-$(uname -m)" \
        no-shared \
        no-module \
        no-asm \
        no-tests \
        no-docs \
        no-engine \
        --prefix=/deps \
        --openssldir=/etc/ssl \
        --libdir=lib \
        -DOPENSSL_NO_SECURE_MEMORY \
        -O2 -g \
    && make -j"$(nproc)" \
    && make install_sw \
    && make install_ssldirs

# The CA bundle is read from the platform rather than embedded, matching curl in
# this repository: an environment without a bundle at this path, such as a
# scratch container, has to be given one with --ca-certificate, SSL_CERT_FILE,
# or a mounted file.
#
# --enable-iri turns on internationalized URLs through libidn2, --enable-pcre2
# selects PCRE2 for --regex-type, --with-cares gives asynchronous DNS, and
# NTLM, digest and opie authentication are all on. Metalink is left off: it
# needs GPGME for signature verification, which is not among the libraries
# ported to Fil-C. NLS is left off as it is for curl; the translations are the
# only thing it adds and musl carries no libintl.
WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/wget.tar.gz \
        "https://ftp.gnu.org/gnu/wget/wget-${WGET_VERSION}.tar.gz" \
    && echo "${WGET_SHA256}  /tmp/wget.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/wget.tar.gz \
    && rm /tmp/wget.tar.gz
RUN CFLAGS="-O2 -g" \
    CPPFLAGS="-I/deps/include" \
    LDFLAGS="-static -L/deps/lib" \
    PKG_CONFIG="pkg-config --static" \
    ./configure \
        --disable-shared \
        --enable-static \
        --with-ssl=openssl \
        --with-openssl \
        --with-libssl-prefix=/deps \
        --with-zlib \
        --with-libpsl \
        --enable-iri \
        --with-libidn2=/deps \
        --enable-pcre2 \
        --with-cares \
        --enable-ntlm \
        --enable-digest \
        --enable-opie \
        --disable-nls \
        --without-metalink \
    && make -j"$(nproc)"

RUN binary=/src/src/wget \
    && file "${binary}" > /tmp/wget.file \
    && grep -Fq "static-pie linked" /tmp/wget.file \
    && readelf -lW "${binary}" > /tmp/wget.segments \
    && ! grep -Fq " INTERP " /tmp/wget.segments \
    && readelf -SW "${binary}" > /tmp/wget.sections \
    && grep -Fq ".debug_info" /tmp/wget.sections \
    && readelf -sW "${binary}" > /tmp/wget.symbols \
    && grep -Fq "pizlonated" /tmp/wget.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/wget.symbols \
    && strings -a "${binary}" > /tmp/wget.strings \
    && ! grep -q "@llvm\." /tmp/wget.strings \
    && "${binary}" --version > /tmp/wget.version \
    && grep -Fq "GNU Wget ${WGET_VERSION}" /tmp/wget.version \
    && grep -Fq "+https" /tmp/wget.version \
    && grep -Fq "+ssl/openssl" /tmp/wget.version \
    && grep -Fq "+iri" /tmp/wget.version \
    && grep -Fq "+psl" /tmp/wget.version \
    && grep -Fq "+cares" /tmp/wget.version

# wget's own test suites are the gate: no artifact is produced unless they pass.
# tests/ drives HTTP, FTP and TLS servers written in Perl; testenv/ does the
# same in Python. Both are run directly rather than through the top-level
# `make check`, which also recurses into fuzz/. Those fuzzer harnesses are not
# a functional suite: they need a fuzzing runtime, ship no corpus in the
# release tarball, and their standalone driver calls dlsym at exit, which Fil-C
# forbids in a static build. wget itself never takes that path.
#
# The HTTPS tests point their client at a server named WgetTestingServer, which
# the suite maps to localhost through the HOSTALIASES environment variable.
# HOSTALIASES is a glibc feature; musl, which this wget is built against,
# ignores it, so the client cannot resolve the name and the eight HTTPS cases
# fail wherever the harness's own glibc lets the server start. The build cannot
# fix this from inside a RUN: /etc/hosts is read-only during a build. The name
# is supplied instead with `docker build --add-host WgetTestingServer:127.0.0.1`,
# which musl does honor; build-all.sh and the CI workflow pass it, and the
# README notes it for a standalone build. Without it the eight cases fail here.
#
# Each suite must succeed and clear a floor on the number of cases that ran, so
# a configuration change that quietly skips most of the suite cannot pass.
RUN set -e; \
    make -C tests check > /tmp/wget-tests.log 2>&1 \
        || { tail -40 /tmp/wget-tests.log; exit 1; }; \
    make -C testenv check > /tmp/wget-testenv.log 2>&1 \
        || { tail -40 /tmp/wget-testenv.log; exit 1; }; \
    tp="$(sed -n 's/^# PASS: *\([0-9][0-9]*\)/\1/p' /tmp/wget-tests.log | tail -1)"; \
    ep="$(sed -n 's/^# PASS: *\([0-9][0-9]*\)/\1/p' /tmp/wget-testenv.log | tail -1)"; \
    echo "wget tests/ passed: ${tp}, testenv/ passed: ${ep}"; \
    test "${tp:-0}" -ge 85; \
    test "${ep:-0}" -ge 45

RUN install -Dm755 src/wget /artifact/bin/wget \
    && install -Dm644 COPYING /artifact/licenses/wget/COPYING \
    && install -Dm644 /openssl/LICENSE.txt /artifact/licenses/openssl/LICENSE.txt \
    && install -Dm644 /zlib/LICENSE /artifact/licenses/zlib/LICENSE \
    && install -Dm644 /libunistring/COPYING /artifact/licenses/libunistring/COPYING \
    && install -Dm644 /libidn2/COPYING /artifact/licenses/libidn2/COPYING \
    && install -Dm644 /pcre2/LICENCE.md /artifact/licenses/pcre2/LICENCE.md \
    && install -Dm644 /libpsl/COPYING /artifact/licenses/libpsl/COPYING \
    && install -Dm644 /cares/LICENSE.md /artifact/licenses/c-ares/LICENSE.md \
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
# artifact can tell it was built with Fil-C at all.
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
        if /artifact/bin/wget -q --spider https://github.com/ 2>/tmp/tls.err; then \
            ok=yes; break; \
        fi; \
        grep -qiE 'cannot verify|certificate' /tmp/tls.err && break; \
        sleep 3; \
    done; \
    if [ "${ok}" != yes ]; then echo "HTTPS check failed:"; cat /tmp/tls.err; exit 1; fi; \
    echo "wget verifies a public certificate from the system trust store"

FROM scratch AS artifact

ARG FILC_VERSION
ARG WGET_VERSION

LABEL org.opencontainers.image.title="wget compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked GNU wget with Fil-C memory safety, OpenSSL, IDN, PSL and PCRE2" \
      org.opencontainers.image.version="${WGET_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.gnu.org/software/wget/" \
      org.opencontainers.image.licenses="GPL-3.0-or-later AND Apache-2.0 AND Zlib"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/wget"]
