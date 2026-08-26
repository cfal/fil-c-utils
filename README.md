# fil-c-utils

`fil-c-utils` builds statically linked, memory-safe command-line utilities with
[Fil-C](https://fil-c.org/). Every utility has its own Dockerfile, and every
executable is exported directly into the local `out/` directory. Fil-C does
not need to be installed on the host.

Included utilities:

| Utility | Commands exported |
| --- | --- |
| 7-Zip | `7z`, `7zz` |
| unRAR | `unrar` |
| GNU tar | `tar` |
| GNU gzip | `gzip`, `gunzip`, `zcat` |
| bzip2 | `bzip2`, `bzip2recover`, `bunzip2`, `bzcat` |
| XZ Utils | `xz`, `unxz`, `xzcat`, `lzma`, `unlzma`, `lzcat` |
| Zstandard | `zstd`, `unzstd`, `zstdcat` |
| curl | `curl` |
| GNU Wget | `wget` |
| GNU nano | `nano` |
| tmux | `tmux` |
| git | `git` |
| OpenSSH | `ssh`, `sshd`, `scp`, `sftp`, `ssh-add`, `ssh-agent`, `ssh-keygen`, `ssh-keyscan` |

Every utility here reads untrusted input: seven of them parse archives, curl
and wget speak to the network, git clones from it, nano opens whatever file it
is pointed at, tmux parses the escape sequences everything running in its
panes emits, and sshd parses the wire protocol of remote peers it has not
authenticated yet.
Fil-C turns spatial and temporal memory-safety violations into deterministic
process failures. That is useful defense in depth for programs that process
untrusted archives. It does not replace sandboxing, least privilege, archive
size limits, path validation, or timely dependency updates.

## Quick start

Requirements:

- Docker with BuildKit support
- An x86-64 or ARM64 Linux host, or an environment capable of building
  `--platform linux/amd64` or `--platform linux/arm64` images
- Network access to the pinned upstream release files and Ubuntu package
  repositories

Build everything:

```sh
./build-all.sh
```

The script stages all builds and replaces `out/` only after every one has
succeeded. Most utilities contribute only executables and license notices;
git and OpenSSH also contribute runtime support files:

```text
out/
├── bin/
│   ├── 7z
│   ├── 7zz -> 7z
│   ├── bunzip2 -> bzip2
│   ├── bzcat -> bzip2
│   ├── bzip2
│   ├── bzip2recover
│   ├── curl
│   ├── git
│   ├── gunzip -> gzip
│   ├── gzip
│   ├── lzcat -> xz
│   ├── lzma -> xz
│   ├── nano
│   ├── scp
│   ├── sftp
│   ├── ssh
│   ├── ssh-add
│   ├── ssh-agent
│   ├── ssh-keygen
│   ├── ssh-keyscan
│   ├── sshd
│   ├── tar
│   ├── tmux
│   ├── unrar
│   ├── unlzma -> xz
│   ├── unxz -> xz
│   ├── unzstd -> zstd
│   ├── wget
│   ├── xz
│   ├── xzcat -> xz
│   ├── zcat -> gzip
│   ├── zstd
│   └── zstdcat -> zstd
├── etc/
│   └── ssh/
│       ├── moduli
│       ├── ssh_config
│       └── sshd_config
├── libexec/
│   ├── git-core/
│   ├── sftp-server
│   ├── ssh-keysign
│   ├── ssh-pkcs11-helper
│   ├── ssh-sk-helper
│   ├── sshd-auth
│   └── sshd-session
├── licenses/
│   ├── 7zip/
│   ├── bzip2/
│   ├── c-ares/
│   ├── curl/
│   ├── expat/
│   ├── file/
│   ├── fil-c/
│   ├── git/
│   ├── gzip/
│   ├── libidn2/
│   ├── libpsl/
│   ├── libunistring/
│   ├── libevent/
│   ├── nano/
│   ├── ncurses/
│   ├── openssh/
│   ├── openssl/
│   ├── pcre2/
│   ├── tar/
│   ├── tmux/
│   ├── unrar/
│   ├── wget/
│   ├── xz/
│   ├── utf8proc/
│   ├── zlib/
│   └── zstd/
├── share/
│   └── man/
└── var/
    └── empty/
```

The executables are native x86-64 or ARM64 static PIEs, according to the
selected build platform, and have no ELF program interpreter. The commands
without compiled-in helper paths can run directly from `out/`:

```sh
./out/bin/7z t archive.7z
./out/bin/unrar t archive.rar
./out/bin/tar -tf archive.tar
./out/bin/gzip -dc file.gz
./out/bin/bzip2 -dc file.bz2
./out/bin/xz -dc file.xz
./out/bin/zstd -dc file.zst
./out/bin/curl -sSL https://example.com/ -o page.html
./out/bin/wget -qO page.html https://example.com/
./out/bin/nano notes.txt
./out/bin/tmux new-session
./out/bin/git clone https://github.com/git/git.git
./out/bin/ssh-keygen -t ed25519
```

curl and wget both verify certificates against
`/etc/ssl/certs/ca-certificates.crt`, the path compiled in at build time, so
they trust whatever the host trusts and keep benefiting from the host's
certificate updates. Point curl elsewhere with `--cacert`, `--capath`, or
`CURL_CA_BUNDLE`, and wget with `--ca-certificate`, `--ca-directory`, or
`SSL_CERT_FILE`. An environment with no bundle at that path, such as a scratch
container or a distribution that keeps certificates elsewhere, has to supply
one.

git runs many of its subcommands as separate programs from
`libexec/git-core`, so that directory has to travel with `bin/git`. It finds
them relative to its own binary, so the tree works from wherever it is
unpacked; copying the whole `out/` tree keeps the two together, while moving
`bin/git` on its own leaves it unable to find them. It verifies HTTPS
certificates against the same platform bundle curl and wget use, and points
elsewhere with `http.sslCAInfo` or `GIT_SSL_CAINFO`.

OpenSSH has compiled-in absolute paths. `sshd` starts `sshd-session`,
`sshd-auth`, and `sftp-server` from `/libexec`, reads `/etc/ssh`, and chroots
its preauthentication child to `/var/empty`. `scp` and `sftp` start
`/bin/ssh`; run either from an unpacked tree with `-S "$PWD/out/bin/ssh"`.
The other five OpenSSH client commands run standalone.

Install the full OpenSSH tree at `/` in an isolated root filesystem before
starting the server. Do not merge it casually into a distribution host: on a
usrmerged system `/bin` is `/usr/bin`, so this tree replaces the distribution's
OpenSSH programs and `/etc/ssh` configuration. The host must create the
dedicated account and host keys itself; the artifact deliberately contains
neither an account database nor private keys:

```sh
groupadd --system sshd
useradd --system --gid sshd --home-dir /var/empty \
  --shell /usr/sbin/nologin --comment 'sshd privsep' sshd
chown root:root /var/empty
chmod 0755 /var/empty
ssh-keygen -A
sshd -t
```

The per-utility tar artifact preserves root ownership and the setuid-root mode
of `/libexec/ssh-keysign`. A local `build-all.sh` run deliberately leaves the
helper at mode `0711`, because its `out/` files belong to the unprivileged user
that ran the build. After copying that tree as root, make the installed OpenSSH
files root-owned and restore `ssh-keysign` to mode `4711` before running
`sshd -t`.

The `sshd` account must stay locked, own no files, and not be shared with any
other service. `sshd -t` fails closed if that account is absent or `/var/empty`
is not root-owned and protected from group/world writes.

nano carries a set of common terminal descriptions compiled into it, so it
drives a terminal with no terminfo database on disk. Its optional runtime data
uses standard host paths: syntax highlighting reads `/etc/nanorc` and
`/usr/share/nano`, and content-based type detection reads
`/usr/share/misc/magic.mgc`. A host with nano and `file` installed supplies
these; where they are absent nano runs without those two extras. Editing,
UTF-8, mouse, multiple buffers, and the spell and lint hooks do not depend on
them.

tmux carries the same compiled-in terminal descriptions, so it runs where no
terminfo database exists. It needs two of them, one for the terminal it runs
inside and one for the terminal it presents to programs in its panes, and both
are built in. What it does need from the host is a shell: panes run
`$SHELL`, or `/bin/sh` if that is unset, so the scratch image below can report
its version but cannot open a pane.

`linux/amd64` remains the default. Set `PLATFORM` to build the native ARM64
artifacts instead; Fil-C publishes checksum-pinned Pizfix/musl distributions
for both platforms:

```sh
PLATFORM=linux/amd64 ./build-all.sh
PLATFORM=linux/arm64 ./build-all.sh
```

## Using compressed tar archives

GNU tar does not link gzip, bzip2, xz, or zstd into the `tar` executable.
Instead, it starts the appropriate command by name. Put this repository's
`out/` first in `PATH` so tar finds the Fil-C build before a system copy:

```sh
PATH="$PWD/out/bin:$PATH" ./out/bin/tar -czf source.tar.gz source/
PATH="$PWD/out/bin:$PATH" ./out/bin/tar -cjf source.tar.bz2 source/
PATH="$PWD/out/bin:$PATH" ./out/bin/tar -cJf source.tar.xz source/
PATH="$PWD/out/bin:$PATH" ./out/bin/tar --zstd -cf source.tar.zst source/
```

The same rule applies while extracting. The tar Dockerfile deliberately
configures the helper names as `gzip`, `bzip2`, `xz`, and `zstd`, so ordinary
`PATH` lookup is sufficient. You can also select a helper explicitly:

```sh
./out/bin/tar --use-compress-program="$PWD/out/bin/zstd" -xf source.tar.zst
```

The standalone `tar` scratch image contains only `tar`; it cannot process a
compressed archive unless a helper is also present in that container. The
combined local `out/` output is the intended way to use the complete tool set.

## Building one utility

Use Docker's local exporter to build any utility independently:

```sh
docker build \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest=out \
  ./gzip
```

Replace `gzip` with `7z`, `unrar`, `tar`, `bzip2`, `xz`, `zstd`, `curl`, `wget`,
`nano`, `tmux`, or `git`. Docker merges an individual artifact tree into an
existing destination, so old files may remain. `build-all.sh` avoids that
ambiguity by staging every build and replacing `out/` transactionally.
Use `--platform linux/arm64` in the command above for an ARM64 artifact.

OpenSSH must use the tar exporter: Docker's local exporter strips the setuid
bit from `ssh-keysign`. Extract as root with permissions preserved:

```sh
docker build \
  --platform linux/amd64 \
  --target artifact \
  --output type=tar,dest=openssh-server.tar \
  ./openssh-server
mkdir openssh-server-out
tar -xpf openssh-server.tar -C openssh-server-out
```

An arm64 OpenSSH build must run on a native arm64 builder. QEMU user-mode
emulation does not implement the seccomp operation exercised by its test suite.

wget is the one exception to a plain `docker build`. Its HTTPS test suite,
which gates the build, resolves a fixed hostname that the musl-built client can
only reach through `/etc/hosts`, and a Dockerfile cannot write `/etc/hosts`
during a build. Add the mapping on the command line:

```sh
docker build \
  --add-host=WgetTestingServer:127.0.0.1 \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest=out \
  ./wget
```

`build-all.sh` and the CI workflow pass this automatically; only a hand-run
`docker build ./wget` needs it.

Each final stage is also a minimal runnable `scratch` image:

```sh
docker build --platform linux/amd64 -t filc-zstd ./zstd
docker run --rm -i filc-zstd -dc < file.zst > file
```

These images have no shell, package manager, or dynamic loader. They contain
the selected utility, command aliases, and license notices. The OpenSSH image
is a root-filesystem payload rather than a runnable server because it has no
accounts or host keys. The curl image has no CA bundle either, so HTTPS needs
one supplied:

```sh
docker run --rm -v /etc/ssl/certs/ca-certificates.crt:/ca.pem:ro \
    filc-curl --cacert /ca.pem https://example.com/
```

## Checking an artifact

The build and bundle gates reject an artifact unless it has the expected
architecture, is static, has Fil-C symbols, contains no known compiler-trap
marker, and passes the project's tests. You can inspect a built binary yourself:

```sh
file out/bin/tar
readelf -hW out/bin/tar | grep Machine
readelf -lW out/bin/tar | grep INTERP
readelf -sW out/bin/tar | grep -m1 pizlonated
readelf -sW out/bin/tar | grep -Em1 'filc_call_user_main|zgc_alloc'
strings -a out/bin/tar | grep -E '@llvm\.|cannot handle inline asm'
```

`file` should say `static-pie linked`, and `Machine` should match the selected
build platform. The `INTERP` command should print nothing and exit nonzero. The
symbol commands should find Fil-C-transformed names and a Fil-C runtime symbol.
The `strings` command should also print nothing: both patterns identify code
Fil-C replaced with a run-time trap. `ldd` alone is not a sufficient provenance
check.

Shipped executables are built with `-g` and then stripped of debug information,
which is most of their size and is recoverable by rebuilding. `--strip-debug`
is used rather than a full strip so `.symtab` survives, since the two symbol
commands above are how anyone holding an artifact can tell it was built with
Fil-C. Fil-C keeps its own metadata for panic reports, so a stripped binary
still names the file, line and function that failed:

```text
filc safety error: cannot write pointer with ptr >= upper.
    /tmp/oob.c:3:41: inner (inlined)
    /tmp/oob.c:4:61: outer (inlined)
```

The one thing stripping does cost is the `alignment` stage in `tests/`, which
reads DWARF. Run it against an unstripped build, `--target build`, rather than
against `out/`; it reports that it could not scan rather than passing. OpenSSH
runs that scan over all 14 unstripped executables inside its Dockerfile before
the debug sections are removed.

## Robustness testing

Where a project ships a test suite, that suite gates its build: no artifact is
produced unless it passes. This is much stronger than a round-trip smoke test,
because the cases were written by the people who know where the program is
delicate, and every one of them runs against the Fil-C binary.

| Utility | Upstream suite | Result under Fil-C |
| --- | --- | --- |
| GNU tar | Autotest, 226 files | 208 pass, 36 skip |
| curl | 1919 cases | 1675 pass, 244 skip |
| GNU Wget | `tests/` + `testenv/`, 136 cases | 134 pass, 2 skip |
| tmux | `regress/`, 35 cases (git only) | 35 pass |
| gzip | 30 cases | 29 pass, 1 skip |
| XZ Utils | 18 cases | 18 pass |
| Zstandard | `playTests.sh` and fuzzers | all pass |
| bzip2 | 3 sample round trips | pass |
| 7-Zip | **none ships** | — |
| unRAR | **none ships** | — |
| GNU nano | **none ships** | pseudo-terminal edit-and-save |
| git | 1046 files | all pass, 6 cases skipped |
| OpenSSH | `make tests`: 97 functional cases, unit/file/compatibility tests | 87 functional pass, 10 skip; PTY, password, and hostbased pass separately |

Nothing needed to be excluded or marked expected-to-fail: Fil-C causes no
failures in any of them. Skipped cases are features these builds do not enable,
such as HTTP/2 and IDN for curl, or tests needing root for tar. Wget's two
skips are one web-of-trust HTTPS case and one proxy-environment test.

git's six are named individually rather than by dropping the files that hold
them, and all six are the same disagreement between two C libraries. git
converts encodings through musl's iconv, while the suite decides what to expect
by running the distribution's iconv, which is glibc's. Four cases expect the
byte-order mark glibc writes for UTF-16 and UTF-32, which musl does not write;
two compare ISO-2022-JP byte for byte, where musl re-emits the shift sequence
around every character rather than holding it across a run. Both encodings are
valid and decode to the same text. The other forty-nine assertions in those
three files run, and they are the ones that test the encoding machinery.

OpenSSH's ten are named individually, and the build asserts all 97 functional
tests still exist and the exact 87/10 main-suite split. Its PTY test is rerun
with a workaround scoped to an upstream shell-pattern portability bug.
Password authentication is rerun with a throwaway yescrypt password and
succeeds; hostbased authentication is rerun after installation and drives the
shipped `ssh-keysign`. An unprivileged artifact-only client then fails with the
setuid bit removed and succeeds after mode `4711` is restored, proving the
helper's root transition rather than only its executable path. Those overrides
are isolated so they cannot alter the other 87 cases. A live preauthentication
connection also verifies that every
execution-capable Fil-C task has no-new-privileges and the seccomp filter.
Fil-C 0.684 keeps only its original, fully signal-blocked thread-group leader
outside that filter in a permanent `pause()` loop to preserve `/proc/self`;
the build asserts it is the sole exception. The remaining skips need an
external DNSSEC fixture, ptrace tooling and a non-root harness, a PAM or
BSD-auth keyboard-interactive backend, or PKCS#11 provider loading. Seven
third-party interoperability scripts and one extra PKCS#11 script are also
dispatched; their exact expected self-skips are asserted, so an unplanned
self-skip fails the build.

nano's release ships no test suite and the program has no batch mode, so its
gate is to drive the real binary through a pseudo-terminal: type a line, save
it with `^O`, exit with `^X`, and check the file holds exactly those bytes. The
harness points the terminfo path at a directory that does not exist, so a pass
also proves the terminal descriptions compiled into the binary are what let it
run where the scratch image has no terminfo on disk.

tmux's release tarball ships no tests either, but unlike nano its suite does
exist: the 35 scripts in `regress/` live only in the git tree. The build fetches
the same tag a second time as a source archive and takes only that directory,
which is how the unRAR build gets its fixture corpus, and runs the tests against
the binary already built. Two further checks cover what a headless suite cannot.
Attaching is the path where a client hands its terminal's file descriptors to
the server over a unix socket with `SCM_RIGHTS`, so `script(1)` supplies a real
pseudo-terminal and a keystroke is driven through the server into a shell in a
pane. Separately, every terminfo database on the build image is moved aside and
a session is started with none, which proves the compiled-in descriptions rather
than the builder's own database are doing the work.

Four details are easy to get wrong. curl's suite silently skips its 62 HTTPS
cases unless `stunnel4` is installed, and zstd's re-links the CLI, so it needs
the same flags as the build or it fails to link rather than testing anything.
Wget's HTTPS tests name their server `WgetTestingServer` and map it to
localhost through `HOSTALIASES`, a glibc feature the musl client ignores; the
build supplies the mapping with `--add-host` so the eight cases run and pass
rather than failing on an unresolvable host. Wget's top-level `make check` also
recurses into `fuzz/`, whose harnesses need a fuzzing runtime, ship no corpus,
and call `dlsym` at exit, which Fil-C forbids in a static build; its `tests/`
and `testenv/` suites are run directly instead. Where a suite reports a count,
the build asserts a floor under it, because a configuration change that quietly
stopped running most of the cases would otherwise look exactly like a pass.
tmux's `osc-11colours` runs about 250 sub-cases a quarter second apart and
legitimately takes over a minute, so each test gets a generous timeout; a
tighter one kills it mid-run and reads as a failure.

**7-Zip and unRAR ship no test suite at all.** That is why `tests/` exists, and
why its fuzzing is aimed hardest at those two: they have the largest parsing
surface here and the least upstream coverage.

Every exported command is also run before it is shipped, including the alias
symlinks, against the stripped copies rather than the build tree. Creating a
symlink proves nothing about whether the program still picks its mode from
`argv[0]`, and a command that is compiled and checked but never executed can
ship unable to do its job: `bzip2recover` did exactly that, for years, on every
musl system including Alpine.

The suite in `tests/` covers the archive utilities. It checks that the binaries
in `out/` handle correct data exactly, refuse hostile data safely, and survive
corrupt data without a memory-safety failure.

```sh
./tests/run-tests.sh            # all stages
./tests/run-tests.sh --quick    # one mutation per archive per strategy
./tests/run-tests.sh --iters 24 # deeper fuzzing
./tests/run-tests.sh alignment  # one stage only
```

Only the `fuzz` stage takes real time, and it scales linearly with `--iters`.
One iteration is about 3,800 mutated archives and roughly 3 minutes on eight
cores, so the default of 6 lands near 20 minutes and `--iters 24` near 80. The
other four stages together finish in a few minutes, which makes
`./tests/run-tests.sh alignment corpus roundtrip safety` the quick check after
a rebuild.

It needs only Python 3 and the executables in `out/`. Set `FILC_OUT` to test a
different directory and `WORK_DIR` to move its scratch space, which defaults to
`${TMPDIR:-/tmp}/fil-c-utils-tests`.

| Stage | What it establishes |
| --- | --- |
| `alignment` | No compiler traps in any binary; with unstripped DWARF, no unaligned pointer fields |
| `corpus` | Builds ~345 valid archives and 27 hostile ones |
| `roundtrip` | Patched code paths run, valid archives restore byte for byte, host tools agree |
| `safety` | No hostile archive writes outside the extraction directory |
| `fuzz` | Mutated archives produce ordinary errors, never a Fil-C panic |

Building the 7-Zip format corpus uses Docker. Without it that part is skipped
and the run says so; every other stage works from Python 3 alone.

### The alignment stage

Three defects share an awkward shape: they compile cleanly, link cleanly, pass
ordinary functional tests, and then abort at run time on a machine or an input
that happens to reach them. This stage finds all three by reading binaries, so
none needs the trigger to be reproduced. The two compiler-trap checks work on
shipped artifacts; the pointer-layout check needs the DWARF retained in the
unstripped build stage. A normal run against `out/` therefore reports that
half as `PARTIAL`, never as a completed alignment check.

**Misaligned pointer fields.** Fil-C stores a capability beside every pointer
slot and requires those slots to keep their natural alignment. A
`#pragma pack(1)` structure holding a pointer panics the first time that field
is written. The stage reads DWARF and reports any pointer-typed member at an
offset that is not a multiple of `sizeof(void *)`.

**Unhandled intrinsics.** Fil-C compiles an intrinsic it cannot lower into a
trap, embedding the LLVM IR text as the panic message. This matters most for
programs that pick a SIMD implementation from CPUID at run time: the trap is
only reached on a CPU that has the relevant feature, so a build can be clean on
the developer's machine and abort on someone else's. The stage greps each
binary for those embedded strings, which is visible without that CPU.

**Unsupported inline assembly.** On targets where Fil-C cannot lower an inline
assembly block, it embeds a similar run-time trap. Optional architecture paths
can hide it until a particular input selects them, so the stage also rejects
Fil-C's inline-assembly trap marker.

The compiler-trap checks are also asserted by the affected utility Dockerfiles,
and compatibility patches have focused functional assertions. The shared stage
is the compiler-trap backstop over every shipped executable and remains the
cheapest one to run after a dependency upgrade. Structural alignment is instead
gated by focused compile-time assertions or a scan of unstripped build outputs.

### The roundtrip stage

Its first phase drives the code each compatibility patch exists to fix, because
a patch that fails to apply usually still builds and still passes an ordinary
archive round trip. It runs tar's obstack consumers (`--help`, `--usage`,
`--show-defaults`, `--transform`, `--exclude`, `-g`), 7-Zip's `i` command for
the replaced CPUID and XGETBV paths, and every exported alias, since `gunzip`,
`zcat`, `unxz`, `lzcat`, `unlzma`, `unzstd`, `zstdcat`, `bunzip2`, and `bzcat`
select decompression by invocation name rather than by flag.

