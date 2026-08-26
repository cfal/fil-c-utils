# syntax=docker/dockerfile:1

ARG FILC_VERSION=0.684
ARG FILC_X86_64_SHA256=eefb594bcbc1261a18dfa8b50041674635f53df2b5fe067915b5652adaed4e3f
ARG FILC_AARCH64_SHA256=564813b819a6e73879bdd993e2176b38ccbd5c5219e5adcbe1589e874c860666
ARG ZLIB_VERSION=1.3.2
ARG ZLIB_SHA256=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
ARG OPENSSL_VERSION=4.0.1
ARG OPENSSL_SHA256=2db3f3a0d6ea4b59e1f094ace2c8cd536dffb87cdc39084c5afa1e6f7f37dd09
ARG OPENSSH_VERSION=10.5p1
ARG OPENSSH_SHA256=d44d28a839ea9daf969cc69150fde59910b2b39361dad81a3bd6cbd19218db11

FROM ubuntu:24.04 AS build

ARG TARGETARCH
ARG FILC_VERSION
ARG FILC_X86_64_SHA256
ARG FILC_AARCH64_SHA256
ARG ZLIB_VERSION
ARG ZLIB_SHA256
ARG OPENSSL_VERSION
ARG OPENSSL_SHA256
ARG OPENSSH_VERSION
ARG OPENSSH_SHA256

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Upstream release hosts are occasionally slow or briefly unreachable, and a
# single stalled fetch otherwise fails a whole build: curl's default is one
# attempt with a five minute connect timeout. These options give up on a
# transfer that stalls below 1 KB/s and retry it instead of waiting it out.
# Integrity still rests on the SHA-256 check, not on the transfer succeeding.
ENV FETCH_RETRY="--retry 5 --retry-delay 2 --retry-all-errors \
    --connect-timeout 20 --speed-limit 1024 --speed-time 30"

# tmux is here for one regress test: ssh-tty drives a remote pseudo-terminal
# through tmux, and without it that test silently self-skips. A PTY is core
# business for an SSH server, so the test is wanted for real.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        binutils \
        ca-certificates \
        curl \
        file \
        libc6-dev \
        linux-libc-dev \
        locales \
        make \
        patch \
        patchelf \
        perl \
        pkg-config \
        tmux \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# The utf8 unit test wants an en_US.UTF-8 locale; configure detects its
# absence and silently drops that test from the suite. Generating it keeps
# the whole unit target in the gate, and the configure result is asserted
# below rather than taken on faith.
RUN sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen \
    && locale-gen

# Fil-C 0.684's generated setup.sh checks x86_64's multiarch path on every
# architecture. Its fallback leaves os-include/asm dangling on aarch64, hiding
# the seccomp and tun UAPI behind a missing asm/types.h. Use the architecture-
# specific path, as Fil-C's own build_os_include.sh does.
WORKDIR /opt/filc
RUN case "${TARGETARCH}" in \
        amd64) filc_arch=x86_64; filc_sha256="${FILC_X86_64_SHA256}"; \
            seccomp_audit_arch=AUDIT_ARCH_X86_64 ;; \
        arm64) filc_arch=aarch64; filc_sha256="${FILC_AARCH64_SHA256}"; \
            seccomp_audit_arch=AUDIT_ARCH_AARCH64 ;; \
        *) echo "unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL ${FETCH_RETRY} -o /tmp/filc.tar.xz \
        "https://github.com/pizlonator/fil-c/releases/download/v${FILC_VERSION}/filc-${FILC_VERSION}-linux-${filc_arch}.tar.xz" \
    && echo "${filc_sha256}  /tmp/filc.tar.xz" | sha256sum -c - \
    && tar --strip-components=1 -xJf /tmp/filc.tar.xz \
    && ./setup.sh \
    && ln -sfn "/usr/include/${filc_arch}-linux-gnu/asm" pizfix/os-include/asm \
    && ls pizfix/os-include | sort > /tmp/os-include.actual \
    && printf '%s\n' asm asm-generic linux > /tmp/os-include.expected \
    && diff -u /tmp/os-include.expected /tmp/os-include.actual \
    && printf '%s\n' \
        '#include <sys/types.h>' \
        '#include <linux/prctl.h>' \
        '#include <linux/seccomp.h>' \
        '#include <linux/filter.h>' \
        '#include <linux/audit.h>' \
        '#include <linux/if_tun.h>' \
        'int no_new_privs = PR_SET_NO_NEW_PRIVS;' \
        'int mode_filter = SECCOMP_MODE_FILTER;' \
        "unsigned audit_arch = ${seccomp_audit_arch};" \
        > /tmp/uapi-probe.c \
    && ./build/bin/clang -fsyntax-only /tmp/uapi-probe.c \
    && rm /tmp/uapi-probe.c /tmp/filc.tar.xz

# OpenSSH needs zlib for its packet compression and OpenSSL beneath the
# transport. Fil-C's release ships only libc, libc++ and its runtime, so each
# of these is built here with the same compiler into a single /deps prefix.
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

# no-asm is required: Fil-C cannot compile OpenSSL's hand-written assembly, so
# every primitive uses the portable C path. SSH spends most of its time in
# exactly those primitives, so that cost shows up on every packet; it is the
# main price of this build.
#
# --libdir=lib matters: OpenSSL defaults to lib64 on x86-64, while openssh
# derives -L<prefix>/lib from --with-ssl-dir, and the mismatch fails the
# static link.
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
        no-shared no-module no-asm no-tests no-docs no-engine \
        --prefix=/deps --openssldir=/deps/ssl --libdir=lib \
        -DOPENSSL_NO_SECURE_MEMORY -O2 -g \
    && make -j"$(nproc)" \
    && make install_sw \
    && make install_ssldirs

WORKDIR /src
RUN curl -fsSL ${FETCH_RETRY} -o /tmp/openssh.tar.gz \
        "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-${OPENSSH_VERSION}.tar.gz" \
    && echo "${OPENSSH_SHA256}  /tmp/openssh.tar.gz" | sha256sum -c - \
    && tar --strip-components=1 -xzf /tmp/openssh.tar.gz \
    && rm /tmp/openssh.tar.gz

