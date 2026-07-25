#!/usr/bin/env python3
"""Verify the valid path: every corpus archive tests clean and restores exactly.

The fuzzer only proves the tools reject garbage safely.  This proves they still
produce and consume correct data across every codec, container, and option the
corpus covers, and that the host's own tools agree about the results.
"""
import hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FILC_OUT") or ROOT / "out")
WORK = Path(os.environ.get("WORK_DIR") or "/tmp/fil-c-utils-tests")
SEED = Path(os.environ.get("SEED_DIR") or WORK / "seed")
CORPUS = Path(os.environ.get("CORPUS_DIR") or WORK / "corpus")
SCRATCH = WORK / "roundtrip"

ENV = {"PATH": f"{OUT}:/usr/bin:/bin", "LC_ALL": "C", "HOME": str(WORK / "home")}
results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    if not ok:
        print(f"  FAIL {name}: {detail}")


def run(argv, cwd=None, stdout=None):
    argv = list(argv)
    if not Path(argv[0]).is_absolute():
        argv[0] = str(OUT / argv[0])
    return subprocess.run(argv, cwd=cwd, stdout=stdout, stderr=subprocess.PIPE,
                          stdin=subprocess.DEVNULL, env=ENV, timeout=600)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def fresh(name):
    d = SCRATCH / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


# --------------------------------------------------------------- test commands
TEST_CMD = {
    ".tar.gz":  ["tar", "-tzf"], ".tar.bz2": ["tar", "-tjf"],
    ".tar.xz":  ["tar", "-tJf"], ".tar.zst": ["tar", "--zstd", "-tf"],
    ".tar": ["tar", "-tf"], ".gz": ["gzip", "-t"], ".bz2": ["bzip2", "-t"],
    ".xz": ["xz", "-t"], ".lzma": ["xz", "-t"], ".zst": ["zstd", "-t"],
    ".7z": ["7z", "t", "-y", "-ppassword", "-bso0", "-bsp0"],
    ".zip": ["7z", "t", "-y", "-ppassword", "-bso0", "-bsp0"],
    ".rar": ["unrar", "t", "-y", "-idq", "-ppassword"],
}


def test_command_for(name):
    for ext in sorted(TEST_CMD, key=len, reverse=True):
        if name.endswith(ext):
            return TEST_CMD[ext]
    return None


VOLUME_PART = re.compile(r".+\.(r\d\d|\d{3})$")
METADATA = {"7z-manifest.tsv", "7z-handlers.txt"}


def load_7z_manifest():
    """archive name -> (handler, opens cleanly) for the 7-Zip format corpus."""
    path = CORPUS / "7z-manifest.tsv"
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                out[parts[0]] = (parts[1], parts[2] == "yes")
    return out


def phase_7z_formats():
    """Every container built for a 7-Zip handler still opens through it.

    This is the coverage check for the format corpus: if a generator drifts and
    stops producing a real container, the fuzzer would keep running against a
    file that no longer reaches the handler it is named after, and would report
    success while testing nothing.
    """
    manifest = load_7z_manifest()
    if not manifest:
        print("7z formats: no format corpus (run make-7z-corpus.sh)")
        return
    reached = sorted({h for h, ok in manifest.values() if ok})
    print(f"7z formats: {len(manifest)} containers reaching {len(reached)} handlers")
    for name, (handler, opens) in sorted(manifest.items()):
        archive = CORPUS / name
        if not archive.exists():
            record(f"7z-format {name}", False, "listed in the manifest but missing")
            continue
        r = run(["7z", "t", "-y", "-ppassword", f"-t{handler}", str(archive)],
                stdout=subprocess.DEVNULL)
        err = r.stderr.decode("utf-8", "replace")
        panic = "filc safety error" in err.lower()
        if opens:
            record(f"7z-format {name} [-t{handler}]", r.returncode == 0 and not panic,
                   f"rc={r.returncode} {err[-160:]}")
        else:
            # Recorded as not openable; it only has to fail like a program.
            record(f"7z-format {name} [-t{handler}]",
                   0 <= r.returncode < 128 and not panic,
                   f"rc={r.returncode} {err[-160:]}")