The remaining phases test every corpus archive, decompress each single-stream
file and compare it against its source, extract each archived tree and compare
every member hash, and hand a sample to the host's own tar, gzip, bzip2, xz,
and unzip. Archives this suite built must exit zero. The pinned rarfile
fixtures are held to a weaker bar, since several are deliberately damaged: they
need only fail the way a program should, with an ordinary exit status and no
Fil-C panic. A stock unRAR build returns the same codes on those files.

### The fuzz stage

Eleven mutation strategies are applied to every corpus archive: bit flips, byte
sets, truncation, header truncation, insertion, zero runs, chunk duplication
and swapping, saturated header bytes, planted 32- and 64-bit size fields, and
oversized octal ASCII for tar's numeric fields. Each mutated file is fed to
every tool that claims its extension, plus 7-Zip, which sniffs the container
itself. Where a tool reads standard input, the same file is also piped to it,
because a decoder that cannot seek takes different branches for headers,
indexes, and trailers; XZ additionally gets a `-T4` run for its threaded
decoder. Runs are capped at 8 GiB of address space, 25 seconds of CPU, and 30
seconds of wall clock.

Every run is classified. `ERR` is the goal for corrupt input, and `OK` is
acceptable since many mutations are harmless. `FILC`, `SIGNAL`, and `TIMEOUT`
are failures, and their inputs are written to the findings directory so they
can be replayed against a rebuilt binary:

