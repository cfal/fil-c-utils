# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.683
ARG FILC_SHA256=0fbc2135ad30d5b0adf31289bcc6f0da0cc8db2323f4eac2978d5f83538d10c6
ARG ZLIB_VERSION=1.3.2
ARG ZLIB_SHA256=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
ARG OPENSSL_VERSION=4.0.1
ARG OPENSSL_SHA256=2db3f3a0d6ea4b59e1f094ace2c8cd536dffb87cdc39084c5afa1e6f7f37dd09
ARG CURL_VERSION=8.21.0
ARG CURL_SHA256=aa1b66a70eace83dc624508745646c08ae561de512ab403adffb93ac87fc72e6
ARG PCRE2_VERSION=10.47
ARG PCRE2_SHA256=c08ae2388ef333e8403e670ad70c0a11f1eed021fd88308d7e02f596fcd9dc16
ARG EXPAT_VERSION=2.8.3
ARG EXPAT_TAG=R_2_8_3
ARG EXPAT_SHA256=22920a86c83f32300b11463635b71f11137a917975af297725e55525027d4e50
ARG GIT_TEST_JOBS=
ARG GIT_VERSION=2.55.0
ARG GIT_SHA256=457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357

FROM ubuntu:24.04 AS build

ARG FILC_VERSION
ARG FILC_SHA256
ARG ZLIB_VERSION
ARG ZLIB_SHA256
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG CURL_VERSION
ARG CURL_SHA256
ARG PCRE2_VERSION
ARG PCRE2_SHA256
ARG EXPAT_VERSION
ARG EXPAT_TAG
ARG EXPAT_SHA256
ARG GIT_VERSION
ARG GIT_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