# Four patches adapt pristine OpenSSH 10.5p1 to Fil-C 0.684 and are gated on
# __FILC__ so an unpatched build keeps upstream behaviour. The first carries
# over the Fil-C 0.684 OpenSSH port's seccomp changes and teaches the sandbox
# about the runtime's threads: it locks them before the filter is installed,
# allows the sched_yield and MAP_NORESERVE mmap they issue in the sandboxed
# child, and makes violations kill the process rather than one thread of it.
# This variant gates those changes on __FILC__ so non-Fil-C builds retain
# upstream behavior.
# The second routes setproctitle through the runtime, because under Fil-C the
# argv area belongs to it and the classic copy-over-argv path is unavailable.
# The third aligns one generated libcrux Result payload to work around an
# aarch64 aggregate-lowering bug fixed after 0.684 in Fil-C commit e0ded6df4296.
# The fourth makes Fil-C/AArch64 select sntrup cryptoint's portable C fallbacks,
# because 0.684 cannot lower the generated AArch64 inline assembly.
COPY patches/0001-prepare-seccomp-sandbox-for-fil-c.patch /tmp/openssh-filc-sandbox.patch
COPY patches/0002-report-process-title-through-fil-c.patch /tmp/openssh-filc-proctitle.patch
COPY patches/0003-align-libcrux-result-for-fil-c.patch /tmp/openssh-filc-libcrux.patch
COPY patches/0004-use-portable-sntrup-cryptoint-on-fil-c-aarch64.patch /tmp/openssh-filc-sntrup.patch
RUN patch --batch --forward -p1 < /tmp/openssh-filc-sandbox.patch \
    && patch --batch --forward -p1 < /tmp/openssh-filc-proctitle.patch \
    && patch --batch --forward -p1 < /tmp/openssh-filc-libcrux.patch \
    && patch --batch --forward -p1 < /tmp/openssh-filc-sntrup.patch \
    && test "$(grep -Fxc '#elif defined(__GNUC__) && defined(__aarch64__) && !defined(__FILC__)' sntrup761.c)" -eq 78 \
    && ! grep -Fxq '#elif defined(__GNUC__) && defined(__aarch64__)' sntrup761.c \
    && test "$(grep -Fxc '#if defined(__GNUC__) && defined(__x86_64__)' sntrup761.c)" -eq 78

# --prefix=/ with explicit bin, libexec and configuration directories puts the
# user-facing commands in /bin and the privilege-separation helpers
# (sshd-session, sshd-auth, sftp-server,
# ssh-keysign, ssh-pkcs11-helper, ssh-sk-helper) in /libexec, which is also
# where sshd looks for them: the paths are compiled in, so they cannot move
# afterwards. sshd therefore only runs from a tree installed at /, unlike
# the other utilities in this repository, which run from wherever they are
# unpacked.
#
# --with-sandbox=seccomp_filter selects the sandbox the patches above adapt;
# it is the Linux default, and naming it keeps a future configure change from
# silently dropping it.
#
# --with-privsep-user=sshd names a dedicated, locked account for the untrusted
# preauthentication process. Upstream requires that this account not be shared
# with another service; the builder creates it below, while deployment hosts
# must provide it themselves because the artifact carries no account database.
#
# --disable-security-key and --disable-pkcs11 turn off authentication paths
# that load third-party FIDO or token provider modules. A static Fil-C binary
# cannot load those host shared objects, and this build does not add the
# separate dependencies needed for built-in FIDO support. Disabling the paths
# makes that limitation explicit instead of leaving runtime-only failures.
#
# PAM, libedit, Kerberos and audit are all opt-in upstream and stay off, so
# nothing outside zlib and OpenSSL reaches the link.
#
# OpenSSH's hardening probe enables -ftrapv, but Fil-C 0.684 accepts the probe
# while leaving its llvm.ubsantrap overflow paths as unsupported-intrinsic
# panics. Suppress only that false-positive probe and use -fwrapv so signed
# overflow is defined rather than optimizer-dependent. This gives up upstream's
# immediate overflow abort; every other hardening flag is retained and asserted.
RUN CFLAGS="-O2 -g -fwrapv" LDFLAGS="-static -L/deps/lib" \
        ossh_cv_cflag__ftrapv=no ./configure \
        --prefix=/ --bindir=/bin --sbindir=/bin \
        --libexecdir=/libexec --sysconfdir=/etc/ssh \
        --with-ssl-dir=/deps --with-zlib=/deps \
        --with-sandbox=seccomp_filter \
        --with-privsep-user=sshd \
        --disable-security-key --disable-pkcs11 \
    && make -j"$(nproc)"

# Fail at the affected operation instead of letting a missing fixture host key
# surface later as an unrelated connection or multiplexing timeout.
RUN ./ssh-keygen -q -t mldsa44-ed25519 -N '' -f /tmp/mldsa44-key \
    && test -s /tmp/mldsa44-key \
    && test -s /tmp/mldsa44-key.pub \
    && rm -f /tmp/mldsa44-key /tmp/mldsa44-key.pub

