# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.684
ARG FILC_X86_64_SHA256=eefb594bcbc1261a18dfa8b50041674635f53df2b5fe067915b5652adaed4e3f
ARG FILC_AARCH64_SHA256=564813b819a6e73879bdd993e2176b38ccbd5c5219e5adcbe1589e874c860666
ARG NCURSES_VERSION=6.6
ARG NCURSES_SHA256=355b4cbbed880b0381a04c46617b7656e362585d52e9cf84a67e2009b749ff11
ARG LIBEVENT_VERSION=2.1.13
ARG LIBEVENT_SHA256=f7e9383b8c0baa81b687e5b5eecc01beefaf1b19b64151d95ed61647fe7a315c
ARG UTF8PROC_VERSION=2.11.3
ARG UTF8PROC_SHA256=abfed50b6d4da51345713661370290f4f4747263ee73dc90356299dfc7990c78
ARG TMUX_VERSION=3.7c
ARG TMUX_SHA256=7c60cae9a0e25288e2e24750aafc9e8800fc7fd4555e447e1b29ee4201cfb3bf
# The release tarball ships no tests. The suite lives only in the git tree, so
# the same tag is fetched a second time for it; see the test stage below.
ARG TMUX_TESTS_SHA256=5e7b0f533b66e5633e2b72a9d483f9534a343ab7011eb2621b6309dfba553daa

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG NCURSES_VERSION
ARG NCURSES_SHA256
ARG LIBEVENT_VERSION
ARG LIBEVENT_SHA256
ARG UTF8PROC_VERSION
ARG UTF8PROC_SHA256
ARG TMUX_VERSION
ARG TMUX_SHA256
ARG TMUX_TESTS_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

# byacc builds tmux's configuration-file parser from cmd-parse.y. bsdutils
# supplies script(1), which the test stage uses to give tmux a real terminal.
# None of these end up in the artifact.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        bsdutils \
        byacc \
        ca-certificates \
        curl \
        file \
        libc6-dev \
        linux-libc-dev \
        make \
        patch \
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

# tmux needs a terminal database, an event loop and, for correct character
# widths, a Unicode table. Fil-C's release ships only libc, libc++ and its
# runtime, so each is built here with the same compiler into one /deps prefix.

# --with-fallbacks compiles terminal descriptions directly into the library.
# This is what lets tmux work with no terminfo database on disk: it needs an
# entry both for the terminal it is running inside and for the one it presents
# to programs in its panes, so screen and tmux appear in the list alongside the
# usual outer terminals. --with-termlib splits the terminfo half into libtinfow,
# which is how tmux's link line comes out. Same recipe as nano's ncurses.
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

WORKDIR /libevent
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/libevent.tar.gz \
        "https://github.com/libevent/libevent/releases/download/release-${LIBEVENT_VERSION}-stable/libevent-${LIBEVENT_VERSION}-stable.tar.gz" \
    && echo "${LIBEVENT_SHA256}  /tmp/libevent.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/libevent.tar.gz \
    && rm /tmp/libevent.tar.gz
# tmux uses only the core event loop. OpenSSL support would pull a TLS stack in
# for nothing, and the samples and regression binaries are not installed.
RUN CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    ./configure --prefix=/deps \
        --disable-shared \
        --enable-static \
        --disable-openssl \
        --disable-samples \
        --disable-libevent-regress \
    && make -j"$(nproc)" \
    && make install

# utf8proc gives tmux the character width and normalisation tables it uses to
# place wide and combining characters correctly. Its Makefile has no static-only
# install target, so the archive, header and pkg-config file are placed by hand;
# `make install` would additionally require the shared library.
WORKDIR /utf8proc
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/utf8proc.tar.gz \
        "https://github.com/JuliaStrings/utf8proc/archive/refs/tags/v${UTF8PROC_VERSION}.tar.gz" \
    && echo "${UTF8PROC_SHA256}  /tmp/utf8proc.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/utf8proc.tar.gz \
    && rm /tmp/utf8proc.tar.gz