# perl and python3 are needed by git's test suite, which gates this build; git
# itself also installs perl helpers. None of them end up in the artifact.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        file \
        gettext \
        libc6-dev \
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
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-x86_64.tar.xz" \
    && echo "${FILC_SHA256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && rm /tmp/filc.tar.xz

# git needs zlib for its object store, libcurl for http and https remotes,
# OpenSSL beneath libcurl, PCRE2 for `grep -P`, and expat for pushing over
# http. Fil-C's release ships only libc, libc++ and its runtime, so each of
# these is built here with the same compiler into a single /deps prefix.
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

WORKDIR /expat
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/expat.tar.gz \
        "https://github.com/libexpat/libexpat/releases/download/${EXPAT_TAG}/expat-${EXPAT_VERSION}.tar.gz" \
    && echo "${EXPAT_SHA256}  /tmp/expat.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/expat.tar.gz \
    && rm /tmp/expat.tar.gz
RUN CFLAGS="-O2 -g" ./configure --disable-shared --enable-static --prefix=/deps \
        --without-docbook --without-examples --without-tests \
    && make -j"$(nproc)" \
    && make install

# no-asm is required: Fil-C cannot compile OpenSSL's hand-written assembly, so
# every primitive uses the portable C path. That costs throughput on TLS-heavy
# transfers and is the main price of this build.
#
# --libdir=lib matters: OpenSSL defaults to lib64 on x86-64, while curl and git
# derive -L<prefix>/lib from the prefix, and the mismatch fails the static link
# with a bare "cannot find -lssl".
#
# OPENSSL_NO_SECURE_MEMORY disables the mlock-backed secure heap, the one piece
# Fil-C's port asserts is unused.
WORKDIR /openssl
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/openssl.tar.gz \
        "https://github.com/openssl/openssl/releases/download/openssl-${OPENSSL_VERSION}/openssl-${OPENSSL_VERSION}.tar.gz" \
    && echo "${OPENSSL_SHA256}  /tmp/openssl.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/openssl.tar.gz \
    && rm /tmp/openssl.tar.gz
RUN ./Configure linux-x86_64 \
        no-shared no-module no-asm no-tests no-docs no-engine \
        --prefix=/deps --openssldir=/deps/ssl --libdir=lib \
        -DOPENSSL_NO_SECURE_MEMORY -O2 -g \
    && make -j"$(nproc)" \
    && make install_sw \
    && make install_ssldirs

# libcurl is what carries git's http and https remotes. It reads the CA bundle
# from the platform, as curl and wget do in this repository.
WORKDIR /curl
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/curl.tar.xz \
        "https://curl.se/download/curl-${CURL_VERSION}.tar.xz" \
    && echo "${CURL_SHA256}  /tmp/curl.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/curl.tar.xz \
    && rm /tmp/curl.tar.xz
RUN CFLAGS="-O2 -g" LDFLAGS="-L/deps/lib" ./configure \
        --disable-shared --enable-static --prefix=/deps \
        --with-openssl=/deps --with-zlib=/deps \
        --with-ca-bundle=/etc/ssl/certs/ca-certificates.crt \
        --without-libpsl --without-libidn2 --without-nghttp2 \
        --without-brotli --without-zstd --without-librtmp \
        --disable-ldap --disable-ldaps --disable-manual --disable-docs \
    && make -j"$(nproc)" \
    && make install

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/git.tar.xz \
        "https://mirrors.edge.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz" \
    && echo "${GIT_SHA256}  /tmp/git.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/git.tar.xz \
    && rm /tmp/git.tar.xz

# git stores an option's default in a single field that holds either a small
# integer or a pointer, declared `intptr_t defval`. Round-tripping a pointer
# through an integer discards the capability Fil-C keeps beside it, so every
# option with a string default produced an unusable pointer. The patch changes
# the field to `void *`, casts the integer readers back with (intptr_t), and
# adjusts each option table accordingly; it also makes compat/obstack allocate
# a fresh chunk rather than deriving one pointer from another allocation.
#
# Upstream Fil-C carries the same change against git 2.46.0. This is that work
# rebased onto 2.55.0, which needed more than a refresh: 2.55 restructured
# parse-options.c and added option tables 2.46 never had. The rebase was driven
# by the compiler rather than by hand, since changing the field type turns every
# remaining site into an error, and -Werror=int-conversion below keeps it that
# way for future updates.
COPY patches/0001-keep-pointer-provenance-in-parse-options-defval.patch /tmp/git-filc.patch
RUN patch --batch --forward -p1 < /tmp/git-filc.patch

# The settings go in config.mak rather than on the make command line or in the
# environment, because neither of those reaches this build. git's Makefile
# assigns CC, CFLAGS and LDFLAGS with plain `=`, and a makefile assignment beats
# the environment, so an exported CC=clang or LDFLAGS=-static is silently
# dropped. config.mak is included after those assignments and therefore wins.
#
# Using a file also means the build, the test suite and the install all read the
# same settings. git records the flags it built with and rebuilds when they
# change, so an install that passed a shorter list would recompile and relink
# the binaries that the tests just vetted.
#
# NO_RUST: git 2.55 builds some subsystems in Rust, and Fil-C compiles C and
#   C++ only. The C implementations they replace are still present and are what
#   this build uses.
# NO_REGEX=NeedsStartEnd: musl's regexec has no REG_STARTEND, so git's bundled
#   regex is used instead.
# NO_GETTEXT: musl carries no libintl, matching the other builds here.
# HAVE_SYNC_FILE_RANGE is cleared, having been set for Linux by
#   config.mak.uname. Fil-C's musl does not implement that syscall and aborts
#   the process on it, so a user who set core.fsyncMethod=batch, which git
#   documents as the fast way to write objects, lost the command outright.
#   Without it git takes the branch it already has for platforms that cannot do
#   a writeout-only flush: it warns that the method is unsupported and falls
#   back to a full fsync. This is a correctness fix rather than a test fix; it
#   was four failing test files that showed it.
# FSMONITOR_DAEMON_BACKEND and FSMONITOR_OS_SETTINGS are cleared for the same
#   reason, and config.mak.uname sets both for Linux as well. The built-in
#   filesystem monitor runs as a long-lived multi-threaded daemon, and under
#   Fil-C it dumps core: the file it leaves behind is what the test suite
#   noticed, reporting an untracked `core` in the working tree after
#   `git status`, with the client side reporting a reset connection and no IPC
#   response. Without the backend git says the daemon is unsupported here
#   instead of crashing, and core.fsmonitor still works in its hook form.
# RUNTIME_PREFIX: git runs a good part of itself as separate programs under
#   libexec/git-core, and without this it looks for them at the absolute path it
#   was configured with. It resolves that directory from the location of the
#   running binary instead, so the extracted tarball works wherever it is
#   unpacked. It refuses to build unless the paths it resolves are relative to
#   the prefix, which git's own defaults already are, so only prefix is set
#   here. prefix is compiled in, which is why it belongs beside the flags
#   rather than being passed at install time only.
# INSTALL_SYMLINKS decides the size of the artifact, and by a wide margin. git
#   installs a dashed alias of every built-in subcommand under libexec,
#   upstream as hard links to the one binary it has already installed. Docker
#   copies between stages in userspace and does not preserve hard links, so
#   each of about a hundred and fifty aliases arrived as its own full copy of
#   an eighty-eight megabyte executable, and the artifact was fourteen
#   gigabytes of the same program. Installed as symlinks instead they cost
#   nothing, and the tree is under a gigabyte.
#
#   The aliases themselves have to stay. Not installing them at all is the
#   larger saving on paper and it breaks git: cloning and pushing over the
#   local and ssh transports runs `git-upload-pack` and `git-receive-pack` by
#   name through a shell, so without those two files on disk a plain
#   `git clone ./repo` fails with "git-upload-pack: not found". Symlinking
#   gives the same size as dropping them, and keeps them working.
RUN printf '%s\n' \
        'CC = /opt/filc/build/bin/clang' \
        'CFLAGS = -O2 -g -Wall -I/deps/include -Werror=int-conversion' \
        'LDFLAGS = -static -L/deps/lib' \
        'ZLIB_PATH = /deps' \
        'USE_LIBPCRE2 = 1' \
        'LIBPCREDIR = /deps' \
        'EXPATDIR = /deps' \
        'CURLDIR = /deps' \
        'NEEDS_SSL_WITH_CURL = 1' \
        'NEEDS_CRYPTO_WITH_SSL = 1' \
        'CURL_LDFLAGS = -lcurl -lssl -lcrypto -lz' \
        'NO_RUST = 1' \
        'NO_REGEX = NeedsStartEnd' \
        'NO_GETTEXT = 1' \
        'NO_TCLTK = 1' \
        'NO_PYTHON = 1' \
        'HAVE_SYNC_FILE_RANGE =' \
        'FSMONITOR_DAEMON_BACKEND =' \
        'FSMONITOR_OS_SETTINGS =' \
        'prefix = /' \
        'RUNTIME_PREFIX = 1' \
        'INSTALL_SYMLINKS = 1' \
    > config.mak \
    && make -j"$(nproc)" all \
    && grep -Fq -- '-Werror=int-conversion' GIT-CFLAGS \
    && grep -Fq -- '-static' GIT-LDFLAGS \
    && grep -Fq /opt/filc/build/bin/clang GIT-CFLAGS

RUN for binary in git git-remote-http git-http-fetch git-daemon; do \
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
    && ./git --version > /tmp/git.version \
    && grep -Fq "git version ${GIT_VERSION}" /tmp/git.version

# git's own test suite is the gate: no artifact is produced unless it passes.
# It is by far the largest suite in this repository, over a thousand files, and
# it drives the binaries that were just built rather than a library.
#
# GIT_TEST_OPTS='--no-chain-lint' keeps per-test shell overhead down; the suite
# is run with prove so the files execute in parallel.
#
# The job count is deliberately half the processors rather than all of them.
# Each test file forks a great many short-lived processes, and the push tests in
# particular run a receive-pack on the other end of a pipe; saturating every
# core made four of those files block indefinitely on this machine while every
# one of them passed on its own. Halving the parallelism costs wall time and
# removes the contention.
#
# Every file runs. Six individual cases are skipped by name, all of them the
# same libc difference and none of them a Fil-C one: git converts encodings
# through musl's iconv, while the suite decides what to expect by running the
# distribution's iconv, which is glibc's. The two disagree in ways that are
# both correct.
#
#   t0028.3, t0028.8, t0028.11, t2082.2 expect the byte-order mark glibc writes
#     for UTF-16 and UTF-32. musl encodes big-endian without one, so the bytes
#     differ before git is involved. t2082 reaches the same conversion through
#     a parallel checkout.
#   t3434.3, t3434.6 compare ISO-2022-JP byte for byte. musl re-emits the shift
#     sequence around every character instead of holding it across a run: both
#     encodings are valid and decode to the same text, and only the bytes differ.
#
# Naming the cases rather than dropping the files keeps the other forty-nine
# assertions in them, which are what test the encoding machinery itself.
#
# Each file is given a fifteen minute ceiling, which is many times the slowest
# of them. Under a loaded machine a push or a clone occasionally stops making
# progress for good. That stall is not this build's doing and not git's: Fil-C's
# own git port stalls the same way under the same stress, while the same git
# source built against glibc came through it untouched. It lands on the push and
# fetch tests because those start the most processes.
#
# Killing the test file is not enough on its own, which is why each one runs
# through a wrapper rather than under a plain timeout. A stalled git survives
# its test: one was found still running, and still holding eight pipes, long
# after the file that started it was gone, reparented away and no longer any
# child of anything the timeout knew about. prove reads each file's output
# through a pipe and waits for end-of-file, which never comes while a survivor
# holds the write end, so prove waits for good with nothing left running to
# explain why. A process group is the one relationship that survives
# reparenting, so the wrapper gives each file its own session and sweeps that
# whole group afterwards, which turns a stall into an ordinary failed file that
# the retry below can pick up.
#
# The ceiling around the whole run stays as a backstop for anything that
# escapes even that. Two hours is several times what a healthy run takes,
# including on a hosted runner, where half the processors is two jobs rather
# than four.
#
# A file that fails, including one killed by either ceiling, is retried on its
# own before the build is failed. The retry is serial and covers only the
# files that failed, so a real failure still fails: a broken binary reproduces
# on its own, where a file that lost a race against fifty of its siblings does
# not. Anything that needed the retry is printed, because a file that keeps
# needing it is a finding rather than noise.
#
# A floor is placed under the number of files that ran, because a change that
# quietly stopped running most of the suite would otherwise look like a pass.
RUN printf '%s\n' \
        '#!/bin/sh' \
        '# Run one git test file so that nothing it starts can outlive it.' \
        '# setsid makes timeout a session leader, so its process group id is its' \
        '# own pid and everything the test starts inherits that group; sweeping' \
        '# the group afterwards therefore reaches processes that were reparented' \
        '# away and are no longer a child of anything. This wrapper stays outside' \
        '# the group, which is what lets it report the exit status.' \
        '#' \
        '# The ceiling is enforced by timeout inside the session rather than by a' \
        '# background watchdog here. A watchdog would inherit this stdout, which' \
        '# is a pipe to prove, and hold it open after the test finished; prove' \
        '# waits for end-of-file on that pipe, so the run would stop dead after' \
        '# as many files as it had jobs.' \
        'setsid timeout -k 30 900 /bin/sh "$@" &' \
        'pid=$!' \
        'wait "${pid}"; rc=$?' \
        'kill -9 -"${pid}" 2>/dev/null' \
        'exit "${rc}"' \
    > /usr/local/bin/git-test-one \
    && chmod +x /usr/local/bin/git-test-one

ARG GIT_TEST_JOBS

# The suite is bound by forking and file I/O rather than by CPU: each file runs
# a shell that spends most of its life waiting on processes and the filesystem.
# Tying the job count to core count therefore left the runner idle and the step
# taking most of an hour. A flat oversubscription keeps work queued instead.
# Overridable so the trade-off can be re-measured rather than assumed.
RUN set -e; \
    cd t; \
    jobs="${GIT_TEST_JOBS:-16}"; \
    test "${jobs}" -ge 1 || jobs=1; \
    started="$(date +%s)"; \
    ls t[0-9]*.sh > /tmp/git-test-files; \
    echo "running $(wc -l < /tmp/git-test-files) git test files with ${jobs} jobs"; \
    export GIT_TEST_OPTS='--no-chain-lint'; \
    export GIT_SKIP_TESTS='t0028.3 t0028.8 t0028.11 t2082.2 t3434.3 t3434.6'; \
    if ! timeout -k 60 7200 \
         prove --exec /usr/local/bin/git-test-one \
              --jobs "${jobs}" $(cat /tmp/git-test-files) > /tmp/git-tests.log 2>&1; then \
        failed="$(sed -n 's/^\(t[0-9][^ ]*\.sh\) *(Wstat:.*/\1/p' /tmp/git-tests.log | sort -u)"; \
        if test -z "${failed}"; then \
            echo "the suite produced no per-file failures, so it did not finish;"; \
            echo "these files never reported a result:"; \
            sed -n 's/^\(t[0-9][^ ]*\.sh\) .*/\1/p' /tmp/git-tests.log | sort -u > /tmp/git-reported; \
            comm -23 /tmp/git-test-files /tmp/git-reported | head -20; \
            grep -E 'Wstat|Failed:|^Result:' /tmp/git-tests.log | tail -20; \
            exit 1; \
        fi; \
        echo "failed under load, retrying one at a time: ${failed}"; \
        if ! timeout -k 60 3600 \
             prove --exec /usr/local/bin/git-test-one \
                  --jobs 1 ${failed} > /tmp/git-retry.log 2>&1; then \
            grep -E 'Wstat|Failed:|^Result:' /tmp/git-retry.log | tail -30; \
            exit 1; \
        fi; \
        echo "PASSED ONLY ON RETRY: ${failed}"; \
    fi; \
    grep -E '^Files=|^Result:' /tmp/git-tests.log; \
    echo "git test wall time: $(( $(date +%s) - started ))s with ${jobs} jobs on $(nproc) cpus"; \
    ran="$(sed -n 's/^Files=\([0-9][0-9]*\),.*/\1/p' /tmp/git-tests.log | tail -1)"; \
    echo "git test files run: ${ran}"; \
    test "${ran:-0}" -ge 1040

# git installs a large tree: the executables, the exec-path helpers it runs as
# subprocesses, and its templates. Everything that shapes that tree is in
# config.mak, so only the staging directory is given here; passing any of it
# again would count as a build-flag change and rebuild what the tests vetted.
RUN make install DESTDIR=/artifact \
    && install -Dm644 COPYING /artifact/licenses/git/COPYING \
    && install -Dm644 LGPL-2.1 /artifact/licenses/git/LGPL-2.1 \
    && install -Dm644 /openssl/LICENSE.txt /artifact/licenses/openssl/LICENSE.txt \
    && install -Dm644 /zlib/LICENSE /artifact/licenses/zlib/LICENSE \
    && install -Dm644 /curl/COPYING /artifact/licenses/curl/COPYING \
    && install -Dm644 /pcre2/LICENCE.md /artifact/licenses/pcre2/LICENCE.md \
    && install -Dm644 /expat/COPYING /artifact/licenses/expat/COPYING \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

# bin/ is the directory that ends up on someone's PATH, and everything this
# repository puts there is a static executable. git installs one thing that is
# not: git-cvsserver, a Perl script. It cannot run from the artifact, which
# carries no interpreter, and it is the reason the bundle refused the tree,
# since that job reads every executable file in bin/ with readelf and stops on
# the first that is not an ELF binary. Dropping whatever is not one makes the
# tree match what the README already says it contains. The type is written to
# a file rather than piped into grep: grep exits at the first match, file dies
# on SIGPIPE, and under pipefail the pipeline reports failure for a binary
# that was perfectly good.
RUN set -e; \
    for f in /artifact/bin/*; do \
        if [ -L "${f}" ]; then continue; fi; \
        file -b "${f}" > /tmp/bin-type; \
        if grep -q '^ELF ' /tmp/bin-type; then continue; fi; \
        echo "dropping ${f##*/}: $(cat /tmp/bin-type)"; \
        rm -f "${f}"; \
    done; \
    echo "bin/ holds: $(ls /artifact/bin | tr '\n' ' ')"