# The configure results that carry the security story are asserted here
# rather than taken on faith, because they are invisible in the binaries:
#   - the seccomp sandbox the patches adapt is the one compiled in;
#   - the dlopen-dependent features are really off, so no code path that
#     would try to load a host shared object exists;
#   - close_range is absent: Fil-C's musl does not implement it and would
#     panic on it, so OpenSSH must take its /proc and brute-force closefrom
#     fallbacks instead;
#   - the utf8 unit test stays in the suite, which the locale generation
#     above is what makes true.
RUN grep -E '^(CFLAGS|CFLAGS_NOPIE|LDFLAGS|LDFLAGS_NOPIE)=' Makefile \
        > /tmp/hardening.flags \
    && cat /tmp/hardening.flags \
    && ! grep -Fq -- '-ftrapv' Makefile \
    && grep -Fq -- '-fwrapv' /tmp/hardening.flags \
    && for flag in -D_FORTIFY_SOURCE=2 -fstack-protector-strong \
            -fzero-call-used-regs=used -ftrivial-auto-var-init=zero \
            -fno-builtin-memset -fPIE; do \
        grep -Fq -- "${flag}" /tmp/hardening.flags || exit 1; \
    done \
    && for flag in -Wl,-z,relro -Wl,-z,now -Wl,-z,noexecstack -pie; do \
        grep -Fq -- "${flag}" /tmp/hardening.flags || exit 1; \
    done \
    && grep -Fq '#define SANDBOX_SECCOMP_FILTER 1' config.h \
    && grep -Fq '#define SSH_TUN_LINUX 1' config.h \
    && grep -Fq '#define SSH_PRIVSEP_USER "sshd"' config.h \
    && ! grep -Eq '^#define (ENABLE_PKCS11|ENABLE_SK|ENABLE_SK_INTERNAL|HAVE_CLOSE_RANGE) ' config.h \
    && grep -Fq 'TEST_SSH_UTF8="yes"' Makefile \
    && case "${TARGETARCH}" in \
        amd64) grep -Fq '#define SECCOMP_AUDIT_ARCH AUDIT_ARCH_X86_64' config.h ;; \
        arm64) grep -Fq '#define SECCOMP_AUDIT_ARCH AUDIT_ARCH_AARCH64' config.h ;; \
        *) exit 1 ;; \
    esac

# The patch effects are asserted here because they are otherwise invisible:
# each object must reference the Fil-C runtime entry point its patch calls, and
# the filter's fail action must remain process-wide. Without these checks a
# partial patch rebase could produce a build that passes every other gate.
RUN readelf -sW sandbox-seccomp-filter.o > /tmp/sandbox.symbols \
    && grep -Fq 'zlock_runtime_threads' /tmp/sandbox.symbols \
    && grep -Fq '#define SECCOMP_FILTER_FAIL SECCOMP_RET_KILL_PROCESS' \
        sandbox-seccomp-filter.c \
    && readelf -sW openbsd-compat/setproctitle.o > /tmp/proctitle.symbols \
    && grep -Fq 'zsetproctitle' /tmp/proctitle.symbols \
    && ! grep -Eq 'argv_(start|env_len)' /tmp/proctitle.symbols

# Every executable the build produced is checked the same way the artifact
# will be: static PIE, no interpreter, DWARF still present at this stage,
# Fil-C symbols, no misaligned pointer fields, and none of the markers of code
# Fil-C cannot run.
COPY --chmod=0755 check-alignment.pl /usr/local/bin/check-filc-alignment
RUN set -e; \
    binaries=(ssh sshd sshd-session sshd-auth scp sftp ssh-add ssh-agent \
            ssh-keygen ssh-keyscan ssh-keysign ssh-pkcs11-helper ssh-sk-helper \
            sftp-server); \
    for binary in "${binaries[@]}"; do \
        test -f "${binary}"; \
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
        ! grep -Fq "Unhandled intrinsic" "/tmp/${binary}.strings"; \
        ! grep -Fq "cannot handle inline asm" "/tmp/${binary}.strings"; \
    done; \
    check-filc-alignment "${binaries[@]}" \
    && ./ssh -V 2> /tmp/ssh.version \
    && grep -Fq "OpenSSH_${OPENSSH_VERSION}" /tmp/ssh.version \
    && grep -Fq "OpenSSL ${OPENSSL_VERSION}" /tmp/ssh.version

# sshd refuses to start without both its dedicated privilege-separation account
# and chroot directory. The account is locked, owns no files, and cannot log in;
# /var/empty stays root-owned and unwritable to anyone else.
RUN groupadd --system sshd \
    && useradd --system --gid sshd --home-dir /var/empty \
        --shell /usr/sbin/nologin --comment 'sshd privsep' sshd \
    && passwd --lock sshd \
    && install -d -o root -g root -m 0755 /var/empty \
    && test "$(passwd --status sshd | awk '{print $2}')" = L \
    && test "$(stat -c '%u:%g:%a' /var/empty)" = '0:0:755'

# The compatibility regressions directly exercise OpenSSH's portability
# fallbacks, including closefrom(), whose close_range path must stay disabled
# under Fil-C because that runtime entry point is unsupported.
RUN make compat-tests \
    && for test_binary in closefromtest opensslvertest snprintftest strduptest \
            strtonumtest utimensattest; do \
        test -x "openbsd-compat/regress/${test_binary}"; \
    done

# OpenSSH 10.5p1's ssh-tty.sh checks for a tab with a `*\t*` POSIX case
# pattern. Ubuntu's /bin/sh parses that as a literal `t`, so root's normal
# HOME makes the test self-skip even though it contains no whitespace. Keep
# the workaround local to this test. Docker builds also leave SHELL unset, so
# name the shell this test drives through tmux; every other regression retains
# the builder's normal environment.
RUN set -euo pipefail; \
    install -d -m 0700 /home/r; \
    safe_path=/src:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; \
    if ! HOME=/home/r PATH="${safe_path}" SHELL=/bin/bash timeout -k 60 900 \
            make t-exec LTESTS=ssh-tty SUDO= 2>&1 | tee /tmp/ssh-tty.log; then \
        for log in regress/failed-ssh.log regress/failed-sshd.log \
                regress/ssh.log regress/sshd.log; do \
            test -r "${log}" || continue; \
            printf 'diagnostic: %s\n' "${log}"; \
            tail -n 200 "${log}"; \
        done; \
        exit 1; \
    fi; \
    test "$(grep -c '^run test ' /tmp/ssh-tty.log)" -eq 1; \
    test "$(grep -c '^skip test ' /tmp/ssh-tty.log || true)" -eq 0; \
    ! grep -Eq '^(Skipped|SKIPPED):' /tmp/ssh-tty.log; \
    for _ in $(seq 1 20); do \
        test -e regress/ctl-sock || break; \
        sleep 1; \
    done; \
    test ! -e regress/ctl-sock