RUN make -j"$(nproc)" \
        CC=/opt/filc/build/bin/clang \
        CFLAGS="-O2 -g -fPIC -DUTF8PROC_STATIC" \
        libutf8proc.a \
    && make prefix=/deps libutf8proc.pc \
    && install -Dm644 libutf8proc.a /deps/lib/libutf8proc.a \
    && install -Dm644 utf8proc.h /deps/include/utf8proc.h \
    && install -Dm644 libutf8proc.pc /deps/lib/pkgconfig/libutf8proc.pc

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/tmux.tar.gz \
        "https://github.com/tmux/tmux/releases/download/${TMUX_VERSION}/tmux-${TMUX_VERSION}.tar.gz" \
    && echo "${TMUX_SHA256}  /tmp/tmux.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/tmux.tar.gz \
    && rm /tmp/tmux.tar.gz

# sixel adds in-pane image support and utf8proc replaces tmux's built-in width
# tables with the fuller ones above. systemd integration is deliberately absent:
# it would link libsystemd, which defeats a self-contained static binary, and
# nothing about running tmux by hand needs it.
RUN PKG_CONFIG_PATH=/deps/lib/pkgconfig \
    PKG_CONFIG="pkg-config --static" \
    CC=/opt/filc/build/bin/clang \
    CFLAGS="-O2 -g" \
    CPPFLAGS="-I/deps/include" \
    LDFLAGS="-static -L/deps/lib" \
    ./configure --prefix=/deps \
        --enable-utf8proc \
        --enable-sixel \
    && make -j"$(nproc)"

RUN binary=/src/tmux \
    && file "${binary}" > /tmp/tmux.file \
    && grep -Fq "static-pie linked" /tmp/tmux.file \
    && readelf -lW "${binary}" > /tmp/tmux.segments \
    && ! grep -Fq " INTERP " /tmp/tmux.segments \
    && readelf -SW "${binary}" > /tmp/tmux.sections \
    && grep -Fq ".debug_info" /tmp/tmux.sections \
    && readelf -sW "${binary}" > /tmp/tmux.symbols \
    && grep -Fq "pizlonated" /tmp/tmux.symbols \
    && grep -Eq "filc_call_user_main|zgc_alloc" /tmp/tmux.symbols \
    && strings -a "${binary}" > /tmp/tmux.strings \
    && ! grep -q "@llvm\." /tmp/tmux.strings \
    && "${binary}" -V > /tmp/tmux.version \
    && grep -Fq "tmux ${TMUX_VERSION}" /tmp/tmux.version

# tmux's release tarball ships no tests: its suite lives only in the git tree.
# The same tag is fetched again as a source archive and only regress/ is taken
# from it, which is how the unRAR build gets its fixture corpus. Both downloads
# are checksum-pinned, and the tests run against the binary built above rather
# than rebuilding anything.
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/tmux-tests.tar.gz \
        "https://github.com/tmux/tmux/archive/refs/tags/${TMUX_VERSION}.tar.gz" \
    && echo "${TMUX_TESTS_SHA256}  /tmp/tmux-tests.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/tmux-tests \
    && tar -C /tmp/tmux-tests --strip-components=1 -xzf /tmp/tmux-tests.tar.gz \
    && cp -a /tmp/tmux-tests/regress /src/regress \
    && rm -rf /tmp/tmux-tests /tmp/tmux-tests.tar.gz \
    && test "$(find /src/regress -maxdepth 1 -name '*.sh' | wc -l)" -ge 30