# Executables are built with -g so the checks above can read DWARF. The shipped
# copies drop it: debug information is most of their size and is recoverable by
# rebuilding. Fil-C keeps its own metadata for panic reports, so a stripped
# binary still names the file, line and function that failed.
#
# --strip-debug rather than a full strip, which would also discard .symtab and
# with it the pizlonated and filc_* symbols. Those are how anyone holding the
# artifact can tell it was built with Fil-C at all.
#
# git ships many of its subcommands as hard links to the same executable, so
# the loop skips anything already stripped rather than doing the work again.
RUN find /artifact/bin /artifact/libexec -type f -perm -u+x -print0 \
        | xargs -0 -r strip --strip-debug 2>/dev/null || true; \
    for f in /artifact/bin/git /artifact/libexec/git-core/git-remote-http; do \
        test -f "${f}" || continue; \
        readelf -SW "${f}" > /tmp/art.sections; \
        grep -Fq ".debug_info" /tmp/art.sections && exit 1; \
        readelf -sW "${f}" > /tmp/art.symbols; \
        grep -Fq "pizlonated" /tmp/art.symbols || exit 1; \
        grep -Eq "filc_call_user_main|zgc_alloc" /tmp/art.symbols || exit 1; \
        file "${f}" > /tmp/art.desc; \
        grep -Fq "static-pie linked" /tmp/art.desc || exit 1; \
    done \
    && echo "artifact binaries stripped of debug info, Fil-C symbols retained"

