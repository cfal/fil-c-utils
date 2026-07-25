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

Fil-C turns spatial and temporal memory-safety violations into deterministic
process failures. That is useful defense in depth for programs that process
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

The script stages all seven builds and replaces `out/` only after every build
has succeeded. Binaries are flat; only license notices use subdirectories:

```text
out/
├── 7z
├── 7zz -> 7z
├── bunzip2 -> bzip2
├── bzcat -> bzip2
├── bzip2
├── bzip2recover
├── gunzip -> gzip
├── gzip
├── lzcat -> xz
├── lzma -> xz
├── tar
├── unrar
├── unlzma -> xz
├── unxz -> xz
├── unzstd -> zstd
├── xz
├── xzcat -> xz
├── zcat -> gzip
├── zstd
├── zstdcat -> zstd
└── licenses/
    ├── 7zip/
    ├── bzip2/
    ├── fil-c/
    ├── gzip/
    ├── tar/
    ├── unrar/
    ├── xz/
    └── zstd/
```

The executables are x86-64 static PIEs and have no ELF program interpreter.
They can run directly from `out/`:

```sh
./out/7z t archive.7z
./out/unrar t archive.rar
./out/tar -tf archive.tar
./out/gzip -dc file.gz
./out/bzip2 -dc file.bz2
./out/xz -dc file.xz
./out/zstd -dc file.zst
```

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
PATH="$PWD/out:$PATH" ./out/tar -czf source.tar.gz source/
PATH="$PWD/out:$PATH" ./out/tar -cjf source.tar.bz2 source/
PATH="$PWD/out:$PATH" ./out/tar -cJf source.tar.xz source/
PATH="$PWD/out:$PATH" ./out/tar --zstd -cf source.tar.zst source/
```

The same rule applies while extracting. The tar Dockerfile deliberately
configures the helper names as `gzip`, `bzip2`, `xz`, and `zstd`, so ordinary
`PATH` lookup is sufficient. You can also select a helper explicitly:

```sh
./out/tar --use-compress-program="$PWD/out/zstd" -xf source.tar.zst
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

Replace `gzip` with `7z`, `unrar`, `tar`, `bzip2`, `xz`, or `zstd`. Docker
merges an individual artifact tree into an existing destination, so old files
may remain. `build-all.sh` avoids that ambiguity by staging every build and
replacing `out/` transactionally.

Each final stage is also a minimal runnable `scratch` image:

```sh
docker build --platform linux/amd64 -t filc-zstd ./zstd
docker run --rm -i filc-zstd -dc < file.zst > file
```

These images have no shell, package manager, dynamic loader, or CA bundle.
They contain the selected utility, command aliases, and license notices.

## Checking an artifact

The Dockerfiles reject an artifact unless it is static, contains debug
information, has Fil-C symbols, and passes a round-trip smoke test. You can
inspect a built binary yourself:

```sh
file out/tar
readelf -lW out/tar | grep INTERP
readelf -sW out/tar | grep -m1 pizlonated
readelf -sW out/tar | grep -Em1 'filc_call_user_main|zgc_alloc'
```

`file` should say `static-pie linked`. The `INTERP` command should print
nothing and exit nonzero. The symbol commands should find Fil-C-transformed
names and a Fil-C runtime symbol. `ldd` alone is not a sufficient provenance
check.

## Robustness testing

The per-utility Dockerfiles run smoke tests against known-good inputs. The
suite in `tests/` goes further: it checks that the binaries in `out/` handle
correct data exactly, refuse hostile data safely, and survive corrupt data
without a memory-safety failure.

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

Fil-C stores a capability beside every pointer slot and requires those slots to
keep their natural alignment. A `#pragma pack(1)` structure that holds a
pointer therefore compiles cleanly, links cleanly, passes a valid-archive test,
and then panics the first time that field is written. This stage reads DWARF
from each executable and reports any pointer-typed member at an offset that is
not a multiple of `sizeof(void *)`, so the defect is caught in the artifact
rather than from a crash report. It is the cheapest stage and the one most
worth running after any dependency upgrade.

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
./out/unrar t -y "${TMPDIR:-/tmp}/fil-c-utils-tests/findings/FILC-unrar-..."
```

`OOM` is reported separately rather than counted as a failure. Under Fil-C an
allocation that cannot be satisfied panics instead of returning `NULL`, so a
run that hits the harness's address-space cap is a resource result, not a
memory-safety result. See the limitation below.

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

Fil-C converts memory-safety violations into deterministic process failures,
which is a crash, not a recovery. A utility that panics on an untrusted archive
is safe but unavailable, so a service that must keep running needs the usual
supervision and per-request isolation regardless.

## Maintainer guide

### Repository layout

```text
.
├── .gitignore
├── README.md
├── build-all.sh
├── 7z/
│   ├── Dockerfile
│   └── patches/
├── bzip2/
│   └── Dockerfile
├── gzip/
│   └── Dockerfile
├── tar/
│   ├── Dockerfile
│   └── patches/
├── unrar/
│   ├── Dockerfile
│   └── patches/
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

Zstandard is built with `ZSTD_NO_ASM=1`. Version 1.5.7 has one pointer-returning
assembly block and several optional alignment blocks that do not honor
`ZSTD_DISABLE_ASM`, so the local patch extends those guards and selects the
existing portable C implementation.

### Updating a dependency

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