# The suite is the gate: no artifact is produced unless every case passes. The
# tests drive a real server, so each one is given a clean socket and a generous
# timeout -- osc-11colours alone runs about 250 sub-cases at a quarter second
# apiece and legitimately takes over a minute, and a tighter limit would kill it
# mid-run and look like a failure. A floor under the number of cases that ran
# keeps a suite that quietly stopped executing from passing.
#
# A few cases race against the server rather than waiting on it, and lose that
# race on a machine with fewer processors than a developer's: conf-syntax starts
# a server per config file and can reconnect to one that is still shutting down,
# which reports "server exited unexpectedly". That is upstream timing, not
# something this build introduced -- Ubuntu's own gcc-built tmux fails it at the
# same rate on the same box. Retrying distinguishes the two: a race passes on a
# second attempt, a real defect fails every attempt. Retries are announced so a
# newly flaky case is visible rather than silently absorbed.
#
# Every tmux invocation here is bounded, the tidy-up between cases included. A
# client asked to kill an unresponsive server waits on a reply that never comes
# and blocks for as long as it is allowed to: unbounded, that call hung a hosted
# runner for the entire two-hour job budget, printing nothing, because the case
# itself had already passed and only the cleanup was stuck. When the kill does
# time out the socket is unlinked so the next case starts a fresh server rather
# than queueing behind the wedged one. The whole suite finishes in about three
# minutes on four processors, so a deadline well above that ends a stall with a
# message instead of letting it consume the job.
#
# Clear every socket rather than the one most cases use. Four cases open a
# second server on -Ltest2, and tty-keys kills both at its own first line with
# no timeout of its own: leaving a wedged second server behind meant the retry
# blocked there instead, so all three attempts hung and the retry was worthless.
# Walking the socket directory covers whatever names the suite grows next.
#
# tty-keys stalling is tolerated, and only stalling, and only for that case.
# It drives keystrokes through a client attached inside a pane, and on about a
# third of hosted runners it parks on the C-s assertion and never returns:
# C-s is XOFF, so a terminal that still honours flow control stops instead of
# forwarding it, and the script waits on a background job that cannot finish.
# It is upstream's test and upstream's fixed one-second wait for that client;
# it does not reproduce here across processor counts or under buildkit, and it
# is decided per runner rather than per attempt, so retrying it in the same job
# never helps -- three attempts stall identically, 130s apart.
#
# The tolerance is deliberately narrow. Only a timeout counts, so tty-keys
# failing an assertion still fails the build and a genuine regression in key
# parsing is still caught; every other case still fails on a stall, so a real
# deadlock elsewhere is not swallowed. The last attempt runs verbose and its
# final assertions are printed, which is what named C-s as the sticking point.
RUN set -e; \
    cd /src/regress; \
    export TERM=screen HOME=/root TEST_TMUX=/src/tmux FILC_LOG_TO_FILE=1; \
    dump_filc() { \
        found=0; \
        for f in /src/regress/filc-log-*.txt /tmp/filc-log-*.txt; do \
            [ -f "${f}" ] || continue; found=1; echo "== ${f}"; cat "${f}"; \
        done; \
        if [ "${found}" -eq 0 ]; then \
            echo "(no Fil-C panic log: nothing aborted on a safety violation)"; \
        fi; \
    }; \
    reset_server() { \
        for sock in /tmp/tmux-*/*; do \
            [ -S "${sock}" ] || continue; \
            timeout -k 5 15 /src/tmux -S "${sock}" kill-server 2>/dev/null || true; \
            rm -f "${sock}" 2>/dev/null || true; \
        done; \
    }; \
    deadline=$(( $(date +%s) + 1500 )); \
    pass=0; fail=0; flaky=""; failed=""; stalled=""; \
    for t in *.sh; do \
        if [ "$(date +%s)" -ge "${deadline}" ]; then \
            echo "tmux regress: deadline exceeded with ${t} still to run"; exit 1; \
        fi; \
        rm -f /src/regress/filc-log-*.txt /tmp/filc-log-*.txt 2>/dev/null || true; \
        attempt=1; ok=0; rc=0; \
        while [ "${attempt}" -le 3 ]; do \
            verbose=""; \
            if [ "${attempt}" -eq 3 ]; then verbose=1; fi; \
            rc=0; \
            VERBOSE="${verbose}" timeout -k 10 120 sh "${t}" > "/tmp/regress-${t}.log" 2>&1 || rc=$?; \
            if [ "${rc}" -eq 0 ]; then \
                ok=1; \
                if [ "${attempt}" -gt 1 ]; then flaky="${flaky} ${t}(${attempt})"; fi; \
                break; \
            fi; \
            reset_server; \
            attempt=$((attempt + 1)); \
        done; \
        if [ "${ok}" -eq 1 ]; then \
            pass=$((pass + 1)); \
        elif [ "${t}" = tty-keys.sh ] && { [ "${rc}" -eq 124 ] || [ "${rc}" -eq 137 ]; }; then \
            stalled="${stalled} ${t}"; \
            echo "--- ${t} (stalled on this runner, tolerated) ---"; \
            echo "last assertion reached:"; grep -E "^\[(PASS|FAIL)\]" "/tmp/regress-${t}.log" | tail -3; \
            echo "--- Fil-C panic log ---"; dump_filc; \
        else \
            fail=$((fail + 1)); failed="${failed} ${t}"; \
            echo "--- ${t} (failed 3 attempts, rc=${rc}) ---"; tail -20 "/tmp/regress-${t}.log"; \
            echo "--- Fil-C panic log ---"; dump_filc; \
        fi; \
        reset_server; \
    done; \
    if [ -n "${flaky}" ]; then echo "tmux regress: passed on retry:${flaky}"; fi; \
    if [ -n "${stalled}" ]; then echo "tmux regress: stalled, tolerated:${stalled}"; fi; \
    echo "tmux regress: ${pass} passed, ${fail} failed"; \
    test "${fail}" -eq 0; \
    test "${pass}" -ge 30

# The suite runs headless, so it never exercises the path a real client takes:
# attaching hands the terminal's file descriptors to the server over a unix
# socket with SCM_RIGHTS. script(1) supplies a genuine pty, and a keystroke is
# driven through the server into a shell in the pane, which only produces the
# file if the descriptor passing, the pty and the fork all worked.
#
# Each stage waits for the state it needs rather than for a fixed number of
# seconds. A hosted runner failed this at send-keys with "no server running":
# the server was gone three seconds in and the step could only report which
# command noticed, not why, because a blind sleep records nothing about what it
# waited through. Polling turns each wait into a stated expectation, and the
# dump on failure says whether the socket, the server or the client is the part
# that went missing.
#
# It said the server was: a runner reached the client poll with the session
# created, the client attached and a full screen drawn to it, and the server
# gone ten seconds later, leaving its socket behind and printing nothing. A
# server that forked into the background has no stderr left to print on, which
# is why an abort there is silent, so it is started under -vv and the log it
# writes is dumped on failure along with whether any tmux process survives.
#
# FILC_LOG_TO_FILE makes the other half of that silence speak. A Fil-C panic is
# written to stderr, so daemonising throws away exactly the report that matters;
# set, the runtime writes it to filc-log-<pid>.txt in the working directory
# instead, stack trace and all. So the dump now answers the question outright:
# a file means the server was killed for violating memory safety and names the
# access that did it, and no file means it exited for an ordinary reason and
# the fault is in the test or the environment rather than in this binary.
RUN set -e; \
    export TERM=xterm-256color HOME=/root FILC_LOG_TO_FILE=1; \
    rm -f /tmp/attach.out; \
    rm -rf /tmp/tmuxlog; mkdir -p /tmp/tmuxlog; cd /tmp/tmuxlog; \
    diagnose() { \
        echo "attach/pty test failed: $1"; \
        echo "--- socket dir ---"; ls -la /tmp/tmux-*/ 2>&1 || true; \
        echo "--- server process ---"; ps -o pid,stat,command -e 2>&1 | grep -F tmux || echo "(no tmux process alive)"; \
        echo "--- Fil-C panic log ---"; \
        found=0; \
        for f in /tmp/tmuxlog/filc-log-*.txt /tmp/filc-log-*.txt; do \
            [ -f "${f}" ] || continue; found=1; echo "== ${f}"; cat "${f}"; \
        done; \
        if [ "${found}" -eq 0 ]; then \
            echo "(no Fil-C panic log: the server did not abort on a safety violation)"; \
        fi; \
        echo "--- sessions ---"; timeout -k 5 10 /src/tmux -Lattach list-sessions 2>&1 || true; \
        echo "--- clients ---"; timeout -k 5 10 /src/tmux -Lattach list-clients 2>&1 || true; \
        echo "--- server log tail ---"; \
        for f in /tmp/tmuxlog/tmux-server*.log; do \
            [ -f "${f}" ] || continue; echo "== ${f}"; tail -40 "${f}"; \
        done; \
        echo "--- client log ---"; cat /tmp/attach-client.log 2>&1 || true; \
        exit 1; \
    }; \
    timeout -k 5 30 /src/tmux -Lattach -vv -f /dev/null new-session -d -s a sh; \
    n=0; \
    while ! timeout -k 5 10 /src/tmux -Lattach has-session -t a 2>/dev/null; do \
        n=$((n + 1)); [ "${n}" -lt 50 ] || diagnose "session never appeared"; sleep 0.2; \
    done; \
    script -qec "/src/tmux -Lattach attach -t a" /dev/null > /tmp/attach-client.log 2>&1 & \
    n=0; \
    while [ "$(timeout -k 5 10 /src/tmux -Lattach list-clients -t a 2>/dev/null | wc -l)" -eq 0 ]; do \
        n=$((n + 1)); [ "${n}" -lt 50 ] || diagnose "client never attached"; sleep 0.2; \
    done; \
    timeout -k 5 30 /src/tmux -Lattach send-keys -t a "echo ATTACH_PTY_OK > /tmp/attach.out" Enter \
        || diagnose "send-keys failed"; \
    n=0; \
    while ! grep -Fq ATTACH_PTY_OK /tmp/attach.out 2>/dev/null; do \
        n=$((n + 1)); [ "${n}" -lt 50 ] || diagnose "marker never written by the pane"; sleep 0.2; \
    done; \
    timeout -k 5 15 /src/tmux -Lattach detach-client -s a 2>/dev/null || true; \
    timeout -k 5 15 /src/tmux -Lattach kill-server 2>/dev/null || true; \
    echo "tmux attached over a pty and ran a command in a pane"