```sh
./out/bin/unrar t -y "${TMPDIR:-/tmp}/fil-c-utils-tests/findings/FILC-unrar-..."
```

`OOM` and `HUGE` are reported separately rather than counted as failures. Both
are Fil-C refusing an allocation, which is a resource result rather than a
memory-safety one; see the runtime limitations below.

`TIMEOUT` deserves its own reading. Fil-C does nothing about a decoder that
simply never finishes, so a hang found here is almost always an upstream defect
present in an ordinary build too, and worth confirming against one before
blaming this repository. Fuzzing found such a case: setting one byte in a
QCOW2 header makes the virtual disk size 64 PiB, and 7-Zip's QCOW handler then
walks the implied cluster table, burning CPU indefinitely on a 640 KB file.
Stock 7-Zip 26.02 behaves identically. It is a good reminder that memory safety
and resource safety are separate problems, and that only the first one is
solved here.

### 7-Zip's format handlers

7-Zip is by a wide margin the largest attack surface here. `7z i` lists 61
compiled-in container handlers and 25 codecs, and its published vulnerability
history sits mostly in the filesystem, disk-image, and installer handlers
rather than in `.7z` or `.zip`. Fuzzing only the containers 7-Zip can write
would leave nearly all of that untested, so the corpus is built from three
sources:

