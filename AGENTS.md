# Repository guidelines

Statically linked, memory-safe CLI utilities built with [Fil-C](https://fil-c.org/).
Each utility owns one self-contained Dockerfile; nothing is installed on the
host.

## Layout and ownership

- `<utility>/Dockerfile` owns that utility's source and dependency pins,
  toolchain setup, flags, assertions, upstream tests, functional tests,
  licenses, and artifact layout.
- `<utility>/patches/` contains minimal compatibility patches, conditional on
  `__FILC__` or an upstream feature flag where possible.
- `build-all.sh` owns the utility and exported-command lists
  (`./build-all.sh --list utilities|executables`); CI reads both from it.
- `tests/` is the cross-utility robustness suite (`./tests/run-tests.sh`).
- `check-versions.py` checks the upstream pins explicitly registered in its
  `COMPONENTS` table. It is not automatic discovery, and Fil-C is deliberately
  excluded.
- The README maintainer guide documents build design, compatibility decisions,
  disabled features, runtime limitations, and release behavior. Keep it in sync
  with implementation changes rather than duplicating detailed history here.

## Architecture and toolchain

- Support both `linux/amd64` and `linux/arm64`. A change is not complete until
  native x86_64 and AArch64 CI builds and tests pass.
- Use Fil-C's checksum-pinned Pizfix/musl release, which supplies the static
  libc, C++ library, and runtime. Do not substitute the glibc-oriented host
  installation.
- Preserve the existing architecture mapping: Docker reports `amd64` and
  `arm64`, while Fil-C release assets use `x86_64` and `aarch64`. Keep a
  SHA-256 pin for each asset and reject unknown `TARGETARCH` values.
- Checksums pin downloaded sources, not the rolling Ubuntu builder image and
  packages. Do not use artifact hash equality as proof of equivalent code.
- CI runs both targets on native GitHub runners because Dockerfiles execute the
  target programs and their upstream suites during the build. Do not mix stage
  artifacts across architectures; artifact names and download patterns must
  retain the architecture.
- Guard target-specific source changes with `__FILC__` and the compiler's
  architecture macro. Do not alter the other architecture's code path unless
  the investigation found a shared defect.

## Dockerfile contract

- Download authoritative, version-pinned releases and verify every SHA-256
  before extraction. Pin statically linked dependencies and fixture sources as
  well as the primary utility.
- Compile every shipped native translation unit and dependency with Fil-C.
  Prevent accidental linkage against host libraries.
- Run the project's official suite against the Fil-C build whenever one ships.
  Pass the same compiler and static-link flags when a suite relinks binaries.
  Install required fixtures and services, assert test-count floors or exact
  skip sets, and fail on unexpected silent skips.
- Do not disable working features or skip failing tests merely to make a build
  pass. Any unavoidable disabled feature or skip needs a technical reason in
  the Dockerfile and README.
- Run a real functional round trip and every exported command, including
  invocation-name aliases. Exercise the staged, stripped artifact copies, not
  only binaries in the build tree.
- Audit every shipped ELF, including helpers under paths such as `libexec`, not
  only `bin/`. Before export, require:
  - the expected ELF machine and `static-pie linked` file type;
  - no ELF `INTERP` program header;
  - DWARF `.debug_info` in the unstripped build;
  - `pizlonated` transformed symbols and a Fil-C runtime symbol such as
    `filc_call_user_main` or `zgc_alloc`;
  - no embedded `@llvm.` unhandled-intrinsic marker;
  - no embedded `cannot handle inline asm` marker.
- Build with `-g`, then use `strip --strip-debug` for shipped copies. Do not
  fully strip `.symtab`: Fil-C provenance must remain independently auditable.
  Re-run static-link and provenance checks after stripping.
- Export all applicable licenses for the utility, its static dependencies, and
  Fil-C. Include required runtime data and helper paths, but never build-host
  secrets.
- Use a `scratch` artifact stage so a dynamic binary cannot appear to work by
  borrowing the builder's loader or libraries.

## Fil-C compatibility work

- Prefer portable upstream code or an existing feature switch over new custom
  implementations. Do not broadly disable Fil-C instrumentation.
- CPU-dispatched SIMD and inline-assembly paths can compile into dormant
  run-time traps that appear only on different hardware or inputs. Static
  marker scans are mandatory even when functional tests pass.
- Fil-C requires pointer fields to retain natural alignment. Packed structures
  and AArch64 ABI-widened copies of small records need focused review. Add a
  compile-time layout assertion when the shared checks cannot prove a patch is
  active.
- Patch application is not proof of effect. When a patch's behavior is
  otherwise invisible, add a focused assertion or test that fails without it.

## Robustness suite

- Rebuild before running `tests/`; an individual Docker local export merges
  into its destination and can leave stale executables behind.
- `out/` contains stripped binaries. Compiler-trap scans still work there, but
  the DWARF-based pointer-alignment scan reports `PARTIAL`. Never describe that
  as a completed structural alignment check; use unstripped build binaries or
  targeted layout assertions.
- For a new archive or container format, add valid corpus generation,
  round-trip and fuzz actions, and hostile path/link cases where applicable. An
  unknown format is silently skipped by the harness.
- Content-dispatched parsers need an explicit handler-selection path in the
  fuzzer. Autodetection alone lets mutations of magic bytes bypass the parser.
- Treat Fil-C panics, signals, and timeouts distinctly. Fil-C makes programs
  memory-safe, not crash-free, resource-safe, or path-safe.

## Registration and documentation

- Register a new utility and every exported command or alias in `build-all.sh`.
- Add maintained release pins to `check-versions.py`; it checks only explicit
  entries. Fil-C upgrades remain a separate compatibility decision.
- Update the README command table, output tree, source-pin table, build and
  runtime limitations, compatibility notes, and licenses.
- Preserve architecture-qualified release bundles and the build -> test ->
  bundle -> release dependency chain.

## Build and check

```sh
PLATFORM=linux/amd64 ./build-all.sh
./tests/run-tests.sh

PLATFORM=linux/arm64 ./build-all.sh
./tests/run-tests.sh

python3 check-versions.py
```

`build-all.sh` defaults to `linux/amd64`. Local emulation can be very slow;
native pull-request CI is the authoritative dual-architecture gate.

## Commits

- Use scoped, imperative subjects: `xz: ...`, `tests: ...`,
  `.github/workflows: ...`.
- Keep commits focused. Do not mix dependency upgrades, compatibility fixes,
  test changes, and documentation when they can stand independently.
- Never weaken a checksum, static-link check, Fil-C provenance check,
  compiler-trap check, assertion, or test to obtain a pass.