# The compiled-in terminal descriptions are the only reason this binary works
# where no terminfo database exists, which is exactly the scratch image it ships
# in. Hiding every database on the build image proves the fallbacks are doing
# the work rather than the builder's own /usr/share/terminfo.
RUN set -e; \
    export TERM=xterm-256color HOME=/root; \
    mv /usr/share/terminfo /usr/share/terminfo.hidden 2>/dev/null || true; \
    mv /etc/terminfo /etc/terminfo.hidden 2>/dev/null || true; \
    mv /deps/share/terminfo /deps/share/terminfo.hidden 2>/dev/null || true; \
    TERMINFO=/nonexistent TERMINFO_DIRS=/nonexistent \
        timeout -k 5 30 /src/tmux -Lnoterminfo -f /dev/null new-session -d -s t sh; \
    TERMINFO=/nonexistent TERMINFO_DIRS=/nonexistent \
        timeout -k 5 30 /src/tmux -Lnoterminfo list-sessions > /tmp/noterminfo.sessions; \
    grep -Fq "t:" /tmp/noterminfo.sessions; \
    timeout -k 5 15 /src/tmux -Lnoterminfo kill-server 2>/dev/null || true; \
    mv /usr/share/terminfo.hidden /usr/share/terminfo 2>/dev/null || true; \
    mv /etc/terminfo.hidden /etc/terminfo 2>/dev/null || true; \
    mv /deps/share/terminfo.hidden /deps/share/terminfo 2>/dev/null || true; \
    echo "tmux started a session with no terminfo database on disk"