- **The codec and filter matrix**, written by 7-Zip itself: LZMA, LZMA2, PPMd,
  BZip2, Deflate, Deflate64, Copy, the BCJ, BCJ2, ARM, ARM64, ARMT, PPC, SPARC,
  IA64, RISCV, Delta, Swap2 and Swap4 filters, AES-256 with and without header
  encryption, ZipCrypto, deep solid blocks, multi-volume sets, and `wim`. The
  branch filters get executable input, since they rewrite call targets in place
  and do nothing to text.
- **Real containers** built in `tests/formats` by a Docker image carrying the
  tools a build host does not normally have: `qemu-img` for QCOW, QCOW2, VMDK,
  VHD, VHDX and VDI; `mksquashfs`, `mkfs.ext4`, `mkfs.vfat` for FAT12/16/32,
  `mkfs.ntfs`, `mkfs.hfsplus`, `genisoimage`, `mkudffs`, `sgdisk`, `sfdisk`,
  `ar`, `cpio`, `gcab`, `arj`, `compress`, `dpkg-deb`, `rpmbuild`, `img2simg`,
  and `objcopy` for PE and IHex.
- **Hand-written containers** in `tests/make-7z-synthetic.py` for formats no
  Linux tool still produces: Mach-O, universal binaries, LHA, SZDD, XAR,
  compressed SWF, CramFS and several others, each written from its published
  layout.

That reaches 34 handlers with containers that open cleanly, against roughly
eight before. The rest are covered by forcing the handler.

**Forcing the handler matters more than the corpus.** 7-Zip selects a handler
from the file's magic bytes, so a mutation that lands on those bytes stops at
dispatch and never enters the parser under test — most of a naive fuzzing run
is wasted that way. Every container is therefore recorded in `7z-manifest.tsv`
with the handler it targets, and the fuzzer runs it three ways: by
autodetection, with an explicit `-t` for its own handler, and with `-t` for two
randomly chosen other handlers. That last one is what gives the formats with no
Linux writer any exposure at all, since it makes them parse large volumes of
structured, mutated input they would otherwise never see.

The manifest's third column records whether each container actually opens. A
few hand-written ones carry correct magic but not a structure the handler
accepts; they stay in the corpus as seeds, and the column stops the roundtrip
stage from demanding a clean test from them. That stage also re-verifies every
container still reaches its handler, so a generator that quietly stops
producing a real image is caught rather than leaving the fuzzer to report
success while testing nothing.

### Why the fuzzer checks itself first

A fuzzing run reports success both when the tools are sound and when the
harness never reached them, and the two are hard to tell apart from a summary
table full of `ERR`. That is not hypothetical here: forcing the handler was
briefly broken by a malformed `-t` argument, and 25,740 runs scored as clean
rejections while 7-Zip was in fact refusing the command line before opening
anything.

So `fuzz.py` runs a preflight. Every distinct action shape is tried once
against an *unmutated* corpus file, where anything other than success means the
harness is wrong rather than the tool, and a malformed invocation aborts the
run instead of producing a reassuring table. Cross-typed actions are exempt,
since being rejected is the point of those.

The same reasoning applies when reading results. A tool with zero `OK` verdicts
across thousands of runs is usually a broken invocation, not a tool that
rejects everything; treat that row as a harness bug until shown otherwise.

### The safety stage

Fil-C stops memory-safety violations. It does nothing about an archive whose
member is named `../../etc/cron.d/root`, so that risk is covered separately.
The stage builds tar, zip, RAR 5, cpio, and ar archives that attempt relative
traversal, absolute paths, Windows separators and drive letters, and symlinks
planted so that a later member writes through them, then extracts each into a
jail and fails if anything appears outside it. unRAR cannot create archives, so
`tests/rar5.py` synthesises the RAR 5 headers directly. cpio and ar are
included because 7-Zip sanitises member names per handler, so covering only its
zip path would say nothing about the others.

The stage verifies its own detector before trusting any result: an extraction
with tar's `-P`, which is documented to allow escapes, must escape. If that
control stays contained the harness is broken and the run aborts.

## Pinned source inputs

All downloaded release archives are version-pinned and SHA-256 verified before
extraction. The Dockerfile frontend and Ubuntu builder use rolling tags rather
than content-addressed image digests.

| Component | Version | SHA-256 |
| --- | --- | --- |
| Fil-C (x86_64) | 0.684 | `eefb594bcbc1261a18dfa8b50041674635f53df2b5fe067915b5652adaed4e3f` |
| Fil-C (aarch64) | 0.684 | `564813b819a6e73879bdd993e2176b38ccbd5c5219e5adcbe1589e874c860666` |
| 7-Zip source | 26.02 | `cf967c98bca02a4b8b16375f441825a8e141362f14be1969bbec8e1ca0bff9dd` |
| unRAR source | 7.2.7 | `01d903a7dcf413cb2925696d7796e48e38d471f79bfe7ef3ad2aebf6c12dbefd` |
| GNU tar source | 1.35 | `4d62ff37342ec7aed748535323930c7cf94acf71c3591882b26a7ea50f3edc16` |
| GNU gzip source | 1.14 | `01a7b881bd220bfdf615f97b8718f80bdfd3f6add385b993dcf6efd14e8c0ac6` |
| bzip2 source | 1.0.8 | `ab5a03176ee106d3f0fa90e381da478ddae405918153cca248e682cd0c4a2269` |
| XZ Utils source | 5.8.3 | `fff1ffcf2b0da84d308a14de513a1aa23d4e9aa3464d17e64b9714bfdd0bbfb6` |
| Zstandard source | 1.5.7 | `eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3` |
| curl source | 8.19.0 | `4eb41489790d19e190d7ac7e18e82857cdd68af8f4e66b292ced562d333f11df` |
| GNU Wget source | 1.25.0 | `766e48423e79359ea31e41db9e5c289675947a7fcf2efdcedb726ac9d0da3784` |
| OpenSSL source | 3.5.7 | `a8c0d28a529ca480f9f36cf5792e2cd21984552a3c8e4aa11a24aa31aeac98e8` |
| zlib source | 1.3.1 | `9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23` |
| libunistring source | 1.4.2 | `5b46e74377ed7409c5b75e7a96f95377b095623b689d8522620927964a41499c` |
| libidn2 source | 2.3.8 | `f557911bf6171621e1f72ff35f5b1825bb35b52ed45325dcdee931e5d3c0787a` |
| libpsl source | 0.23.0 | `f39b9631b3d369a21259ea4654f8875c0ec6995ce9551c0eb5d423e4c011f911` |
| PCRE2 source | 10.47 | `c08ae2388ef333e8403e670ad70c0a11f1eed021fd88308d7e02f596fcd9dc16` |
| c-ares source | 1.34.8 | `c222b6d681096f9444d2c4863d2c1174019e27cacca0a4a5c114d36dd7d7bf78` |
| GNU nano source | 9.1 | `5f47764274cb7532349ce0aa20ec10f1e8e851a6e9fa3eb66812c43d196db042` |
| ncurses source | 6.6 | `355b4cbbed880b0381a04c46617b7656e362585d52e9cf84a67e2009b749ff11` |
| file source | 5.46 | `c9cc77c7c560c543135edc555af609d5619dbef011997e988ce40a3d75d86088` |
| tmux source | 3.7b | `87f2e99e3b685973f2ca002ffd6ed7e51a5744f7009daae5a15670b6d532db96` |
| tmux tests (git tag) | 3.7b | `156dc43dcbc7f06e35e1fae3118c44d77a370c46676b34b82bbafc4e608d8130` |
| libevent source | 2.1.13 | `f7e9383b8c0baa81b687e5b5eecc01beefaf1b19b64151d95ed61647fe7a315c` |
| utf8proc source | 2.11.3 | `abfed50b6d4da51345713661370290f4f4747263ee73dc90356299dfc7990c78` |
| OpenSSH portable source | 10.5p1 | `d44d28a839ea9daf969cc69150fde59910b2b39361dad81a3bd6cbd19218db11` |

