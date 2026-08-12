# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_X86_64_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG FILC_AARCH64_SHA256=405bcd4ea69bed4542581cd917581b2a34ae8e363cc5c76b701f27585de60e66
ARG NCURSES_VERSION=6.6
ARG NCURSES_SHA256=355b4cbbed880b0381a04c46617b7656e362585d52e9cf84a67e2009b749ff11
ARG FILE_VERSION=5.46
ARG FILE_SHA256=c9cc77c7c560c543135edc555af609d5619dbef011997e988ce40a3d75d86088
ARG NANO_VERSION=9.1
ARG NANO_SHA256=5f47764274cb7532349ce0aa20ec10f1e8e851a6e9fa3eb66812c43d196db042

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG NCURSES_VERSION
ARG NCURSES_SHA256
ARG FILE_VERSION
ARG FILE_SHA256
ARG NANO_VERSION
ARG NANO_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

# gcc builds the pseudo-terminal smoke harness only; the shipped nano is built
# entirely with the Fil-C clang.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        file \
        gcc \
        libc6-dev \
        linux-libc-dev \
        make \
        patchelf \
        pkg-config \
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

# nano needs a curses library and, for content-based syntax detection, libmagic.
# Fil-C's release ships only libc, libc++ and its runtime, so both are built
# here with the same compiler into a single /deps prefix.

# ncurses is on Fil-C's list of programs that build unchanged, and it does.
# --with-fallbacks compiles a set of common terminal descriptions directly into
# the library: the scratch image carries no terminfo database, so without this
# nano could not drive any terminal. The widec libraries are what give nano
# UTF-8 editing. --with-termlib splits the terminfo half into libtinfow, which
# is how nano's pkg-config link line comes out.
WORKDIR /ncurses
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/ncurses.tar.gz \
        "https://ftp.gnu.org/gnu/ncurses/ncurses-${NCURSES_VERSION}.tar.gz" \
    && echo "${NCURSES_SHA256}  /tmp/ncurses.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/ncurses.tar.gz \
    && rm /tmp/ncurses.tar.gz

RUN CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    ./configure --prefix=/deps \
        --without-shared \
        --without-debug \
        --without-ada \
        --without-cxx-binding \
        --without-manpages \
        --without-tests \
        --enable-widec \
        --enable-pc-files \
        --with-pkg-config-libdir=/deps/lib/pkgconfig \
        --with-termlib \
        --with-fallbacks="xterm,xterm-256color,linux,vt100,vt220,screen,screen-256color,tmux,tmux-256color,ansi,vt52,rxvt,putty,dumb" \
        --disable-stripping \
    && make -j"$(nproc)" \
    && make install

# libmagic gives nano a last-resort way to recognise a file's type from its
# content when the name and first line do not name a syntax. --datadir=/usr/share
# sets the database path compiled into the library to the platform's standard
# /usr/share/misc/magic, the same host-path approach curl uses for its CA
# bundle: a host with `file` installed supplies the database, and where it is
# absent nano simply falls back to name-based detection. The compression
# back-ends are turned off so libmagic pulls in nothing further.
WORKDIR /file
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/file.tar.gz \
        "https://astron.com/pub/file/file-${FILE_VERSION}.tar.gz" \
    && echo "${FILE_SHA256}  /tmp/file.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/file.tar.gz \
    && rm /tmp/file.tar.gz

# --datadir sets the database path compiled into the library, but `make install`
# would also write the 5.46-format magic.mgc to that path, replacing the build
# image's system database with one its own `file` (5.45) cannot read -- which
# then reports every binary as "data" and breaks the provenance checks below.
# Staging the install and copying only the pieces nano links against keeps the
# compiled-in path while leaving the build image's `file` working.
RUN CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    ./configure --prefix=/deps --datadir=/usr/share \
        --disable-shared \
        --enable-static \
        --disable-libseccomp \
        --disable-zlib \
        --disable-bzlib \
        --disable-xzlib \
        --disable-zstdlib \
        --disable-lzlib \
    && make -j"$(nproc)" \
    && make install DESTDIR=/tmp/filestage \
    && install -Dm644 /tmp/filestage/deps/lib/libmagic.a /deps/lib/libmagic.a \
    && install -Dm644 /tmp/filestage/deps/include/magic.h /deps/include/magic.h \
    && rm -rf /tmp/filestage

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/nano.tar.xz \
        "https://ftp.gnu.org/gnu/nano/nano-${NANO_VERSION}.tar.xz" \
    && echo "${NANO_SHA256}  /tmp/nano.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/nano.tar.xz \
    && rm /tmp/nano.tar.xz