# OpenSSH's own test suite is the gate: no artifact is produced unless it
# passes. `make tests` is file-tests, t-exec (the functional battery that
# starts a real sshd per test and therefore drives key exchange, privilege
# separation and the seccomp sandbox this build patches), interop-tests and
# extra-tests, and unit.
#
# SUDO is passed empty on purpose: the harness substitutes it for privilege
# escalation it does not need when the build runs as root, and pointing it at
# a nonexistent sudo binary would break those substitution sites.
#
# SKIP_LTESTS names ten of the ninety-seven functional tests, and the counts
# below fail the build if the split is ever different, so an upgrade cannot
# silently add unrun tests. Each skip either cannot run in this build or is
# isolated so its prerequisites cannot change other cases:
#   sshfp-connect            needs an external DNSSEC fixture domain
#   agent-getpeereid         needs a second local user reached through sudo
#   agent-ptrace             skips itself when run as root
#   hostbased                rewrites the system ssh_config; run separately
#                            below after the stripped helper is installed
#   password                 needs a temporary password; run separately below
#   kbdint                   has no backend without PAM or BSD authentication
#   ssh-tty                  has an upstream shell-portability bug; run above
#                            with its workaround scoped to that test
#   agent-pkcs11-restrict,
#   agent-pkcs11-cert,
#   ssh-pkcs11               test the PKCS#11 provider feature this build
#                            disables, because a static binary cannot dlopen
#                            a token library
# The interop tests (PuTTY, Conch, Dropbear) self-skip when those foreign
# implementations are absent, which is the suite's own intended behaviour and
# is left visible in the log.
#
# The seven optional interoperability scripts and the extra PKCS#11 script are
# still dispatched. They self-skip because their external implementations or
# provider are absent; the exact script-and-reason allowlist below makes any
# other self-skip fail the build.
RUN set -euo pipefail; \
    timeout -k 60 5400 make tests SUDO= SKIP_LTESTS='sshfp-connect agent-getpeereid agent-ptrace hostbased password kbdint agent-pkcs11-restrict agent-pkcs11-cert ssh-pkcs11 ssh-tty' 2>&1 | tee /tmp/tests.log; \
    run_count="$(grep -c '^run test ' /tmp/tests.log)"; \
    skip_count="$(grep -c '^skip test ' /tmp/tests.log)"; \
    functional_count="$((run_count + skip_count - 8))"; \
    echo "make tests: ${run_count} dispatched, ${skip_count} skipped; ${functional_count} functional tests registered"; \
    test "${run_count}" -eq 95; \
    test "${skip_count}" -eq 10; \
    test "${functional_count}" -eq 97; \
    awk '/^run test / { current=$3 } /^(Skipped|SKIPPED):/ { print current ": " $0 }' \
        /tmp/tests.log | sort > /tmp/self-skips.actual; \
    printf '%s\n' \
        'agent-pkcs11.sh: SKIPPED: No PKCS#11 library found' \
        'conch-ciphers.sh: SKIPPED: conch interop tests not enabled' \
        'dropbear-ciphers.sh: SKIPPED: dropbear interop tests not enabled' \
        'dropbear-kex.sh: SKIPPED: dropbear interop tests not enabled' \
        'dropbear-server.sh: SKIPPED: dropbear interop tests not enabled' \
        'putty-ciphers.sh: SKIPPED: putty interop tests not enabled' \
        'putty-kex.sh: SKIPPED: putty interop tests not enabled' \
        'putty-transfer.sh: SKIPPED: putty interop tests not enabled' \
        | sort > /tmp/self-skips.expected; \
    diff -u /tmp/self-skips.expected /tmp/self-skips.actual

# Exercise upstream's password regression separately, so its test-only root
# login override and nonempty SUDO placeholder cannot change any other case.
# Ubuntu's chpasswd generates a yescrypt hash explicitly; the cleartext and the
# unlocked root password exist only in this discarded builder layer.
RUN set -euo pipefail; \
    test_password='filc-openssh-password-test'; \
    printf 'root:%s\n' "${test_password}" | chpasswd --crypt-method YESCRYPT; \
    grep -q '^root:\$y\$' /etc/shadow; \
    printf '%s\n' "${test_password}" > regress/password; \
    chmod 0600 regress/password; \
    cleanup_password() { passwd --lock root >/dev/null; rm -f regress/password; }; \
    trap cleanup_password EXIT; \
    timeout -k 60 900 make t-exec LTESTS=password SUDO=env \
        TEST_SSH_SSHD_CONFOPTS='PermitRootLogin yes' 2>&1 | tee /tmp/password.log; \
    test "$(grep -c '^run test ' /tmp/password.log)" -eq 1; \
    test "$(grep -c '^skip test ' /tmp/password.log || true)" -eq 0; \
    ! grep -Eq '^(Skipped|SKIPPED):' /tmp/password.log

# The suite is past, so install for real: the smoke test below needs the
# helpers at the compiled-in /libexec paths, which only a real install gives.
RUN make install STRIP_OPT=

# Stage the artifact from the same tree the tests vetted. sshd needs its
# privilege separation directory at runtime, and the FROM-scratch artifact
# carries no filesystem beyond what is staged here, so /var/empty travels
# with it.
RUN make install DESTDIR=/artifact STRIP_OPT= \
    && install -d -o root -g root -m 0755 /artifact/var/empty \
    && install -Dm644 LICENCE /artifact/licenses/openssh/LICENCE \
    && install -Dm644 /openssl/LICENSE.txt /artifact/licenses/openssl/LICENSE.txt \
    && install -Dm644 /zlib/LICENSE /artifact/licenses/zlib/LICENSE \
    && install -Dm644 /opt/filc/LLVM-LICENSE.txt /artifact/licenses/fil-c/LLVM-LICENSE.txt \
    && install -Dm644 /opt/filc/MUSL-LICENSE.txt /artifact/licenses/fil-c/MUSL-LICENSE.txt \
    && install -Dm644 /opt/filc/PAS-LICENSE.txt /artifact/licenses/fil-c/PAS-LICENSE.txt