The Dockerfile frontend, Ubuntu base image, and Ubuntu packages installed in
the builder are not pinned to immutable digests or a snapshot repository. They
can change as their tags and repositories receive updates, so these builds are
source-pinned and resistant to upstream release URL drift, but are not
guaranteed to be bit-for-bit reproducible. The exported programs do not depend
on those Ubuntu packages at runtime.

License notices for each utility and the statically linked Fil-C runtime are
exported beside the binaries. 7-Zip includes code under its documented unRAR
restriction. RARLAB's unRAR license prohibits using its source to recreate the
RAR compression algorithm. Review `out/licenses/` before redistribution.

## Build limitations

- GNU tar is built without ACL, POSIX ACL, SELinux, extended-attribute, or NLS
  support. Normal file modes, ownership, timestamps, links, and archive formats
  remain available.
- Only executable commands are exported. Shell-script companions such as
  `zgrep`, `bzgrep`, and `xzgrep` are not included in the static artifact set.
- XZ's assembler optimizations and platform sandbox are disabled. Fil-C still
  instruments the C implementation, but process isolation remains the caller's
  responsibility.
- zstd's optional gzip, xz, and lz4 compatibility integrations are disabled to
  prevent accidental linkage against host libraries. Native `.zst` support and
  threading are enabled.
- Build-stage binaries retain DWARF for validation. Shipped binaries use
  `--strip-debug`, preserving `.symtab` and Fil-C's own diagnostic metadata but
  removing DWARF. Static Fil-C runtime and metadata still make them larger than
  conventional dynamically linked distribution builds.
- curl is built without HTTP/2, HTTP/3, brotli, zstd, IDN, PSL and LDAP. It
  keeps HTTP/1.1, TLS via OpenSSL, gzip via zlib, and the protocols OpenSSL and
  musl support unaided.
- curl's OpenSSL has no assembly, so TLS throughput is well below a
  distribution build. Upstream Fil-C's OpenSSL port also carries roughly 90 KB
  of changes for constant-time guarantees that this build does not apply; the
  library is functionally correct without them, but side-channel resistance in
  some primitives is weaker than upstream OpenSSL.
- wget is built with almost every feature: HTTPS via OpenSSL, gzip via zlib,
  internationalized URLs via libidn2, Public Suffix List cookie checking via
  libpsl, PCRE2 regular expressions, asynchronous DNS via c-ares, NTLM, digest
  and opie authentication, IPv6, and WARC output. Metalink is the one feature
  left off: it needs GPGME to verify signatures, and GPGME is not among the
  libraries ported to Fil-C. NLS is also off, as it is for curl. wget shares
  curl's no-assembly OpenSSL and the throughput and side-channel caveats above.
- OpenSSH is built without PKCS#11 token providers or FIDO/security-key
  providers because those paths load host shared objects that a static Fil-C
  process cannot use. PAM, Kerberos, and BSD authentication are also absent.
  Password authentication, including yescrypt hashes, works through the system
  account database. The default configuration still spells
  `KbdInteractiveAuthentication yes`, but no keyboard-interactive backend is
  compiled in, so that method is inert. OpenSSH shares curl's no-assembly
  OpenSSL and the throughput and side-channel caveats above. Fil-C 0.684 cannot
  lower the overflow traps from OpenSSH's `-ftrapv` hardening flag, so this
  build uses `-fwrapv`: signed overflow is defined to wrap instead of aborting.
  Fil-C still checks every memory access, but a non-memory overflow logic bug
  continues with the wrapped value rather than failing immediately. On
  AArch64, sntrup761 uses cryptoint's portable C because Fil-C 0.684 cannot
  lower its AArch64 inline assembly; sntrup and ML-KEM remain enabled.
  Cryptoint intends this fallback to resist timing-changing optimization but
  does not guarantee constant-time execution, and its Fil-C/AArch64 machine
  code has not been side-channel audited.
- tmux is built with sixel image support and utf8proc, which replaces its
  built-in character-width tables with fuller Unicode ones. systemd integration
  is left off: it would link libsystemd and defeat a self-contained static
  binary. tmux runs panes with `$SHELL` or `/bin/sh`, so unlike the other
  utilities its scratch image is only useful for `tmux -V`; a pane needs a
  shell the image does not contain.
- git is built with its http and https remotes through libcurl, `grep -P`
  through PCRE2, and http pushing through expat. Two subsystems are off. git
  2.55 implements some of its object-store code in Rust, and Fil-C compiles C
  and C++ only, so `NO_RUST` selects the C implementations those replace.
  `NO_REGEX=NeedsStartEnd` uses git's bundled regex because musl's `regexec`
  has no `REG_STARTEND`. `core.fsyncMethod=batch` falls back to a full fsync
  and says so: it wants a writeout-only flush through `sync_file_range`, which
  Fil-C's musl does not implement, and git is built without it so that the
  setting degrades rather than aborting the command. The built-in filesystem
  monitor is off for the same reason: that daemon crashed under Fil-C, leaving
  a core file behind and the client reporting a reset connection, so git is
  built without the backend and reports `fsmonitor--daemon is not supported on
  this platform`. `core.fsmonitor` still works in its hook form, where the
  monitor is a program you name rather than one git runs itself. git shares
  curl's no-assembly OpenSSL, ARM lock fallback, and the throughput and
  side-channel caveats above.
  The Perl and Python subcommands are not exported: they are scripts, not
  executables, and this repository ships only the latter.
- One thing to know about git under load: when many copies of it run at once,
  a push occasionally stops making progress and has to be killed. This build
  does not introduce it. Fil-C's own git port, built from the source Fil-C
  ships, does the same thing, and the same git source built against glibc came
  through the identical stress without a stall. It is intermittent rather than
  reliable, and it has not been seen running one git at a time, which is why
  the build gives each test file a ceiling and retries a file that hits it
  rather than treating the whole suite as broken. What the stalled processes
  look like from outside is a fork whose child never reaches `exec` while both
  its threads wait on a held lock; that is a description of the symptom, not a
  diagnosis, since a reproducer built to provoke exactly that shape could not.

## Runtime limitations

Allocation failure is not recoverable. Fil-C panics when it cannot satisfy an
allocation, where an ordinary build would return `NULL` and let the program
report an error and exit. A malformed archive that provokes a large allocation
therefore aborts the process under a memory cap that a conventional build would
survive. A corrupt 32-byte `.xz` index illustrates it:

| Address-space cap | Stock xz 5.8.3 | This build |
| --- | --- | --- |
| 4 GiB | `Cannot allocate memory`, exit 1 | Fil-C panic, exit 133 |
| 8 GiB | `Compressed data is corrupt`, exit 1 | Fil-C panic, exit 133 |
| 10 GiB | `Compressed data is corrupt`, exit 1 | `Compressed data is corrupt`, exit 1 |

Both builds want several GiB to reject that file, which is an upstream property
of xz 5.8.3 rather than something Fil-C introduces; 5.4.5 rejects it in under
1 GiB. Fil-C adds roughly a quarter again on top. The difference that matters
here is the failure mode: a panic instead of a clean diagnostic. Size the
memory limit for a container running these utilities with that in mind, and
treat an abort under a tight cap as a resource result rather than evidence of a
memory-safety defect. The fuzz stage classifies it as `OOM` for that reason.