def phase_verify():
    """Archives this suite built must test clean.

    The pinned markokr/rarfile fixtures are held to a weaker bar: several of
    them are deliberately damaged or use archive features unrar rejects, and a
    stock unrar build returns the same nonzero codes.  For those, the
    requirement is only that the tool fails the way a program should -- an
    ordinary exit status, no signal, and no Fil-C panic.
    """
    print("verify: every corpus archive passes its own integrity test")
    seven_zip = load_7z_manifest()
    for archive in sorted(CORPUS.iterdir()):
        if not archive.is_file() or archive.name in METADATA:
            continue
        if VOLUME_PART.match(archive.name):
            continue    # continuation volumes open through their first part
        if archive.name in seven_zip:
            continue    # covered by phase_7z_formats with an explicit handler
        cmd = test_command_for(archive.name)
        if cmd is None:
            record(f"verify {archive.name}", False, "no test command for this extension")
            continue
        r = run(cmd + [str(archive)], stdout=subprocess.DEVNULL)
        err = r.stderr.decode("utf-8", "replace")
        if archive.name.startswith("rarfile-"):
            ok = 0 <= r.returncode < 128 and "filc safety error" not in err.lower()
            record(f"verify {archive.name}", ok,
                   f"rc={r.returncode} {err[-160:]}")
        else:
            record(f"verify {archive.name}", r.returncode == 0,
                   f"rc={r.returncode} {err[-160:]}")


# ----------------------------------------------------------- single-stream data
STREAM_SOURCES = {
    "repeat": SEED / "text/repeat.txt",
    "random": SEED / "bin/random.bin",
    "empty": None,
}
DECOMP = {".gz": ["gzip", "-dc"], ".bz2": ["bzip2", "-dc"], ".xz": ["xz", "-dc"],
          ".lzma": ["xz", "-dc"], ".zst": ["zstd", "-dqc"]}


def phase_streams():
    print("streams: single-stream compressors restore their input byte for byte")
    for archive in sorted(CORPUS.iterdir()):
        stem = archive.name.split(".")[0]
        ext = "." + archive.name.rsplit(".", 1)[-1]
        if stem not in STREAM_SOURCES or ext not in DECOMP or ".tar" in archive.name:
            continue
        src = STREAM_SOURCES[stem]
        want = sha(src) if src else sha_bytes(b"")
        r = run(DECOMP[ext] + [str(archive)], stdout=subprocess.PIPE)
        if r.returncode != 0:
            record(f"stream {archive.name}", False,
                   f"rc={r.returncode} {r.stderr.decode('utf-8', 'replace')[-160:]}")
            continue
        record(f"stream {archive.name}", sha_bytes(r.stdout) == want,
               f"content differs from {src.name if src else 'empty input'}")

    # Concatenated members must decode to the concatenation of their inputs.
    want = sha_bytes(SEED.joinpath("text/repeat.txt").read_bytes() * 2
                     + SEED.joinpath("bin/random.bin").read_bytes())
    for name, cmd in (("multi.gz", DECOMP[".gz"]), ("multi.bz2", DECOMP[".bz2"]),
                      ("multi.xz", DECOMP[".xz"]), ("multi.zst", DECOMP[".zst"])):
        archive = CORPUS / name
        if not archive.exists():
            continue
        r = run(cmd + [str(archive)], stdout=subprocess.PIPE)
        record(f"multi {name}", r.returncode == 0 and sha_bytes(r.stdout) == want,
               f"rc={r.returncode}, concatenated members did not round-trip")