# No host private key may enter the artifact: keys are per-deployment secrets,
# generated with ssh-keygen -A wherever the tree is installed.
RUN set -e; \
    if ls /artifact/etc/ssh/ssh_host_*_key 2>/dev/null; then exit 1; fi; \
    cmp sshd_config.out /artifact/etc/ssh/sshd_config; \
    cmp ssh_config.out /artifact/etc/ssh/ssh_config; \
    cmp moduli.out /artifact/etc/ssh/moduli; \
    test ! -e /artifact/etc/ssh/ssh_known_hosts; \
    test "$(stat -c '%u:%g:%a' /artifact/var/empty)" = '0:0:755'

# bin/ holds only static executables in this repository; drop anything else so
# the tree matches what the README says it contains. The type is written to a
# file rather than piped into grep: grep exits at the first match, file dies
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
    find /artifact/bin -mindepth 1 -maxdepth 1 -printf '%f\n' | sort \
        > /tmp/bin.actual; \
    printf '%s\n' scp sftp ssh ssh-add ssh-agent ssh-keygen ssh-keyscan sshd \
        | sort > /tmp/bin.expected; \
    diff -u /tmp/bin.expected /tmp/bin.actual; \
    find /artifact/libexec -mindepth 1 -maxdepth 1 -printf '%f\n' | sort \
        > /tmp/libexec.actual; \
    printf '%s\n' sftp-server ssh-keysign ssh-pkcs11-helper ssh-sk-helper \
        sshd-auth sshd-session | sort > /tmp/libexec.expected; \
    diff -u /tmp/libexec.expected /tmp/libexec.actual

# Executables are built with -g so the checks above can read DWARF. The shipped
# copies drop it: debug information is most of their size and is recoverable by
# rebuilding. Fil-C keeps its own metadata for panic reports, so a stripped
# binary still names the file, line and function that failed.
#
# --strip-debug rather than a full strip, which would also discard .symtab and
# with it the pizlonated and filc_* symbols. Those are how anyone holding the
# artifact can tell it was built with Fil-C at all. Every shipped executable
# is checked afterwards, not a sample of three.
RUN set -e; \
    find /artifact/bin /artifact/libexec -type f -perm -u+x -print0 \
        | xargs -0 -r strip --strip-debug; \
    for f in /artifact/bin/* /artifact/libexec/*; do \
        test -f "${f}" || continue; \
        printf 'checking artifact binary: %s\n' "${f}"; \
        file "${f}" > /tmp/art.desc; \
        grep -Fq "static-pie linked" /tmp/art.desc; \
        readelf -hW "${f}" > /tmp/art.header; \
        machine="$(sed -n 's/^[[:space:]]*Machine:[[:space:]]*//p' /tmp/art.header)"; \
        case "${TARGETARCH}" in \
            amd64) test "${machine}" = 'Advanced Micro Devices X86-64' ;; \
            arm64) test "${machine}" = AArch64 ;; \
            *) exit 1 ;; \
        esac; \
        readelf -lW "${f}" > /tmp/art.segments; \
        ! grep -Fq ' INTERP ' /tmp/art.segments; \
        grep -Fq 'GNU_RELRO' /tmp/art.segments; \
        ! grep -Eq 'GNU_STACK.*RWE' /tmp/art.segments; \
        readelf -SW "${f}" > /tmp/art.sections; \
        ! grep -Fq ".debug_info" /tmp/art.sections; \
        readelf -sW "${f}" > /tmp/art.symbols; \
        grep -Fq "pizlonated" /tmp/art.symbols; \
        grep -Eq "filc_call_user_main|zgc_alloc" /tmp/art.symbols; \
        strings -a "${f}" > /tmp/art.strings; \
        ! grep -q '@llvm\.' /tmp/art.strings; \
        ! grep -Fq 'Unhandled intrinsic' /tmp/art.strings; \
        ! grep -Fq 'cannot handle inline asm' /tmp/art.strings; \
    done; \
    test "$(stat -c '%u:%g:%a' /artifact/libexec/ssh-keysign)" = '0:0:4711'; \
    echo 'all 14 artifact binaries are stripped static Fil-C PIEs without compiler traps'

# Put the shipped, stripped copies at their compiled-in paths before exercising
# them. The disabled PKCS#11 helper logs its refusal only to syslog, while the
# security-key helper writes its refusal to stderr; both must exit 255. sshd -t
# validates the dedicated account and root-owned chroot as well as the installed
# default configuration. Privilege-changing, signalling and task-creation
# syscalls must remain absent from the sandbox allowlist: the uid/gid drop and
# runtime-thread lock happen before the filter instead of widening it.
RUN set -euo pipefail; \
    rm -rf /libexec; \
    cp -a /artifact/bin/. /bin/; \
    cp -a /artifact/libexec /libexec; \
    /bin/sshd -t; \
    ! grep -Eq 'SC_ALLOW\(__NR_(clone|clone3|fork|vfork|setgroups|setgid|setregid|setresgid|setuid|setreuid|setresuid|tkill|tgkill)\)' \
        sandbox-seccomp-filter.c; \
    strings -a /libexec/ssh-pkcs11-helper > /tmp/pkcs11-helper.strings; \
    grep -Fq 'PKCS#11 support disabled at compile time' /tmp/pkcs11-helper.strings; \
    set +e; \
    /libexec/ssh-pkcs11-helper 2> /tmp/pkcs11-helper.log; \
    pkcs11_rc=$?; \
    /libexec/ssh-sk-helper 2> /tmp/sk-helper.log; \
    sk_rc=$?; \
    set -e; \
    test "${pkcs11_rc}" -eq 255; \
    test ! -s /tmp/pkcs11-helper.log; \
    test "${sk_rc}" -eq 255; \
    test "$(cat /tmp/sk-helper.log)" = 'ssh-sk-helper: disabled at compile time'