The sharper form of this needs no memory limit at all. Fil-C will not create an
object beyond a maximum size, and asks for one are refused with a panic rather
than a recoverable failure. A corrupt archive whose header carries an
unvalidated length reaches that ceiling directly. Fuzzing found one in 7-Zip's
WIM handler, where `CUnpacker::Unpack2` sizes a buffer straight from the
resource header (`WimIn.cpp:312`); an 11 MB file asks for 1.88 PiB:

| | Stock 7-Zip 26.02 | This build |
| --- | --- | --- |
| Result | `ERROR: Can't allocate required memory!` | `filc safety error: attempt to allocate object that is too big` |
| Exit | 2 | 133 |

The unvalidated size field is an upstream weakness present in both builds. Only
the outcome differs, and it differs the same way as the xz case: an ordinary
build reports an error and exits, this one aborts. The fuzz stage reports these
as `HUGE`, separately from `OOM` and from real memory-safety failures, because
all three read very differently in a summary table and only the last is a
Fil-C-caught bug.

The practical consequence for both forms is the same. Fil-C makes these
utilities memory-safe, not crash-free, on hostile input. A service that must
stay available needs supervision and per-request isolation regardless.

The same holds for the memory-safety violations Fil-C is actually there to
catch: turning one into a deterministic process failure is containment, not
recovery.

## Maintainer guide

### Repository layout

```text
.
├── .gitignore
├── README.md
├── build-all.sh
├── check-versions.py
├── .github/workflows/
│   ├── ci.yml
│   ├── build.yml
│   └── versions.yml
├── 7z/
│   ├── Dockerfile
│   └── patches/
├── bzip2/
│   └── Dockerfile
├── curl/
│   └── Dockerfile
├── git/
│   ├── Dockerfile
│   └── patches/
├── gzip/
│   └── Dockerfile
├── nano/
│   ├── Dockerfile
│   └── smoke.c
├── openssh-server/
│   ├── Dockerfile
│   ├── check-alignment.pl
│   └── patches/
├── tar/
│   ├── Dockerfile
│   └── patches/
├── tmux/
│   └── Dockerfile
├── unrar/
│   ├── Dockerfile
│   └── patches/
├── wget/
│   └── Dockerfile
├── xz/
│   └── Dockerfile
├── zstd/
│   ├── Dockerfile
│   └── patches/
└── tests/
    ├── run-tests.sh
    ├── lib.sh
    ├── make-seed.py
    ├── make-corpus.sh
    ├── make-rar-corpus.py
    ├── make-7z-corpus.sh
    ├── make-7z-synthetic.py
    ├── make-hostile.py
    ├── rar5.py
    ├── scan-alignment.py
    ├── roundtrip.py
    ├── extraction-safety.py
    ├── fuzz.py
    └── formats/
        ├── Dockerfile
        └── generate.sh
```

Each Dockerfile owns its source pins, toolchain setup, compile flags, static
link assertions, Fil-C provenance assertions, functional tests, licenses, and
artifact stage. Keep utility-specific work inside that utility's directory.

`tests/` works on the finished `out/` tree and belongs to no single utility. It
covers what a per-utility build check cannot: behaviour across formats, hostile
input, and inputs that no upstream test suite ships.

`ci.yml` runs on pushes to `main`, on pull requests, and on `v*` tags, in four
stages: build, then the test suite against those binaries, then the bundle,
then a release for tags only. The build and test matrices use native GitHub
runners for both x86_64 and aarch64. Each stage depends on the one before it,
so a failing suite means no architecture bundle is published and no release is
drafted. `build.yml` holds the compile matrix and exists only to be called from
`ci.yml`; the utilities build independently, so running them in parallel makes
CI take the time of the slowest one rather than the sum of them all.

### Cutting a release

Push a tag beginning with `v`:

```sh
git tag v1.0.0
git push origin v1.0.0
```

That runs the whole pipeline against the tag and, if every stage passes, drafts
a GitHub release holding `fil-c-utils-v1.0.0-x86_64.tar.gz` and
`fil-c-utils-v1.0.0-aarch64.tar.gz`, each with its `.sha256`. The release is a
**draft**, so it is reviewed before anyone can download it. Tagged builds take
their version from the tag; every other build is named for the short commit
hash.

The release job is the only one granted `contents: write`, and it hangs off the
bundle, which hangs off the test suite. A tag cannot produce a release whose
binaries failed the suite. It re-verifies the checksum after downloading the
artifact rather than trusting the round trip through artifact storage.

### Version freshness

`versions.yml` runs when a pull request is opened and checks every upstream pin
registered in `check-versions.py` against its latest release. If any registered
pin is behind, it posts the report as a comment on the pull request. It never
fails the workflow: a dependency falling behind is worth putting in front of a
reviewer, but it is not a reason to block a change that touches none of it.
When every registered pin is current it stays silent.

It runs `check-versions.py`, which reads each pin from its Dockerfile, asks each
upstream for its newest release, and prints one row per component:

```text
component  pinned     latest     status
7z         26.02      26.02      ok
...
curl       8.19.0     8.21.0     OUTDATED
```

The `COMPONENTS` table is explicit rather than discovered from Dockerfile
arguments. Every upstream has a different release source, so the registered
sources are queried differently: GitHub releases for 7-Zip, XZ, Zstandard,
curl, OpenSSL, and zlib; GNU listings for GNU projects; sourceware for bzip2;
and rarlab for unRAR. A new maintained release pin needs a table entry and an
upstream-specific lookup or it will not receive freshness reports.

The check never stops at the first problem. A component whose upstream is
unreachable, or whose listing has changed shape, is reported as an error and
the walk continues, so a single flaky host cannot hide a stale pin behind it.
It runs locally the same way, where it does exit nonzero if anything is behind,
so it works as a plain command as well as a source of comment text:

```sh
python3 check-versions.py
```

Two caveats. OpenSSL maintains several release branches in parallel (a 3.5.x
alongside a 4.0.x, for instance) and marks the newest of each as a release, so
each pin must be compared with the branch it intentionally follows. Fil-C
itself is not checked: it is the toolchain rather than a utility, and moving it
is a larger compatibility decision than a pin bump. A pull request opened from
a fork gets a read-only token and cannot be commented on; the check still runs
and prints its report to the workflow log.

### Build design

The builders use Fil-C's Pizfix/musl release rather than the glibc-oriented
host installation. Pizfix includes the static libc, C++ library, and Fil-C
runtime archives needed for standalone executables.

Every Dockerfile builds with `-g` and checks its unstripped native executables
before staging them. Across the Dockerfile and bundle gates, every shipped ELF,
including helper programs outside `bin/`, is checked for:

- the expected x86-64 or AArch64 ELF machine
- `static-pie linked` in `file` output
- no ELF `INTERP` program header
- a DWARF `.debug_info` section before stripping
- `pizlonated` transformed symbols
- a Fil-C runtime symbol such as `filc_call_user_main` or `zgc_alloc`
- no embedded `@llvm.` unhandled-intrinsic marker
- no embedded `cannot handle inline asm` marker
- successful startup and a meaningful functional round trip

The staged copies use `strip --strip-debug`, not a full strip. That removes
DWARF while retaining `.symtab`, so anyone holding an artifact can still verify
the transformed and runtime symbols. Fil-C's diagnostic metadata remains too,
so a safety failure still identifies its source location. Static-link and
provenance checks run again against the stripped copies, and exported aliases
are invoked by name before shipping.

The `scratch` artifact stage is both the local-export tree and the final image.
It ensures an accidentally dynamic binary cannot appear to work merely because
the builder's loader or libraries are available. It also makes required helper
paths and runtime data explicit. Every utility exports its own license, the
licenses of its static dependencies, and the Fil-C runtime licenses beside the
binaries.

### Architecture support

Every utility supports both `linux/amd64` and `linux/arm64`. Docker exposes
those targets to a Dockerfile as `TARGETARCH=amd64` and `TARGETARCH=arm64`,
while Fil-C names its release assets `x86_64` and `aarch64`. Each Dockerfile's
architecture switch maps those names, selects a separate checksum pin, and
rejects any unknown target.

The CI build, robustness, audit, and bundle jobs use native runners for both
architectures. Dockerfiles execute the programs and their upstream suites while
building, so native CI is the authoritative gate; emulated local builds can be
much slower. Stage artifacts and download patterns include the architecture to
prevent valid binaries from different machines being merged into one bundle.

