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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/bzip2.tar.gz \
        "https://sourceware.org/pub/bzip2/bzip2-${BZIP2_VERSION}.tar.gz" \
    && echo "${BZIP2_SHA256}  /tmp/bzip2.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/bzip2.tar.gz \
    && rm /tmp/bzip2.tar.gz

COPY patches/0001-clear-errno-before-getc-in-bzip2recover.patch /tmp/bzip2-recover.patch
RUN patch --batch --forward -p1 < /tmp/bzip2-recover.patch

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
        strings -a "${binary}" > "/tmp/${binary}.strings"; \
        ! grep -q "@llvm\." "/tmp/${binary}.strings"; \
    done \
    && ./bzip2 --help >/tmp/bzip2-help.txt 2>&1 \
    && ./bzip2 -c README > /tmp/smoke.bz2 \
    && ./bzip2 -dc /tmp/smoke.bz2 > /tmp/smoke.out \
    && cmp README /tmp/smoke.out

# bzip2recover was built and checked for provenance but never run, which is how
# it shipped unable to recover anything: after a getc returns EOF it tested
# errno without clearing it first, and on musl a stale EINVAL from an earlier
# call made every archive look like an I/O error. Under glibc errno happened to
# be zero. The patch above is upstream's own fix (pushed 2026-06-11, not yet in
# a release); running bzip2recover here is what makes it verifiable.
RUN set -e; \
    cd /tmp; \
    /src/bzip2 -1 -c /src/README > recover-me.bz2; \
    /src/bzip2recover recover-me.bz2 > /tmp/recover.log 2>&1 \
        || { cat /tmp/recover.log; exit 1; }; \
    grep -Fq "finished" /tmp/recover.log; \
    test -f rec00001recover-me.bz2; \
    /src/bzip2 -dc rec*recover-me.bz2 > recovered.out; \
    cmp /src/README recovered.out; \
    echo "bzip2recover recovered the archive intact"

# The project's own test suite is a build gate, as it is for curl. It exercises
# far more of the program than a round-trip smoke test can, and every case runs
# against the Fil-C binary.
RUN make test > /tmp/bzip2-test.log 2>&1 \
    || { tail -30 /tmp/bzip2-test.log; exit 1; }

RUN install -Dm755 bzip2 /artifact/bin/bzip2 \
    && install -Dm755 bzip2recover /artifact/bin/bzip2recover \
    && ln -s bzip2 /artifact/bin/bunzip2 \
    && ln -s bzip2 /artifact/bin/bzcat \
    && install -Dm644 LICENSE /artifact/licenses/bzip2/LICENSE \
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

# Aliases are symlinks, so creating them proves nothing about whether the
# program still selects its mode from argv[0]. bzip2recover shipped unable to
# work at all because it was built and checked but never run; these are the
# same shape. The shipped, stripped copies are exercised rather than the build
# tree, so this covers the links, the dispatch and the strip in one step.
RUN set -e; \
    printf 'alias dispatch %.0s' $(seq 1 200) > /tmp/alias.txt; \
    /artifact/bin/bzip2 -c /tmp/alias.txt > /tmp/alias.bz2; \
    /artifact/bin/bunzip2 -c /tmp/alias.bz2 | cmp - /tmp/alias.txt; \
    /artifact/bin/bzcat /tmp/alias.bz2 | cmp - /tmp/alias.txt; \
    echo "bunzip2 and bzcat dispatch"

FROM scratch AS artifact

ARG FILC_VERSION
ARG BZIP2_VERSION

LABEL org.opencontainers.image.title="bzip2 compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked bzip2 with Fil-C memory safety" \
      org.opencontainers.image.version="${BZIP2_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://sourceware.org/bzip2/" \
      org.opencontainers.image.licenses="bzip2-1.0.6"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/bzip2"]