# Upstream's hostbased regression is isolated because it intentionally mutates
# the builder's global SSH configuration. It drives the stripped ssh-keysign at
# /libexec through every supported host-key algorithm; the staged configuration
# must remain pristine and contain none of that test-only state.
RUN set -euo pipefail; \
    timeout -k 60 900 make t-exec LTESTS=hostbased SUDO=env \
        TEST_SSH_HOSTBASED_AUTH=setupandrun 2>&1 | tee /tmp/hostbased.log; \
    test "$(grep -c '^run test ' /tmp/hostbased.log)" -eq 1; \
    test "$(grep -c '^skip test ' /tmp/hostbased.log || true)" -eq 0; \
    ! grep -Eq '^(Skipped|SKIPPED):' /tmp/hostbased.log; \
    cmp ssh_config.out /artifact/etc/ssh/ssh_config; \
    test ! -e /artifact/etc/ssh/ssh_known_hosts

# Linux ssh-agent rejects clients whose peer uid differs from the agent's uid.
# A successful same-uid connection and the agent's uid-mismatch log ensure the
# negative result reached that check rather than failing on the socket path.
RUN set -euo pipefail; \
    agent_socket=/tmp/peer-uid-agent.sock; \
    rm -f "${agent_socket}"; \
    /bin/ssh-agent -d -a "${agent_socket}" > /tmp/peer-uid-agent.log 2>&1 & \
    agent_pid=$!; \
    cleanup_agent() { kill "${agent_pid}" 2>/dev/null || true; wait "${agent_pid}" 2>/dev/null || true; rm -f "${agent_socket}"; }; \
    trap cleanup_agent EXIT; \
    for _ in 1 2 3 4 5 6 7 8 9 10; do \
        test -S "${agent_socket}" && break; \
        sleep 1; \
    done; \
    test -S "${agent_socket}"; \
    chmod 0666 "${agent_socket}"; \
    set +e; \
    SSH_AUTH_SOCK="${agent_socket}" /bin/ssh-add -l > /tmp/peer-uid-positive.log 2>&1; \
    positive_rc=$?; \
    set -e; \
    set +e; \
    setpriv --reuid="$(id -u sshd)" --regid="$(id -g sshd)" --clear-groups \
        env SSH_AUTH_SOCK="${agent_socket}" /bin/ssh-add -l \
        > /tmp/peer-uid-negative.log 2>&1; \
    negative_rc=$?; \
    set -e; \
    test "${positive_rc}" -eq 1; \
    grep -Fxq 'The agent has no identities.' /tmp/peer-uid-positive.log; \
    test "${negative_rc}" -eq 1; \
    grep -Fxq 'error fetching identities: communication with agent failed' \
        /tmp/peer-uid-negative.log; \
    grep -Fq 'uid mismatch' /tmp/peer-uid-agent.log; \
    cleanup_agent; \
    trap - EXIT