# ------------------------------------------------------------------ whole trees
def tree_hashes(root):
    """Relative path -> content hash, for regular files only."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[str(p.relative_to(root))] = sha(p)
    return out


TREE_CASES = [
    ("seed.gnu.tar", ["tar", "-xf"]), ("seed.posix.tar", ["tar", "-xf"]),
    ("seed.ustar.tar", ["tar", "-xf"]), ("seed.oldgnu.tar", ["tar", "-xf"]),
    ("seed.tar.gz", ["tar", "-xzf"]), ("seed.tar.bz2", ["tar", "-xjf"]),
    ("seed.tar.xz", ["tar", "-xJf"]), ("seed.tar.zst", ["tar", "--zstd", "-xf"]),
    ("seed.LZMA.7z", None), ("seed.LZMA2.7z", None), ("seed.BZip2.7z", None),
    ("seed.Deflate.7z", None), ("seed.PPMd.7z", None), ("seed.Copy.7z", None),
    ("seed.zip", None),
]


def phase_trees():
    print("trees: archived directory trees extract back to identical content")
    expected = tree_hashes(SEED)
    for name, tar_cmd in TREE_CASES:
        archive = CORPUS / name
        if not archive.exists():
            continue
        dest = fresh("tree-" + name.replace("/", "_"))
        if tar_cmd:
            r = run(tar_cmd + [str(archive), "-C", str(dest)])
        else:
            r = run(["7z", "x", "-y", "-bso0", "-bsp0", f"-o{dest}", str(archive)])
        if r.returncode != 0:
            record(f"tree {name}", False,
                   f"rc={r.returncode} {r.stderr.decode('utf-8', 'replace')[-160:]}")
            continue
        got = tree_hashes(dest)
        # The corpus archives hold a subset of the seed tree, so compare the
        # intersection and require that nothing extracted differs.
        mismatched = [k for k, v in got.items() if expected.get(k) != v]
        record(f"tree {name}", not mismatched and len(got) > 0,
               f"{len(mismatched)} member(s) differ, e.g. {mismatched[:3]}"
               if mismatched else "extracted nothing")


# --------------------------------------------------------------- host interop
HOST = {t: shutil.which(t) for t in ("tar", "gzip", "bzip2", "xz", "unzip")}


def phase_interop():
    print("interop: the host's own tools agree with the Fil-C output")
    checks = [
        ("gzip", ["-t"], "repeat.9.gz"), ("bzip2", ["-t"], "repeat.9.bz2"),
        ("xz", ["-t"], "repeat.9.xz"), ("xz", ["-t"], "repeat.lzma"),
        ("xz", ["-t"], "random.mt.xz"), ("tar", ["-tf"], "seed.gnu.tar"),
        ("tar", ["-tf"], "seed.posix.tar"), ("tar", ["-tzf"], "seed.tar.gz"),
        ("unzip", ["-tqq"], "seed.store.zip"),
    ]
    for tool, args, name in checks:
        path = HOST.get(tool)
        archive = CORPUS / name
        if not path or not archive.exists():
            continue
        r = subprocess.run([path] + args + [str(archive)], capture_output=True,
                           timeout=300, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        # Info-ZIP reserves exit 1 for warnings.  Under LC_ALL=C it warns about
        # the corpus's non-ASCII member names while still validating the data.
        ok = r.returncode == 0 or (tool == "unzip" and r.returncode == 1)
        record(f"interop host {tool} <- {name}", ok,
               f"rc={r.returncode} {r.stderr.decode('utf-8', 'replace')[-160:]}")

    # And the reverse: the Fil-C tools read what the host produced.
    if HOST.get("gzip") and HOST.get("tar"):
        d = fresh("interop-host")
        blob = d / "host.tar.gz"
        subprocess.run([HOST["tar"], "-czf", str(blob), "-C", str(SEED), "text", "names"],
                       check=False, capture_output=True, timeout=300)
        if blob.exists():
            r = run(["tar", "-tzf", str(blob)], stdout=subprocess.DEVNULL)
            record("interop fil-c tar <- host tar.gz", r.returncode == 0,
                   f"rc={r.returncode}")


# ------------------------------------------------------- patched code paths
# Each compatibility patch exists because some construct is unsupported under
# Fil-C.  A patch that silently fails to apply usually still builds and still
# passes an archive round trip, so drive the specific code each one touches.
PATCHED_PATHS = [
    # tar's obstack: help text, argument transforms, exclusion lists, and
    # incremental snapshots are its main consumers.
    ("tar --help", ["tar", "--help"]),
    ("tar --usage", ["tar", "--usage"]),
    ("tar --show-defaults", ["tar", "--show-defaults"]),
    ("tar --transform", ["tar", "--transform=s|a|b|", "-cf", "{s}/tr.tar",
                         "-C", "{s}", "probe.txt"]),
    ("tar --exclude", ["tar", "--exclude=*.o", "--exclude-vcs", "-cf",
                       "{s}/ex.tar", "-C", "{s}", "probe.txt"]),
    ("tar --incremental", ["tar", "-g", "{s}/snar", "-cf", "{s}/inc.tar",
                           "-C", "{s}", "probe.txt"]),
    # 7-Zip's CPUID and XGETBV replacements report through the info command.
    ("7z i", ["7z", "i"]),
]

# gzip needs GNU_STANDARD=0 for these names to select decompression, and the
# rest confirm the exported aliases dispatch as documented.
ALIASES = [("gunzip", ".gz"), ("zcat", ".gz"), ("unxz", ".xz"), ("xzcat", ".xz"),
           ("lzcat", ".lzma"), ("unlzma", ".lzma"), ("unzstd", ".zst"),
           ("zstdcat", ".zst"), ("bunzip2", ".bz2"), ("bzcat", ".bz2")]


def phase_patched_paths():
    print("patches: the code each compatibility patch touches still runs")
    scratch = fresh("patched")
    (scratch / "probe.txt").write_bytes(b"probe\n")

    for name, argv in PATCHED_PATHS:
        r = run([a.replace("{s}", str(scratch)) for a in argv], stdout=subprocess.DEVNULL)
        err = r.stderr.decode("utf-8", "replace")
        record(f"patched {name}", r.returncode == 0 and "filc safety error" not in err.lower(),
               f"rc={r.returncode} {err[-160:]}")

    body = b"alias dispatch\n"
    (scratch / "src.txt").write_bytes(body)
    makers = [("gzip", ".gz", []), ("xz", ".xz", []), ("zstd", ".zst", []),
              ("bzip2", ".bz2", []),
              # lzcat and unlzma select the legacy lzma_alone container, so the
              # probe has to be that format rather than an .xz file renamed.
              ("xz", ".lzma", ["--format=lzma"])]
    for maker, ext, extra in makers:
        blob = scratch / ("src" + ext)
        with open(blob, "wb") as fh:
            run([maker, "-q", "-c"] + extra + [str(scratch / "src.txt")], stdout=fh)

    for alias, ext in ALIASES:
        blob = scratch / ("src" + ext)
        if not blob.exists():
            continue
        args = ["-q", "-c"] if alias in ("unzstd", "zstdcat") else ["-c"]
        r = run([alias] + args + [str(blob)], stdout=subprocess.PIPE)
        record(f"alias {alias}", r.returncode == 0 and r.stdout == body,
               f"rc={r.returncode}, {alias} did not decompress by name")


def main():
    if not CORPUS.is_dir():
        print(f"no corpus at {CORPUS}; run make-corpus.sh first", file=sys.stderr)
        return 2
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (WORK / "home").mkdir(parents=True, exist_ok=True)

    phase_patched_paths()
    phase_7z_formats()
    phase_verify()
    phase_streams()
    phase_trees()
    phase_interop()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results)} checks, {len(failed)} failed")
    if failed:
        print("FAIL")
        return 1
    print("PASS: valid archives round-trip exactly and interoperate with the host")
    return 0


if __name__ == "__main__":
    sys.exit(main())
