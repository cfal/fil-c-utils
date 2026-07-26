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

Every utility here reads untrusted input: seven of them parse archives, and
curl and wget speak to the network. Fil-C turns spatial and temporal memory-safety
violations into deterministic process failures. That is useful defense in depth for programs that process
untrusted archives. It does not replace sandboxing, least privilege, archive
size limits, path validation, or timely dependency updates.

## Quick start

Requirements:

- Docker with BuildKit support
- An x86-64 Linux host, or an environment capable of building
  `--platform linux/amd64` images
- Network access to the pinned upstream release files and Ubuntu package
  repositories

Build everything:

```sh
./build-all.sh
```

The script stages all nine builds and replaces `out/` only after every build
has succeeded. The tree has two directories, one for executables and one
for license notices:

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
│   ├── gunzip -> gzip
│   ├── gzip
│   ├── lzcat -> xz
│   ├── lzma -> xz
│   ├── tar
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
└── licenses/
    ├── 7zip/
    ├── bzip2/
    ├── c-ares/
    ├── curl/
    ├── fil-c/
    ├── gzip/
    ├── libidn2/
    ├── libpsl/
    ├── libunistring/
    ├── openssl/
    ├── pcre2/
    ├── tar/
    ├── unrar/
    ├── wget/
    ├── xz/
    ├── zlib/
    └── zstd/
```

The executables are x86-64 static PIEs and have no ELF program interpreter.
They can run directly from `out/`:

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
```

curl and wget both verify certificates against
`/etc/ssl/certs/ca-certificates.crt`, the path compiled in at build time, so
they trust whatever the host trusts and keep benefiting from the host's
certificate updates. Point curl elsewhere with `--cacert`, `--capath`, or
`CURL_CA_BUNDLE`, and wget with `--ca-certificate`, `--ca-directory`, or
`SSL_CERT_FILE`. An environment with no bundle at that path, such as a scratch
container or a distribution that keeps certificates elsewhere, has to supply
one.

Set `PLATFORM` to override the Docker platform. The pinned Fil-C release is
currently provided only for `linux/amd64`:

```sh
PLATFORM=linux/amd64 ./build-all.sh
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

Replace `gzip` with `7z`, `unrar`, `tar`, `bzip2`, `xz`, `zstd`, `curl`, or `wget`. Docker
merges an individual artifact tree into an existing destination, so old files
may remain. `build-all.sh` avoids that ambiguity by staging every build and
replacing `out/` transactionally.

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
the selected utility, command aliases, and license notices. The curl image has
no CA bundle either, so HTTPS needs one supplied:

```sh
docker run --rm -v /etc/ssl/certs/ca-certificates.crt:/ca.pem:ro \
    filc-curl --cacert /ca.pem https://example.com/