# The shipped, stripped copy is exercised rather than the build tree, so this
# covers the install layout and the strip in one step. A program that is built
# and checked but never run can ship unable to do its job.
RUN set -e; \
    export HOME=/tmp/githome; \
    mkdir -p "${HOME}"; \
    /artifact/bin/git config --global user.email builder@example.com; \
    /artifact/bin/git config --global user.name Builder; \
    /artifact/bin/git config --global init.defaultBranch main; \
    rm -rf /tmp/smoke && mkdir -p /tmp/smoke && cd /tmp/smoke; \
    /artifact/bin/git init -q .; \
    printf 'hello\n' > file.txt; \
    /artifact/bin/git add file.txt; \
    /artifact/bin/git commit -q -m 'initial commit'; \
    /artifact/bin/git tag -a v1 -m 'a tag'; \
    test "$(/artifact/bin/git tag -n | wc -l)" -eq 1; \
    /artifact/bin/git log --oneline | grep -Fq 'initial commit'; \
    printf 'second\n' >> file.txt; \
    /artifact/bin/git diff --stat | grep -Fq file.txt; \
    /artifact/bin/git grep -P 'he.lo' -- file.txt; \
    /artifact/bin/git clone -q . /tmp/smoke-clone; \
    test -f /tmp/smoke-clone/file.txt; \
    echo 'git init, commit, tag, log, diff, grep -P and clone all work'