Architecture-specific source patches are guarded with both `__FILC__` and the
compiler's target macro. An ARM workaround must leave x86 code generation
unchanged unless the investigation also found a shared x86 defect, and vice
versa.

### Compatibility details

7-Zip's x86 feature detection normally uses inline CPUID and XGETBV assembly.
Its patch substitutes Fil-C's supported intrinsic interfaces on x86 only; ARM64
keeps 7-Zip's native architecture paths. One of those paths uses the inline ARM
`rbit` instruction in the Deflate decoder, which Fil-C 0.684 cannot lower. An
ARM-only patch selects 7-Zip's existing bit-reversal table instead, and the
Dockerfile gates both Deflate-in-7z and ZIP decoding. The build also defines
`Z7_NO_LARGE_PAGES`; 7-Zip's 2 MiB alignment request exceeds Fil-C's supported
allocation alignment.

A second 7-Zip patch removes the AVX-family SIMD paths. Fil-C implements the
SSE and AES-NI intrinsics 7-Zip uses, but not the AVX ones: the VAES AES path,
Blake2s AVX2/AVX-512, the LzFind 256-bit match finder, the AVX2 byte swapper,
and the SHA-512 extension all reach `llvm.x86.avx.vzeroupper`, which Fil-C
compiles into a trap. Because 7-Zip chooses among these from CPUID at run time,
the defect is invisible on a CPU without the feature. A build tested on a Zen 2
machine, which has no VAES, ran encrypted archives perfectly and then aborted
in `AesCtr_Code_HW_256` on CI hardware that does. The patch has to touch both
the definition and the dispatch for each path, since 7-Zip repeats the same
compiler-version block in `AesOpt.c` and `Aes.c` and `MyAes.cpp`, and again in
`Sha512Opt.c` and `Sha512.c`. SSE and AES-NI stay enabled.

Three 7-Zip handlers keep 12-byte POD records in `CRecordVector`. The AArch64
ABI copies those values with an 8-byte access followed by a 4-byte access, while
their normal 12-byte stride leaves every other element only 4-byte aligned.
Fil-C correctly rejects that widened access. An ARM-only patch aligns the RAR,
UDF, and SquashFS records to 8 bytes, making their internal stride 16 bytes. The
change costs 4 bytes per live record and does not affect any on-disk layout.

unRAR normally enables packed structures and misaligned integer access on
x86-64 and ARM64. Fil-C requires pointer slots to retain their natural
alignment, so the unRAR patch selects the existing alignment-safe code paths
under Fil-C. Tests use the checksum-pinned `markokr/rarfile` fixture corpus at
commit
`09fd4f216ef502e478f1aeb6f0e193b49056eee8`, covering more than 50 RAR 1.5,
RAR 2, RAR 3, and RAR 5 archives, including solid, encrypted, multi-volume,
Unicode, link, timestamp, and deliberately unusual cases.

That patch needs its own assertion, because nothing else catches it failing.
`ALLOW_MISALIGNED` controls `#pragma pack(1)` on unRAR's PPMd structures, and
packed they hold pointers at offsets 2, 4, and 12. Such a build compiles,
links, satisfies every static-link and Fil-C-symbol check, and passes all 51
fixture archives, because valid RAR files rarely drive the RAR3 PPMd decoder
deep enough to write through one of those fields. It then panics on a RAR3
archive that does. The Dockerfile therefore compiles a translation unit that
asserts `ALLOW_MISALIGNED` is undefined and that each PPMd pointer member sits
at a multiple of `alignof(void *)`. The `alignment` stage can re-check the same
property from an unstripped build's DWARF. Shipped `out/` binaries have no
DWARF, so that run checks compiler traps but reports structural alignment as
`PARTIAL`; the focused compile-time assertion remains the build gate.

GNU tar's bundled obstack implementation normally aligns pointers relative to
address zero. The tar patch uses the obstack allocation as the alignment base
under Fil-C, preserving pointer provenance for help generation, transforms,
incremental archives, and other obstack consumers.

gzip defines `GNU_STANDARD=0` so its documented `gunzip` and `zcat` invocation
names select decompression mode. The Dockerfile tests both aliases rather than
assuming that creating the links is sufficient.

gzip and nano both vendor gnulib's x87 control-word helper. On x86-64 its
long-double formatting path normally saves and restores the precision control
with inline `fnstcw` and `fldcw`, whose memory operands Fil-C turns into run-time
traps. Fil-C's musl fenv implementation cannot change x87 precision, so the
default extended precision remains in effect. Scoped patches omit the redundant
save and restore under Fil-C. Both Dockerfiles reject the compiler's trap marker
if any unsupported inline assembly remains.

XZ uses `LDFLAGS=-Wc,-static` during `make`. Libtool consumes plain `-static`
as a request to prefer static project libraries and otherwise emits a
dynamically loaded Fil-C executable. `-Wc,-static` passes the flag through to
the Fil-C driver, producing the required static PIE. Defining
`LZMA_RANGE_DECODER_CONFIG=0` selects XZ's portable C range decoder instead of
its x86 inline-assembly decoder.

curl is the only utility here with dependencies, and Fil-C's release ships
just libc, libc++ and its runtime, so its Dockerfile builds zlib and OpenSSL
with the same compiler into a shared `/deps` prefix before building curl.

OpenSSL needs `no-asm`, because Fil-C cannot compile its hand-written assembly.
Every primitive therefore runs the portable C path, which costs throughput on
TLS-heavy transfers and is the main price of this build. `no-shared` and
`no-module` avoid the linker version scripts that are the only change Fil-C's
own OpenSSL port required, and `OPENSSL_NO_SECURE_MEMORY` disables the
mlock-backed secure heap that port asserts is unused. Two settings are easy to
get wrong: `--libdir=lib` is required because OpenSSL defaults to `lib64` on
x86-64 while curl derives `-L<prefix>/lib` from `--with-openssl`, and the
mismatch fails the static link with a bare `cannot find -lssl`; and
`make install_ssldirs` has to follow `install_sw`, or `openssl.cnf` is missing
and the build's own TLS test cannot generate a certificate.

curl needs the same libtool treatment as XZ, for the same reason: a plain
`-static` yields a dynamically loaded Fil-C executable, and `-Wc,-static` at
`make` time is what produces the static PIE. Overriding `LDFLAGS` there
replaces what configure recorded, so `-L/deps/lib` has to be repeated.

On ARM64, curl's global-init lock normally uses an inline `yield` instruction
that Fil-C compiles into a run-time trap. The local patch excludes that
optional assembly under Fil-C and selects curl's existing `sched_yield()`
fallback. Curl's thread-safety test exercises the patched lock. Git statically
links its own libcurl and applies the same patch.

The CA bundle is not embedded. curl's `--with-ca-embed` would compile a copy
into the executable, but it prefers that copy over the system store rather than
falling back to it, so a host's certificate updates would stop applying. A
build that embeds the bundle also fails 28 of curl's own tests, which compare
verbose stderr byte for byte and see its `Using embedded CA bundle` note.
Reading the platform's store avoids both, at the cost of needing a bundle
supplied where the platform has none.

Zstandard is built with `ZSTD_NO_ASM=1`. Version 1.5.7 has one pointer-returning
assembly block and several optional alignment blocks that do not honor
`ZSTD_DISABLE_ASM`, so the local patch extends those guards and selects the
existing portable C implementation.

On ARM64, `ZSTD_NO_INTRINSICS` also selects Zstandard's portable SWAR row
matcher. Its NEON matcher uses structured `ld2` and `ld4` loads that Fil-C
0.684 compiles into unhandled-intrinsic traps. The flag is architecture-scoped,
so x86 keeps its supported SIMD matcher.

Zstandard's optimal parser also stores 12-byte repcode arrays in 28-byte table
entries. Clang widens their copies to an 8-byte access on ARM64, leaving every
other entry under-aligned for Fil-C. The ARM-specific patch aligns that member
to 8 bytes and pads each entry to 32 bytes; the compression algorithm is
unchanged, at a cost of about 16 KiB per optimal-parser table.

The same 8-byte chunking applies when Zstandard passes its 12-byte frame
parameters by value. `ZSTD_parameters` normally places that member at offset
28, so the ARM patch aligns it and grows the parameter structure from 40 to 48
bytes under Fil-C. Dictionary training exercises this path in the upstream
suite.