```

## Checking an artifact

The Dockerfiles reject an artifact unless it is static, has Fil-C symbols, and
passes the project's tests. You can inspect a built binary yourself:

```sh
file out/bin/tar
readelf -lW out/bin/tar | grep INTERP
readelf -sW out/bin/tar | grep -m1 pizlonated
readelf -sW out/bin/tar | grep -Em1 'filc_call_user_main|zgc_alloc'
```

`file` should say `static-pie linked`. The `INTERP` command should print
nothing and exit nonzero. The symbol commands should find Fil-C-transformed
names and a Fil-C runtime symbol. `ldd` alone is not a sufficient provenance
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
against `out/`; it reports that it could not scan rather than passing.

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
| gzip | 30 cases | 29 pass, 1 skip |
| XZ Utils | 18 cases | 18 pass |
| Zstandard | `playTests.sh` and fuzzers | all pass |
| bzip2 | 3 sample round trips | pass |
| 7-Zip | **none ships** | — |
| unRAR | **none ships** | — |

Nothing needed to be excluded or marked expected-to-fail: Fil-C causes no
failures in any of them. Skipped cases are features these builds do not enable,
such as HTTP/2 and IDN for curl, or tests needing root for tar. Wget's two
skips are one web-of-trust HTTPS case and one proxy-environment test.

Three details are easy to get wrong. curl's suite silently skips its 62 HTTPS
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
| `alignment` | No binary places a pointer field at an unaligned offset |
| `corpus` | Builds ~345 valid archives and 27 hostile ones |
| `roundtrip` | Patched code paths run, valid archives restore byte for byte, host tools agree |
| `safety` | No hostile archive writes outside the extraction directory |
| `fuzz` | Mutated archives produce ordinary errors, never a Fil-C panic |

Building the 7-Zip format corpus uses Docker. Without it that part is skipped
and the run says so; every other stage works from Python 3 alone.

### The alignment stage

Two defects share an awkward shape: they compile cleanly, link cleanly, pass
every functional test, and then abort at run time on a machine or an input that
happens to reach them. This stage finds both by reading the binary, so neither
needs the trigger to be reproduced.

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

Both checks are also asserted in every utility's Dockerfile, so a build that
introduces either fails immediately rather than shipping. This is the cheapest
stage and the one most worth running after any dependency upgrade.

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
| Fil-C | 0.681 | `84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787` |
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
- Debug information is retained intentionally, so binaries are significantly
  larger than conventional stripped distribution builds.
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
├── gzip/
│   └── Dockerfile
├── tar/
│   ├── Dockerfile
│   └── patches/
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
then a release for tags only. Each stage depends on the one before it, so a
failing suite means no `fil-c-utils-<version>-x86_64.tar.gz` is published and
no release is drafted. `build.yml` holds the compile matrix and exists only to
be called from `ci.yml`; the utilities build independently, so running them in
parallel makes CI take the time of the slowest one rather than the sum of them
all.

### Cutting a release

Push a tag beginning with `v`:

```sh
git tag v1.0.0
git push origin v1.0.0
```

That runs the whole pipeline against the tag and, if every stage passes, drafts
a GitHub release holding `fil-c-utils-v1.0.0-x86_64.tar.gz` and its `.sha256`.
The release is a **draft**, so it is reviewed before anyone can download it.
Tagged builds take their version from the tag; every other build is named for
the short commit hash.

The release job is the only one granted `contents: write`, and it hangs off the
bundle, which hangs off the test suite. A tag cannot produce a release whose
binaries failed the suite. It re-verifies the checksum after downloading the
artifact rather than trusting the round trip through artifact storage.

### Version freshness

`versions.yml` runs when a pull request is opened and checks every pinned
upstream version against its latest release. If any pin is behind, it posts the
report as a comment on the pull request. It never fails the workflow: a
dependency falling behind is worth putting in front of a reviewer, but it is
not a reason to block a change that touches none of it. When every pin is
current it stays silent.

It runs `check-versions.py`, which reads each pin from its Dockerfile, asks each
upstream for its newest release, and prints one row per component:

```text
component  pinned     latest     status
7z         26.02      26.02      ok
...
curl       8.19.0     8.21.0     OUTDATED
```

Every upstream has a different release source, so the sources are queried
differently: GitHub releases for 7-Zip, XZ, Zstandard, curl, and OpenSSL; the
GNU FTP listing for tar and gzip; sourceware for bzip2; rarlab for unRAR; and
zlib.net for zlib. The curl build's bundled OpenSSL and zlib are checked too.

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
"latest" here means the highest version overall; a pin deliberately tracking an
older branch will read as `OUTDATED`. Fil-C itself is not checked: it is the
toolchain rather than a utility, and moving it is a larger decision than a pin
bump. A pull request opened from a fork gets a read-only token and cannot be
commented on; the check still runs and prints its report to the workflow log.

### Build design

The builders use Fil-C's Pizfix/musl release rather than the glibc-oriented
host installation. Pizfix includes the static libc, C++ library, and Fil-C
runtime archives needed for standalone executables.

Debug information is retained because Fil-C safety failures produce much more
useful diagnostics with symbols. Before export, every native executable is
checked for:

- `static-pie linked` in `file` output
- no ELF `INTERP` program header
- a DWARF `.debug_info` section
- `pizlonated` transformed symbols
- a Fil-C runtime symbol such as `filc_call_user_main` or `zgc_alloc`
- successful startup and a real compression or archive round trip

The `scratch` artifact stage is both the local-export tree and the final image.
It ensures an accidentally dynamic binary cannot appear to work merely because
the builder's loader or libraries are available.

### Compatibility details

7-Zip's x86 feature detection normally uses inline CPUID and XGETBV assembly.
Its patch substitutes Fil-C's supported intrinsic interfaces. The build also
defines `Z7_NO_LARGE_PAGES`; 7-Zip's 2 MiB alignment request exceeds Fil-C's
supported allocation alignment.

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

unRAR normally enables packed structures and misaligned integer access on
x86-64. Fil-C requires pointer slots to retain their natural alignment, so the
unRAR patch selects the existing alignment-safe code paths under Fil-C. Tests
use the checksum-pinned `markokr/rarfile` fixture corpus at commit
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
at a multiple of `alignof(void *)`. The `alignment` stage in `tests/` re-checks
the same property from the shipped binary's DWARF, which also catches an `out/`
tree left over from an earlier build.

GNU tar's bundled obstack implementation normally aligns pointers relative to
address zero. The tar patch uses the obstack allocation as the alignment base
under Fil-C, preserving pointer provenance for help generation, transforms,
incremental archives, and other obstack consumers.

gzip defines `GNU_STANDARD=0` so its documented `gunzip` and `zcat` invocation
names select decompression mode. The Dockerfile tests both aliases rather than
assuming that creating the links is sufficient.

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

### Updating a dependency

Run `python3 check-versions.py` to see which pins are behind; the `versions`
workflow runs the same check when a pull request is opened and comments if any
are.

1. Change the version and checksum arguments near the top of its Dockerfile.
2. Download the release from the authoritative upstream location and calculate
   its SHA-256 checksum.
3. Update the checksum in the pinned-input table above.
4. Rebase compatibility patches onto the pristine new release.
5. Run a no-cache Docker build for the changed utility.
6. Run `./build-all.sh`, then `./tests/run-tests.sh`.

For example:

```sh
docker build --no-cache \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest=/tmp/filc-zstd \
  ./zstd

./build-all.sh
./tests/run-tests.sh --iters 24
```

Run `./build-all.sh` before the suite, not after. `out/` is a build product,
and an individual `docker build --output` merges into whatever is already
there, so a stale executable can survive an upgrade and be tested in place of
the one the Dockerfile now describes. The `alignment` stage catches the specific
case where a stale binary predates a Fil-C patch, but it cannot catch every
kind of drift.

Do not weaken a checksum, static-link assertion, Fil-C symbol assertion, or
functional test merely to make an upgrade pass. Document new compatibility
flags or patches here with the Fil-C limitation they address.

### Adding a utility

A new utility gets one subdirectory and one Dockerfile. Its source must come
from an authoritative, checksum-pinned release. Compile every native
translation unit with Fil-C, link statically, preserve debug information, run
a meaningful functional test, export all applicable licenses, and use a
`scratch` artifact stage.

Add the directory name to `UTILITIES` and every exported executable or alias to
`EXECUTABLES` in `build-all.sh`. Extend the user-facing command table, output
tree, pins, limitations, and compatibility notes in this README.

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