# Final functional proof uses only the stripped artifact. It runs every public
# command, exercises both sshd helper processes and sftp-server, verifies the
# seccomp filter and no-new-privileges state on every execution-capable Fil-C
# task, observes a real process title, rejects an unauthorized key, proves the
# setuid ssh-keysign transition from an unprivileged client, survives SIGHUP,
# and shuts down cleanly. Fil-C 0.684's musl startup keeps the original thread-
# group leader signal-blocked in an infinite pause solely to preserve
# /proc/self; it never enters Fil-C or application code. The task checks that
# exact leader as the sole exception, including the mask with all blockable
# signals blocked and only synchronous faults open, and requires the added
# filter everywhere else.
RUN set -euo pipefail; \
    useradd -m -s /bin/bash sshtest; \
    passwd --delete sshtest; \
    install -d -o sshtest -g sshtest -m 0700 /home/sshtest/.ssh; \
    /bin/ssh-keygen -q -t ed25519 -N '' -f /home/sshtest/.ssh/smoke_key; \
    /bin/ssh-keygen -q -t ed25519 -N '' -f /home/sshtest/.ssh/wrong_key; \
    cp /home/sshtest/.ssh/smoke_key.pub /home/sshtest/.ssh/authorized_keys; \
    chown -R sshtest:sshtest /home/sshtest/.ssh; \
    chmod 0600 /home/sshtest/.ssh/authorized_keys; \
    rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub; \
    /bin/ssh-keygen -A; \
    printf '%s\n' localhost "$(hostname)" > /home/sshtest/.shosts; \
    chown sshtest:sshtest /home/sshtest/.shosts; \
    chmod 0600 /home/sshtest/.shosts; \
    grep -Fqx 'EnableSSHKeysign yes' /etc/ssh/ssh_config \
        || printf '%s\n' 'EnableSSHKeysign yes' >> /etc/ssh/ssh_config; \
    : > /etc/ssh/ssh_known_hosts; \
    for client_host in localhost "$(hostname)"; do \
        for public_key in /etc/ssh/ssh_host_*_key.pub; do \
            printf '%s %s\n' "${client_host}" "$(cat "${public_key}")" \
                >> /etc/ssh/ssh_known_hosts; \
        done; \
    done; \
    for private_key in /etc/ssh/ssh_host_*_key; do \
        test "$(stat -c '%u:%g:%a' "${private_key}")" = '0:0:600'; \
    done; \
    /bin/sshd -t -f /artifact/etc/ssh/sshd_config; \
    printf '%s\n' \
        'Port 2222' \
        'ListenAddress 0.0.0.0' \
        'LogLevel DEBUG3' \
        'PermitRootLogin no' \
        'PubkeyAuthentication yes' \
        'PasswordAuthentication no' \
        'KbdInteractiveAuthentication no' \
        'HostbasedAuthentication yes' \
        'HostbasedUsesNameFromPacketOnly yes' \
        'IgnoreRhosts no' \
        'UsePAM no' \
        'Subsystem sftp /libexec/sftp-server' \
        'PidFile /tmp/smoke-sshd.pid' \
        > /tmp/smoke-sshd_config; \
    sshopts=(-T -p 2222 -i /home/sshtest/.ssh/smoke_key \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o BatchMode=yes); \
    hostbased_opts=(-T -p 2222 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o BatchMode=yes -o HostbasedAuthentication=yes \
        -o PubkeyAuthentication=no -o PreferredAuthentications=hostbased); \
    run_hostbased_client() { \
        setpriv --reuid="$(id -u sshtest)" --regid="$(id -g sshtest)" \
            --init-groups env HOME=/home/sshtest USER=sshtest LOGNAME=sshtest \
            /bin/ssh "${hostbased_opts[@]}" sshtest@127.0.0.1 "$@"; \
    }; \
    start_sshd() { \
        rm -f /tmp/smoke-sshd.pid; \
        : > /tmp/smoke-sshd.log; \
        /bin/sshd -f /tmp/smoke-sshd_config -E /tmp/smoke-sshd.log; \
        for _ in 1 2 3 4 5 6 7 8 9 10; do \
            test -s /tmp/smoke-sshd.pid && break; \
            sleep 1; \
        done; \
        test -s /tmp/smoke-sshd.pid; \
    }; \
    stop_sshd() { \
        server_pid="$(cat /tmp/smoke-sshd.pid)"; \
        kill "${server_pid}"; \
        for _ in 1 2 3 4 5 6 7 8 9 10; do \
            kill -0 "${server_pid}" 2>/dev/null || break; \
            sleep 1; \
        done; \
        ! kill -0 "${server_pid}" 2>/dev/null; \
    }; \
    start_sshd; \
    exec 3<>/dev/tcp/127.0.0.1/2222; \
    printf 'SSH-2.0-filc-smoke\r\n' >&3; \
    privsep_uid="$(id -u sshd)"; \
    privsep_gid="$(id -g sshd)"; \
    auth_pid=; \
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
        for proc_dir in /proc/[0-9]*; do \
            test -r "${proc_dir}/comm" || continue; \
            read -r comm < "${proc_dir}/comm" || continue; \
            test "${comm}" = sshd-auth || continue; \
            proc_pid="${proc_dir##*/}"; \
            for status_file in "${proc_dir}"/task/*/status; do \
                task_dir="${status_file%/status}"; \
                test "${task_dir##*/}" != "${proc_pid}" || continue; \
                if grep -Eq '^NoNewPrivs:[[:space:]]+1$' "${status_file}" \
                        && grep -Eq '^Seccomp:[[:space:]]+2$' "${status_file}"; then \
                    auth_pid="${proc_pid}"; \
                    break; \
                fi; \
            done; \
            test -z "${auth_pid}" || break; \
        done; \
        test -n "${auth_pid}" && break; \
        sleep 1; \
    done; \
    if test -z "${auth_pid}"; then \
        cat /tmp/smoke-sshd.log; \
        for proc_dir in /proc/[0-9]*; do \
            test -r "${proc_dir}/comm" || continue; \
            read -r comm < "${proc_dir}/comm" || continue; \
            case "${comm}" in sshd|sshd-auth|sshd-session) ;; *) continue ;; esac; \
            printf 'process %s (%s): ' "${proc_dir##*/}" "${comm}"; \
            tr '\0' ' ' < "${proc_dir}/cmdline" 2>/dev/null || true; \
            printf '\n'; \
            grep -E '^(State|Pid|PPid|Uid|Gid|Threads|SigBlk|NoNewPrivs|Seccomp|Seccomp_filters):' \
                "${proc_dir}/status" || true; \
            for task_dir in "${proc_dir}"/task/*; do \
                printf 'task %s wchan: ' "${task_dir##*/}"; \
                cat "${task_dir}/wchan" 2>/dev/null || true; \
                printf '\n'; \
                grep -E '^(State|Pid|PPid|Uid|Gid|SigBlk|NoNewPrivs|Seccomp|Seccomp_filters):' \
                    "${task_dir}/status" || true; \
            done; \
        done; \
        exit 1; \
    fi; \
    mapfile -t task_statuses < <(printf '%s\n' /proc/"${auth_pid}"/task/*/status); \
    test "${#task_statuses[@]}" -ge 4; \
    leader_status="/proc/${auth_pid}/task/${auth_pid}/status"; \
    grep -Eq '^State:[[:space:]]+S ' "${leader_status}"; \
    if ! grep -Fq $'SigBlk:\tfffffffc7ffbfa27' "${leader_status}"; then \
        cat "${leader_status}"; \
        exit 1; \
    fi; \
    grep -Eq '^NoNewPrivs:[[:space:]]+0$' "${leader_status}"; \
    leader_filters="$(awk '$1 == "Seccomp_filters:" { print $2 }' "${leader_status}")"; \
    filtered_tasks=0; \
    for status_file in "${task_statuses[@]}"; do \
        awk -v uid="${privsep_uid}" -v gid="${privsep_gid}" \
            '$1 == "Uid:" { u=1; if ($2 != uid || $3 != uid || $4 != uid || $5 != uid) exit 1 } \
             $1 == "Gid:" { g=1; if ($2 != gid || $3 != gid || $4 != gid || $5 != gid) exit 1 } \
             END { if (!u || !g) exit 1 }' "${status_file}"; \
        task_dir="${status_file%/status}"; \
        test "${task_dir##*/}" != "${auth_pid}" || continue; \
        grep -Eq '^NoNewPrivs:[[:space:]]+1$' "${status_file}"; \
        grep -Eq '^Seccomp:[[:space:]]+2$' "${status_file}"; \
        task_filters="$(awk '$1 == "Seccomp_filters:" { print $2 }' "${status_file}")"; \
        if test -n "${leader_filters}"; then \
            test -n "${task_filters}"; \
            test "${task_filters}" -gt "${leader_filters}"; \
        fi; \
        filtered_tasks="$((filtered_tasks + 1))"; \
    done; \
    test "${filtered_tasks}" -eq "$(( ${#task_statuses[@]} - 1 ))"; \
    tr '\0' ' ' < /proc/"${auth_pid}"/cmdline > /tmp/preauth.cmdline; \
    grep -Fq 'sshd-auth: [session-auth]' /tmp/preauth.cmdline; \
    exec 3>&-; \
    grep -Fq 'setting PR_SET_NO_NEW_PRIVS' /tmp/smoke-sshd.log; \
    grep -Fq 'attaching seccomp filter program' /tmp/smoke-sshd.log; \
    grep -Fq "permanently_set_uid: ${privsep_uid}/$(id -g sshd)" /tmp/smoke-sshd.log; \
    if ! /bin/ssh "${sshopts[@]}" sshtest@127.0.0.1 'echo ssh-exec-works' > /tmp/smoke.out; then \
        cat /tmp/smoke-sshd.log; \
        exit 1; \
    fi; \
    grep -Fq ssh-exec-works /tmp/smoke.out; \
    if /bin/ssh -T -p 2222 -i /home/sshtest/.ssh/wrong_key \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o BatchMode=yes sshtest@127.0.0.1 true; then \
        echo 'unauthorized key was accepted' >&2; \
        exit 1; \
    fi; \
    test "$(stat -c '%u:%g:%a' /libexec/ssh-keysign)" = '0:0:4711'; \
    chmod 0711 /libexec/ssh-keysign; \
    set +e; \
    run_hostbased_client true > /tmp/hostbased-setuid-negative.log 2>&1; \
    hostbased_negative_rc=$?; \
    set -e; \
    test "${hostbased_negative_rc}" -eq 255; \
    grep -Fq 'could not open any host key' /tmp/hostbased-setuid-negative.log; \
    grep -Fq 'ssh_keysign: no reply' /tmp/hostbased-setuid-negative.log; \
    chmod 4711 /libexec/ssh-keysign; \
    run_hostbased_client 'echo hostbased-setuid-works' \
        > /tmp/hostbased-setuid-positive.log; \
    grep -Fq hostbased-setuid-works /tmp/hostbased-setuid-positive.log; \
    test "$(stat -c '%u:%g:%a' /libexec/ssh-keysign)" = '0:0:4711'; \
    /bin/ssh "${sshopts[@]}" sshtest@127.0.0.1 'sleep 30' & \
    held_ssh_pid=$!; \
    session_title=; \
    for _ in 1 2 3 4 5 6 7 8 9 10; do \
        for proc_dir in /proc/[0-9]*; do \
            test -r "${proc_dir}/comm" || continue; \
            read -r comm < "${proc_dir}/comm" || continue; \
            test "${comm}" = sshd-session || continue; \
            tr '\0' ' ' < "${proc_dir}/cmdline" > /tmp/session.cmdline 2>/dev/null || continue; \
            if grep -Fq 'sshd-session: sshtest@notty' /tmp/session.cmdline; then \
                session_title=found; \
                break; \
            fi; \
        done; \
        test -n "${session_title}" && break; \
        sleep 1; \
    done; \
    test "${session_title}" = found; \
    kill "${held_ssh_pid}"; \
    wait "${held_ssh_pid}" 2>/dev/null || true; \
    /bin/ssh -tt -p 2222 -i /home/sshtest/.ssh/smoke_key \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o BatchMode=yes sshtest@127.0.0.1 tty > /tmp/smoke.tty; \
    grep -q '^/dev/pts/' /tmp/smoke.tty; \
    printf 'smoke payload\n' > /tmp/smoke-up.txt; \
    /bin/scp -P 2222 -i /home/sshtest/.ssh/smoke_key \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        /tmp/smoke-up.txt sshtest@127.0.0.1:/tmp/smoke-down.txt; \
    grep -Fq 'smoke payload' /tmp/smoke-down.txt; \
    printf 'put /tmp/smoke-up.txt /tmp/smoke-sftp.txt\n' > /tmp/smoke-batch; \
    chmod 0644 /tmp/smoke-up.txt /tmp/smoke-batch; \
    /bin/sftp -P 2222 -i /home/sshtest/.ssh/smoke_key \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -b /tmp/smoke-batch sshtest@127.0.0.1; \
    grep -Fq 'smoke payload' /tmp/smoke-sftp.txt; \
    /bin/ssh-keyscan -p 2222 127.0.0.1 > /tmp/smoke-scan 2>/dev/null; \
    grep -Fq ssh-ed25519 /tmp/smoke-scan; \
    eval "$(/bin/ssh-agent -s)" > /dev/null; \
    /bin/ssh-add /home/sshtest/.ssh/smoke_key; \
    /bin/ssh-add -l > /tmp/smoke-agent-list; \
    agent_key_fingerprint="$(/bin/ssh-keygen -lf /home/sshtest/.ssh/smoke_key.pub | awk '{print $2}')"; \
    grep -Fq "${agent_key_fingerprint}" /tmp/smoke-agent-list; \
    /bin/ssh-agent -k > /dev/null; \
    kill -HUP "$(cat /tmp/smoke-sshd.pid)"; \
    hup_ready=; \
    for _ in 1 2 3 4 5 6 7 8 9 10; do \
        if /bin/ssh "${sshopts[@]}" sshtest@127.0.0.1 \
                'echo survived-sighup' > /tmp/smoke.hup 2> /tmp/smoke-hup.log; then \
            hup_ready=yes; \
            break; \
        fi; \
        sleep 1; \
    done; \
    if test "${hup_ready}" != yes; then \
        cat /tmp/smoke-hup.log /tmp/smoke-sshd.log; \
        exit 1; \
    fi; \
    grep -Fq survived-sighup /tmp/smoke.hup; \
    stop_sshd; \
    echo 'all stripped commands, sandbox state, process titles, authentication, setuid signing, transfers, SIGHUP and shutdown work'

# The artifact is a root filesystem payload, not a runnable appliance: there
# is no passwd or shadow inside it, no host keys, and sshd wants both before
# it will serve. It carries no ENTRYPOINT for that reason; install the tree
# at / on a host that provides accounts and keys. scp and sftp also expect the
# compiled-in /bin/ssh unless their -S option names another client.
FROM scratch AS artifact

ARG FILC_VERSION
ARG OPENSSH_VERSION

LABEL org.opencontainers.image.title="OpenSSH compiled with Fil-C" \
      org.opencontainers.image.description="Statically linked OpenSSH client and server with Fil-C memory safety, OpenSSL and zlib" \
      org.opencontainers.image.version="${OPENSSH_VERSION}-filc${FILC_VERSION}" \
      org.opencontainers.image.source="https://www.openssh.com/" \
      org.opencontainers.image.licenses="BSD-2-Clause AND Apache-2.0 AND Zlib"

COPY --from=build /artifact/ /