FastCover and the legacy dictionary builder likewise nest a 12-byte parameter
block at offsets 44 and 4. Those members are aligned under Fil-C on ARM64,
growing the structures from 56 to 64 bytes and 16 to 24 bytes respectively.
The regular COVER layout already has the required alignment.

The legacy dictionary builder also keeps 12-byte items in a table and passes
them by value. Its ARM patch gives those items 8-byte alignment, changing the
table stride from 12 to 16 bytes so the ABI's widened copies remain aligned.

Long-distance matching uses another internal table of 12-byte raw sequences.
Those entries receive the same ARM-only alignment and 16-byte stride because
the matcher reads them by value.

nano is the second utility with dependencies, and like curl it builds them with
the same compiler into a shared `/deps` prefix: ncurses for the terminal and
libmagic, from the `file` project, for content-based syntax detection. Both are
on Fil-C's list of programs that build unchanged, and neither needed a patch.
ncurses is built widec, for UTF-8, and split with `--with-termlib` so the
terminfo half is its own library. The setting that matters is
`--with-fallbacks`: it compiles a set of common terminal descriptions
(`xterm`, `linux`, `vt100`, `screen`, `tmux` and others) into the library. A
scratch image carries no terminfo database, so without them nano could not
drive any terminal at all, and the smoke test enforces this by running with the
terminfo path pointed at nothing. libmagic is configured with
`--datadir=/usr/share` so the database path compiled into it is the platform
standard `/usr/share/misc/magic`, the same host-path approach curl uses for its
CA bundle. Every one of nano's features is on by default, so no feature flags
are needed beyond `--enable-utf8`; the build asserts `ENABLE_UTF8` and
`HAVE_LIBMAGIC` in `config.h` rather than trusting configure to have found the
library. Only nano's `lib` and `src` directories are built, which skips the
documentation step and its `makeinfo` requirement.

tmux reuses that same ncurses recipe and adds libevent for its event loop and
utf8proc for character widths. All three build unchanged. Two things about it
are specific. It is the only utility here whose terminal descriptions have to
cover both directions: tmux needs an entry for the terminal it runs inside and
another for the one it presents to programs in its panes, which is why `screen`
and `tmux` appear in the fallback list next to the outer terminals. And
utf8proc's Makefile has no static-only install target, so its archive, header
and pkg-config file are placed by hand; `make install` would insist on building
the shared library too. The upstream reference build, `build_tmux.sh` in the
Fil-C tree, is dynamic and installs into a prefix that already holds ncurses
and libevent, so the static link and the terminfo question are this build's own
work rather than something inherited from it.

OpenSSH locks Fil-C's collector and allocator threads before installing its
preauthentication seccomp filter, then allows the runtime's `sched_yield` and
`MAP_NORESERVE` use. Violations kill the whole process because leaving other
runtime-managed threads alive is unsafe. Its second patch routes process-title
updates through `zsetproctitle`; Fil-C owns the original `argv` storage, so
OpenSSH's usual overwrite-in-place implementation is unavailable. The Fil-C
0.684 aarch64 release also leaves its kernel-UAPI `asm` include symlink dangling
on Debian multiarch systems; the build retargets it to the architecture-specific
directory and compiles a seccomp/tun header probe before building dependencies.
Finally, Fil-C 0.684 misclassifies a byte-aligned libcrux aggregate in the
aarch64 calling convention. A Fil-C/AArch64-only alignment attribute works
around that compiler bug without disabling OpenSSH's ML-DSA or ML-KEM support;
a static layout assertion and native cryptographic tests guard the workaround.
The generated sntrup761 cryptoint code has a separate AArch64 assembly path
that Fil-C 0.684 cannot lower. A fourth patch selects cryptoint's portable C
fallbacks only on Fil-C/AArch64; sntrup761x25519 remains enabled, while x86-64
and non-Fil-C AArch64 builds retain their assembly paths.

### Updating a dependency

Run `python3 check-versions.py` to see which pins are behind; the `versions`
workflow runs the same check when a pull request is opened and comments if any
are.

1. Change the version and checksum arguments near the top of its Dockerfile.
2. Download the release from the authoritative upstream location and calculate
   its SHA-256 checksum.
3. Update the checksum in the pinned-input table above.
4. Confirm its `check-versions.py` registration and release-series policy;
   add an entry for a newly maintained source.
5. Refresh compatibility patches against a pristine copy of the new release.
6. Run a no-cache Docker build for the changed utility, then rebuild the
   complete output before running the robustness suite.

For example:

```sh
rm -rf "$HOME/filc-zstd-amd64"
docker build --no-cache \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest="$HOME/filc-zstd-amd64" \
  ./zstd

PLATFORM=linux/amd64 ./build-all.sh
./tests/run-tests.sh --iters 24
```

Remove or choose a fresh local-export destination before each individual
build: Docker merges into an existing destination. Repeat the build and suite
with `PLATFORM=linux/arm64` when native ARM hardware is available. In all cases,
the pull-request workflow's native x86_64 and AArch64 matrices are the
authoritative dual-architecture gate.

Run `./build-all.sh` before the suite, not after. `out/` is a build product,
and an individual `docker build --output` merges into whatever is already
there, so a stale executable can survive an upgrade and be tested in place of
the one the Dockerfile now describes. `build-all.sh` avoids that by staging all
utilities and replacing `out/` only after every build succeeds. The alignment
stage cannot reliably identify stale shipped binaries because they contain no
DWARF.

Do not weaken a checksum, static-link assertion, Fil-C symbol assertion,
compiler-trap check, expected test count, or functional test merely to make an
upgrade pass. Do not silently disable a feature or allow a suite to skip its
coverage. Document new compatibility flags, deliberate skips, disabled
features, or patches here with the Fil-C limitation they address.

### Adding a utility

A new utility gets one subdirectory and one Dockerfile. Its source and every
statically linked dependency must come from authoritative, version-pinned
releases whose SHA-256 checksums are verified before extraction. Reuse the
existing `TARGETARCH` mapping and checksum-pinned Fil-C Pizfix/musl toolchains
for both architectures.

Compile every shipped native translation unit and dependency with Fil-C and
link each executable as a static PIE with no interpreter. Audit all native
helpers as well as `bin/`: require DWARF before stripping, Fil-C transformed and
runtime symbols, and no `@llvm.` or `cannot handle inline asm` trap marker. Use
`strip --strip-debug`, retain `.symtab`, then repeat the static-link and
provenance checks against the staged copies.

Run the official upstream suite against the Fil-C build whenever one exists.
Keep the same compiler and link flags if it rebuilds programs, arrange the
fixtures needed to prevent silent skips, and assert a test-count floor or exact
intentional skip set. Run a meaningful functional workflow and every exported
command or invocation-name alias against the stripped artifact. Export the
utility, dependency, and Fil-C licenses, preserve required helper/data paths,
exclude build-host secrets, and finish with a `scratch` artifact stage.

Add the directory name to `UTILITIES` and every exported executable or alias to
`EXECUTABLES` in `build-all.sh`. Extend the user-facing command table, output
tree, pins, limitations, compatibility notes, and license list in this README.
Add maintained release pins to `check-versions.py`; only explicit `COMPONENTS`
entries receive freshness reports.

CI needs no change for a new utility. It builds the utilities in parallel
rather than calling `build-all.sh`, but it reads both lists from the script
through `./build-all.sh --list utilities` and `--list executables`, so
`build-all.sh` stays the only place either list is written down.

Teach `tests/` about the new format: add archives to `make-corpus.sh`, a test
command and decode action to `roundtrip.py` and `fuzz.py`, and hostile members
to `make-hostile.py` if the format carries stored paths or links. A format the
suite does not recognise is silently skipped rather than reported.

If the utility dispatches on content rather than on the command line, as 7-Zip
does, give the fuzzer a way to name the handler explicitly. Autodetection alone
means a mutation that touches the magic bytes never reaches the code being
tested, which quietly wastes most of a run.

Patches should be minimal, conditional on `__FILC__` or an upstream feature
flag where possible, and should replace unsupported low-level operations with
portable code or Fil-C APIs rather than broadly disabling instrumentation. When
a patch's effect is invisible to the existing build checks, as unRAR's
alignment patch is, add an assertion that fails the build without it.