COPY patches/0001-disable-x87-control-word-assembly-under-fil-c.patch /tmp/nano-fil-c.patch
RUN patch --batch --forward -p1 < /tmp/nano-fil-c.patch

# All of nano's features are on by default; only --enable-tiny and the
# individual --disable-* flags take any away, and none are given here. The
# explicit --enable-utf8 and the presence of libmagic are the two that depend
# on configuration, so both are asserted below rather than trusted. --prefix
# and --sysconfdir set the standard host paths nano reads its optional runtime
# data from (/etc/nanorc and /usr/share/nano); nothing is installed there, so a
# host that has them supplies syntax highlighting and where they are absent
# nano runs without it.
RUN PKG_CONFIG_PATH=/deps/lib/pkgconfig \
    CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    CPPFLAGS="-I/deps/include" \
    LDFLAGS="-static -L/deps/lib" \
    ./configure --prefix=/usr --sysconfdir=/etc --enable-utf8 \
    && grep -Fq "#define ENABLE_UTF8 1" config.h \
    && grep -Fq "#define HAVE_LIBMAGIC 1" config.h \
    && grep -Fq "#define HAVE_MAGIC_H 1" config.h

# lib is gnulib, src is nano itself. Building these two directly skips the doc
# subdirectory, whose makeinfo step is not needed for the program and is not
# installed.
RUN make -j"$(nproc)" -C lib \
    && make -j"$(nproc)" -C src

RUN binary=/src/src/nano; failed=0; \
    file "${binary}" > /tmp/nano.file; \
    grep -Fq "static-pie linked" /tmp/nano.file || { echo "FAIL: not static-pie: $(cat /tmp/nano.file)"; failed=1; }; \
    readelf -lW "${binary}" > /tmp/nano.segments; \
    grep -Fq " INTERP " /tmp/nano.segments && { echo "FAIL: has a program interpreter"; failed=1; }; \
    readelf -SW "${binary}" > /tmp/nano.sections; \
    grep -Fq ".debug_info" /tmp/nano.sections || { echo "FAIL: no .debug_info"; failed=1; }; \
    readelf -sW "${binary}" > /tmp/nano.symbols; \
    grep -Fq "pizlonated" /tmp/nano.symbols || { echo "FAIL: no pizlonated symbols"; failed=1; }; \
    grep -Eq "filc_call_user_main|zgc_alloc" /tmp/nano.symbols || { echo "FAIL: no Fil-C runtime symbol"; failed=1; }; \
    strings -a "${binary}" > /tmp/nano.strings; \
    grep -q "@llvm\." /tmp/nano.strings && { echo "FAIL: unhandled intrinsic:"; grep -o "@llvm\.[a-z0-9._]*" /tmp/nano.strings | sort -u; failed=1; }; \
    grep -Fq "cannot handle inline asm" /tmp/nano.strings && { echo "FAIL: unsupported inline assembly"; failed=1; }; \
    "${binary}" --version > /tmp/nano.version 2>&1; \
    grep -Fq "version ${NANO_VERSION}" /tmp/nano.version || { echo "FAIL: version string; got: $(cat /tmp/nano.version)"; failed=1; }; \
    test "${failed}" -eq 0 && echo "nano provenance checks passed"; \
    exit "${failed}"

# nano has no batch mode and ships no test suite, so the gate is to actually
# drive it through a pseudo-terminal: type a line, save, exit, and check the
# file. The harness forces the terminfo database off disk, so a pass also
# proves the compiled-in fallbacks are what let nano run in the scratch image.
COPY smoke.c /tmp/smoke.c
RUN gcc -O2 -o /tmp/smoke /tmp/smoke.c -lutil \
    && /tmp/smoke /src/src/nano /tmp/nano-smoke.txt

RUN install -Dm755 src/nano /artifact/bin/nano \
    && install -Dm644 COPYING /artifact/licenses/nano/COPYING \
    && install -Dm644 /ncurses/COPYING /artifact/licenses/ncurses/COPYING \
    && install -Dm644 /file/COPYING /artifact/licenses/file/COPYING \
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

FROM scratch AS artifact

ARG FILC_VERSION
ARG NANO_VERSION

LABEL org.opencontainers.image.title="GNU nano compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked GNU nano with Fil-C memory safety" \
      org.opencontainers.image.version="${NANO_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://git.savannah.gnu.org/cgit/nano.git" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/nano"]