# git finds the programs under libexec/git-core relative to its own binary, so
# the tarball has to work from wherever it is unpacked rather than only from the
# path it was configured with. Unpacking it somewhere else and asking git where
# it would look is what proves that, and it is worth proving: with a compiled-in
# path this still passes every check above and then fails on the user's machine.
RUN set -e; \
    rm -rf /tmp/relocated; \
    mkdir -p /tmp/relocated; \
    cp -a /artifact/bin /artifact/libexec /tmp/relocated/; \
    found="$(/tmp/relocated/bin/git --exec-path)"; \
    test "${found}" = /tmp/relocated/libexec/git-core; \
    export HOME=/tmp/githome; \
    rm -rf /tmp/reloc-repo && mkdir -p /tmp/reloc-repo && cd /tmp/reloc-repo; \
    /tmp/relocated/bin/git init -q .; \
    printf 'moved\n' > file.txt; \
    /tmp/relocated/bin/git add file.txt; \
    /tmp/relocated/bin/git commit -q -m 'commit from a relocated tree'; \
    /tmp/relocated/bin/git log --oneline | grep -Fq 'relocated'; \
    echo "git resolves its exec-path from the binary location: ${found}"

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
    export GIT_EXEC_PATH=/artifact/libexec/git-core; \
    ok=no; \
    for _ in 1 2 3; do \
        rm -rf /tmp/tls-clone; \
        if /artifact/bin/git clone -q --depth 1 \
                https://github.com/git/git /tmp/tls-clone 2>/tmp/tls.err; then \
            ok=yes; break; \
        fi; \
        grep -qiE 'certificate|SSL' /tmp/tls.err && break; \
        sleep 3; \
    done; \
    if [ "${ok}" != yes ]; then echo "HTTPS check failed:"; cat /tmp/tls.err; exit 1; fi; \
    test -e /tmp/tls-clone/.git; \
    echo "git clones over HTTPS using the system trust store"

FROM scratch AS artifact

ARG FILC_VERSION
ARG GIT_VERSION

LABEL org.opencontainers.image.title="git compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked git with Fil-C memory safety, OpenSSL, libcurl, PCRE2 and expat" \
      org.opencontainers.image.version="${GIT_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://git-scm.com/" \
      org.opencontainers.image.licenses="GPL-2.0-only AND LGPL-2.1-or-later AND Apache-2.0 AND Zlib"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/git"]
