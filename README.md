# fil-c-utils

`fil-c-utils` produces statically linked, memory-safe builds of common archive
utilities using [Fil-C](https://fil-c.org/). Each utility has an independent,
reproducible Docker build. The resulting Linux executables are exported to the
local `out/` directory; installing Fil-C on the host is not required.

Currently included:

- 7-Zip's full standalone `7z` command
- RARLAB's extraction-only `unrar` command

Fil-C turns spatial and temporal memory-safety violations into deterministic
process failures. It is useful defense in depth for utilities that parse
untrusted archives, but it does not replace container isolation, least
privilege, archive size limits, or normal patch management.

## Quick start

Requirements:

- Docker with BuildKit support
- An x86-64 Linux host, or an environment capable of building
  `--platform linux/amd64` images
- Network access to the pinned upstream release files

Build everything:

```sh
./build-all.sh
```

The script creates:

```text
out/
├── 7z
├── 7zz -> 7z
├── unrar
└── licenses/
    ├── 7zip/
    ├── fil-c/
    └── unrar/
```

Each executable is a static PIE and can run directly from `out/`:

```sh
./out/7z t archive.7z
./out/7z x archive.7z

./out/unrar t archive.rar
./out/unrar x archive.rar
```

Output paths are replaced on every run so stale binaries cannot survive a
successful rebuild. Set `PLATFORM` to override the Docker platform, though the
pinned Fil-C release currently supports only `linux/amd64`:

```sh
PLATFORM=linux/amd64 ./build-all.sh
```

## Building one utility

Docker's local exporter can build either artifact independently:

```sh
docker build \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest=out \
  ./7z

docker build \
  --platform linux/amd64 \
  --target artifact \
  --output type=local,dest=out \
  ./unrar
```

When exporting utilities individually into the same existing directory, Docker
merges their artifact trees. `build-all.sh` stages both builds first and only
replaces `out/` after both have succeeded.

The final Docker stage is also runnable as a minimal `scratch` image:

```sh
docker build --platform linux/amd64 -t filc-7z ./7z
docker run --rm -v "$PWD:/work" -w /work filc-7z t archive.7z

docker build --platform linux/amd64 -t filc-unrar ./unrar
docker run --rm -v "$PWD:/work" -w /work filc-unrar t archive.rar
```

The images contain no shell, package manager, dynamic loader, or CA bundle.
They contain only the utility and its license notices.

## Pinned inputs

Every downloaded input is version-pinned and SHA-256 verified before use.

| Component | Version | SHA-256 |
| --- | --- | --- |
| Fil-C | 0.681 | `84272acf017fe76bddb32bb3865f3d97ce332eb6e6a17fc1c07a8eb9ad777787` |
| 7-Zip source | 26.02 | `cf967c98bca02a4b8b16375f441825a8e141362f14be1969bbec8e1ca0bff9dd` |
| unRAR source | 7.2.7 | `01d903a7dcf413cb2925696d7796e48e38d471f79bfe7ef3ad2aebf6c12dbefd` |

License notices for each utility and the statically linked Fil-C runtime are
exported beside the corresponding binary. 7-Zip includes code under its
documented unRAR restriction. RARLAB's unRAR license prohibits using its source
to recreate the RAR compression algorithm. Review the exported notices before
redistribution.

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
│       └── 0001-use-fil-c-cpu-intrinsics.patch
└── unrar/
    └── Dockerfile
```

Each Dockerfile owns its source pins, toolchain setup, compile flags, static
link checks, functional tests, licenses, and artifact stage. Keep utility
specific work inside that utility's directory.

### Build design

The builders use Fil-C's Pizfix/musl release rather than the glibc-oriented
host installation. The Pizfix package includes static libc, libc++, and Fil-C
runtime archives; the glibc package does not include all archives required for
a fully static executable.

The builds retain debug information intentionally. Fil-C safety failures print
symbolized diagnostics, which are much more useful than stacks from stripped
binaries. The Dockerfiles verify all of the following before exporting:

- The result is reported as a static PIE.
- The ELF has no program interpreter.
- DWARF `.debug_info` is present.
- The utility starts successfully.
- A real archive can be tested and extracted with verified output.

7-Zip receives one compatibility patch. Its x86 feature detection normally
uses inline CPUID and XGETBV assembly, while Fil-C requires its supported
intrinsic interfaces. The build also defines `Z7_NO_LARGE_PAGES` for both C and
C++ translation units. 7-Zip's Linux huge-page optimization requests 2 MiB
alignment, which exceeds Fil-C's supported allocation alignment; ordinary
aligned allocation remains available.

unRAR needs no source changes. Its functional test uses the 542-byte
`rar5-subdirs.rar` fixture from
[`markokr/rarfile`](https://github.com/markokr/rarfile) at commit
`09fd4f216ef502e478f1aeb6f0e193b49056eee8`. The fixture is SHA-256 pinned,
used only in the builder stage, and never exported.

### Updating a dependency

1. Change the version and archive-specific version arguments near the top of
   the relevant Dockerfile.
2. Download the release from the authoritative upstream location and calculate
   its SHA-256 checksum.
3. Update the checksum in the Dockerfile and the pinned-input table above.
4. Rebase compatibility patches onto the new pristine source release.
5. Run `./build-all.sh` without cache when validating a toolchain or source
   upgrade:

```sh
docker build --no-cache --platform linux/amd64 --target artifact ./7z
docker build --no-cache --platform linux/amd64 --target artifact ./unrar
./build-all.sh
```

6. Exercise representative archives beyond the small build-time smoke tests,
   including malformed, encrypted, multi-volume, large, and path-heavy inputs.

Do not silently weaken a checksum, static-link assertion, or functional test to
make an upgrade pass. Document new compatibility flags or patches here with the
Fil-C limitation they address.

### Adding a utility

A new utility should have one subdirectory and one Dockerfile. Its Dockerfile
must use checksum-pinned authoritative source, compile every native translation
unit with Fil-C, link statically, retain debug information, run a meaningful
functional test, and export licenses. Add one `build_utility` call to
`build-all.sh`, extend the user-facing output tree, and document any patches or
unsupported features.

Patches should be minimal, conditional on `__FILC__` where appropriate, and
should replace unsupported low-level operations with Fil-C APIs rather than
disabling safety instrumentation broadly.