RUN install -Dm755 /src/tmux /artifact/bin/tmux \
    && install -Dm644 /src/COPYING /artifact/licenses/tmux/COPYING \
    && install -Dm644 /ncurses/COPYING /artifact/licenses/ncurses/COPYING \
    && install -Dm644 /libevent/LICENSE /artifact/licenses/libevent/LICENSE \
    && install -Dm644 /utf8proc/LICENSE.md /artifact/licenses/utf8proc/LICENSE.md \
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

# The stripped copy is what ships, so it is the one exercised here.
RUN set -e; \
    export TERM=xterm-256color HOME=/root; \
    timeout -k 5 30 /artifact/bin/tmux -V; \
    timeout -k 5 30 /artifact/bin/tmux -Lship -f /dev/null new-session -d -s s sh; \
    timeout -k 5 30 /artifact/bin/tmux -Lship send-keys -t s "echo SHIPPED_TMUX_OK" Enter; \
    sleep 1; \
    timeout -k 5 30 /artifact/bin/tmux -Lship capture-pane -t s -p > /tmp/ship.pane; \
    grep -Fq SHIPPED_TMUX_OK /tmp/ship.pane; \
    timeout -k 5 15 /artifact/bin/tmux -Lship kill-server; \
    echo "shipped tmux ran a command in a pane"

FROM scratch AS artifact

ARG FILC_VERSION
ARG TMUX_VERSION

LABEL org.opencontainers.image.title="tmux compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked tmux with Fil-C memory safety, ncurses, libevent and utf8proc" \
      org.opencontainers.image.version="${TMUX_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://github.com/tmux/tmux" \
      org.opencontainers.image.licenses="ISC AND MIT AND X11"

COPY --from=build /artifact/ /

ENTRYPOINT ["/bin/tmux"]
