#!/usr/bin/env python3
"""Mutation-fuzz the Fil-C utilities against corrupted archives.

Every run gets one verdict:

  OK       the tool accepted the mutated file (mutations are often benign)
  ERR      the tool rejected it and exited normally -- the desired outcome
  OOM      the allocator gave up; under Fil-C that is a panic, not a NULL
  LIMIT    the harness's own CPU/file-size cap fired
  FILC     Fil-C caught a memory-safety violation -- a latent bug in the tool
  SIGNAL   died some other way
  TIMEOUT  did not finish, so a potential denial of service

FILC, SIGNAL, and TIMEOUT are failures.  Their inputs are saved so they can be
replayed against a rebuilt binary.
"""
import argparse, hashlib, json, os, random, resource, shutil, signal, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FILC_OUT") or ROOT / "out")
WORK = Path(os.environ.get("WORK_DIR") or "/tmp/fil-c-utils-tests")
CORPUS = Path(os.environ.get("CORPUS_DIR") or WORK / "corpus")
FINDINGS = Path(os.environ.get("FINDINGS_DIR") or WORK / "findings")

AS_LIMIT = 8 * 1024**3       # address space; keeps a runaway header honest
FSIZE_LIMIT = 512 * 1024**2  # any single output file
CPU_LIMIT = 25               # seconds of CPU
WALL_TIMEOUT = 30            # seconds of wall clock

OOM_MARKERS = ("filc safety error: out of memory",)
FILC_MARKERS = ("filc safety error", "filc panic", "filc internal error")

STRATEGIES = ["bitflip", "byteset", "truncate", "chophead", "insert", "zerorun",
              "dupchunk", "swapchunk", "headermax", "bigfields", "asciidigits"]
FAILING = ("FILC", "SIGNAL", "TIMEOUT", "SPAWNFAIL")
VERDICTS = ("OK", "ERR", "OOM", "LIMIT", "FILC", "SIGNAL", "TIMEOUT")


def _load_7z_manifest():
    """archive name -> the 7-Zip handler it was built for."""
    path = CORPUS / "7z-manifest.tsv"
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "\t" in line:
                name, handler = line.split("\t", 1)
                out[name.strip()] = handler.strip()
    return out


def _load_7z_handlers():
    path = CORPUS / "7z-handlers.txt"
    return [h for h in path.read_text().split()] if path.exists() else []


SEVENZ_TYPES = _load_7z_manifest()
SEVENZ_HANDLERS = _load_7z_handlers()


def _limits():
    resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT, AS_LIMIT))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_LIMIT, FSIZE_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setsid()


def run(argv, cwd, stdin_path=None):
    env = {"PATH": f"{OUT}:/usr/bin:/bin", "LC_ALL": "C", "HOME": str(WORK / "home")}
    stdin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdin=stdin,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             preexec_fn=_limits, env=env)
    except OSError as e:
        return {"verdict": "SPAWNFAIL", "rc": None, "err": str(e)}
    finally:
        if stdin_path:
            stdin.close()

    try:
        _, err = p.communicate(timeout=WALL_TIMEOUT)
        timed_out = False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        _, err = p.communicate()
        timed_out = True

    err = (err or b"").decode("utf-8", "replace")
    low = err.lower()
    rc = p.returncode

    if any(m in low for m in OOM_MARKERS):
        verdict = "OOM"
    elif any(m in low for m in FILC_MARKERS):
        verdict = "FILC"
    elif timed_out:
        verdict = "TIMEOUT"
    elif rc == 0:
        verdict = "OK"
    elif rc < 0 or rc >= 128:
        sig = -rc if rc < 0 else rc - 128
        verdict = "LIMIT" if sig in (signal.SIGXFSZ, signal.SIGXCPU, signal.SIGKILL) \
            else "SIGNAL"
    else:
        verdict = "ERR"
    return {"verdict": verdict, "rc": rc, "err": err[-3000:]}


def mutate(data, rng, strategy):
    b = bytearray(data)
    n = len(b)
    if n == 0:
        return bytes(b)
    if strategy == "bitflip":
        for _ in range(rng.randint(1, 8)):
            b[rng.randrange(n)] ^= 1 << rng.randrange(8)
    elif strategy == "byteset":
        for _ in range(rng.randint(1, 8)):
            b[rng.randrange(n)] = rng.randrange(256)
    elif strategy == "truncate":
        b = b[: rng.randrange(n)]
    elif strategy == "chophead":
        b = b[rng.randrange(1, min(n, 64) + 1):]
    elif strategy == "insert":
        i = rng.randrange(n + 1)
        b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 64)))
    elif strategy == "zerorun":
        i = rng.randrange(n)
        b[i: i + rng.randint(1, 512)] = b"\x00" * min(rng.randint(1, 512), n - i)
    elif strategy == "dupchunk":
        i = rng.randrange(n)
        ln = rng.randint(1, max(1, min(4096, n - i)))
        b[i:i] = b[i: i + ln]
    elif strategy == "swapchunk" and n > 32:
        ln = rng.randint(1, min(1024, n // 2))
        i, j = rng.randrange(n - ln), rng.randrange(n - ln)
        b[i:i+ln], b[j:j+ln] = b[j:j+ln], b[i:i+ln]
    elif strategy == "headermax":
        for _ in range(rng.randint(1, 6)):
            b[rng.randrange(min(n, 64))] = 0xFF
    elif strategy == "bigfields":
        # Plant absurd little-endian sizes and counts where headers keep them.
        val = rng.choice([b"\xff\xff\xff\xff", b"\xff\xff\xff\x7f", b"\x00\x00\x00\x80",
                          b"\xff" * 8, b"\xff\xff\xff\xff\xff\xff\xff\x7f"])
        i = rng.randrange(max(1, min(n, 1024) - len(val)))
        b[i: i + len(val)] = val
    elif strategy == "asciidigits":
        # tar's numeric fields are octal ASCII; make them enormous.
        i = rng.randrange(max(1, n - 12))
        b[i: i + 12] = b"77777777777 "
    return bytes(b)


def actions_for(name, rng=None):
    """[(tool, argv template, stdin?)] for an archive name; {f} is its path.

    Reading from a pipe is a separate code path from reading a file: the
    decoder cannot seek, so it takes different branches for headers, indexes,
    and trailers.  Both are covered where the tool supports stdin.
    """
    acts = []

    # 7-Zip picks a handler from the file's magic bytes, so a mutation that
    # lands on those bytes stops at dispatch and never enters the handler under
    # test.  For anything with a known handler, force it with -t as well, and
    # push the same bytes through an unrelated handler: that is the only way
    # the formats with no Linux writer ever see structured input.
    handler = SEVENZ_TYPES.get(name)
    if handler:
        acts.append(("7z-fmt", ["7z", "l", "-y", "-slt", "-ppassword",
                                f"-t{handler}", "{f}"], False))
        acts.append(("7z-fmt", ["7z", "t", "-y", "-ppassword",
                                f"-t{handler}", "{f}"], False))
        acts.append(("7z-fmt", ["7z", "x", "-y", "-ppassword", "-o.",
                                f"-t{handler}", "{f}"], False))
        if SEVENZ_HANDLERS and rng is not None:
            for other in rng.sample(SEVENZ_HANDLERS, min(2, len(SEVENZ_HANDLERS))):
                acts.append(("7z-cross", ["7z", "t", "-y", "-ppassword",
                                          f"-t{other}", "{f}"], False))

    def add(tool, *argv):
        acts.append((tool, list(argv), False))

    def pipe(tool, *argv):
        acts.append((tool + "|", list(argv), True))

    if name.endswith((".tar.gz", ".tgz")):
        add("tar", "tar", "-tzvf", "{f}"); add("tar", "tar", "-xzf", "{f}")
        pipe("tar", "tar", "-tzvf", "-")
    elif name.endswith(".tar.bz2"):
        add("tar", "tar", "-tjvf", "{f}"); add("tar", "tar", "-xjf", "{f}")
        pipe("tar", "tar", "-tjvf", "-")
    elif name.endswith(".tar.xz"):
        add("tar", "tar", "-tJvf", "{f}"); add("tar", "tar", "-xJf", "{f}")
        pipe("tar", "tar", "-tJvf", "-")
    elif name.endswith(".tar.zst"):
        add("tar", "tar", "--zstd", "-tvf", "{f}"); add("tar", "tar", "--zstd", "-xf", "{f}")
        pipe("tar", "tar", "--zstd", "-tvf", "-")
    elif name.endswith(".tar"):
        add("tar", "tar", "-tvf", "{f}"); add("tar", "tar", "-xf", "{f}")
        pipe("tar", "tar", "-tvf", "-")
    elif name.endswith(".gz"):
        add("gzip", "gzip", "-tv", "{f}"); add("gzip", "gzip", "-dc", "{f}")
        add("gzip", "gzip", "-lv", "{f}")
        pipe("gzip", "gzip", "-dc")
    elif name.endswith(".bz2"):
        add("bzip2", "bzip2", "-tvv", "{f}"); add("bzip2", "bzip2", "-dc", "{f}")
        add("bzip2", "bzip2recover", "{f}")
        pipe("bzip2", "bzip2", "-dc")
    elif name.endswith((".xz", ".lzma")):
        add("xz", "xz", "-tvv", "{f}"); add("xz", "xz", "-dc", "{f}")
        add("xz", "xz", "-lvv", "{f}")
        add("xz", "xz", "-T4", "-tvv", "{f}")   # threaded decoder is separate code
        pipe("xz", "xz", "-dc")
    elif name.endswith(".zst"):
        add("zstd", "zstd", "-t", "{f}"); add("zstd", "zstd", "-dc", "{f}")
        add("zstd", "zstd", "-lv", "{f}")
        pipe("zstd", "zstd", "-dc")
    elif name.endswith((".7z", ".zip")):
        add("7z", "7z", "l", "-y", "-ppassword", "{f}")
        add("7z", "7z", "t", "-y", "-ppassword", "{f}")
        add("7z", "7z", "x", "-y", "-ppassword", "-o.", "{f}")
    elif name.endswith(".rar"):
        add("unrar", "unrar", "l", "-y", "-ppassword", "{f}")
        add("unrar", "unrar", "t", "-y", "-ppassword", "{f}")
        add("unrar", "unrar", "x", "-y", "-ppassword", "{f}", "./")

    # 7-Zip sniffs the container itself, so give it a shot at every format.
    if not name.endswith((".7z", ".zip")):
        acts.append(("7z-sniff", ["7z", "t", "-y", "-ppassword", "{f}"], False))
    return acts


def one_case(job):
    seed_name, strategy, iteration, master = job
    data = (CORPUS / seed_name).read_bytes()
    rng = random.Random(f"{master}:{seed_name}:{strategy}:{iteration}")
    mutated = mutate(data, rng, strategy)

    results = []
    with tempfile.TemporaryDirectory(prefix="fz-", dir=str(WORK / "work")) as td:
        tdp = Path(td)
        target = tdp / seed_name          # keep the extension: tools dispatch on it
        target.write_bytes(mutated)
        # Multi-volume sets (.rNN, .00N) only open through their first volume,
        # so the rest of the chain has to travel with it, unmutated.
        stem = seed_name.rsplit(".", 1)[0]
        for sibling in CORPUS.iterdir():
            if sibling.name != seed_name and sibling.name.startswith(stem + "."):
                shutil.copy(sibling, tdp / sibling.name)

        for tool, tmpl, use_stdin in actions_for(seed_name, rng):
            wd = tdp / f"x{len(results)}"
            wd.mkdir()
            argv = [a.replace("{f}", str(target)) for a in tmpl]
            argv[0] = str(OUT / argv[0])
            r = run(argv, cwd=str(wd), stdin_path=str(target) if use_stdin else None)
            r.update(seed=seed_name, strategy=strategy, iter=iteration, tool=tool,
                     cmd=" ".join(tmpl) + (" < archive" if use_stdin else ""))
            if r["verdict"] in FAILING:
                digest = hashlib.sha256(mutated).hexdigest()[:16]
                repro = FINDINGS / f"{r['verdict']}-{tool}-{strategy}-{digest}-{seed_name}"
                repro.parent.mkdir(parents=True, exist_ok=True)
                repro.write_bytes(mutated)
                r["repro"] = str(repro)
            else:
                r.pop("err", None)
            results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=6,
                    help="mutations per corpus archive per strategy")
    ap.add_argument("--seed", default="0", help="master seed; changes the whole run")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--filter", default="", help="substring filter on archive names")
    ap.add_argument("--out", default=None, help="JSONL log path")
    a = ap.parse_args()

    for d in (WORK / "work", WORK / "home", FINDINGS):
        d.mkdir(parents=True, exist_ok=True)
    log_path = Path(a.out) if a.out else WORK / "fuzz.jsonl"

    if not CORPUS.is_dir():
        print(f"no corpus at {CORPUS}; run make-corpus.sh first", file=sys.stderr)
        return 2
    metadata = {"7z-manifest.tsv", "7z-handlers.txt"}
    seeds = sorted(p.name for p in CORPUS.iterdir()
                   if p.is_file() and p.name not in metadata and a.filter in p.name)
    if not seeds:
        print(f"no corpus archives matched {a.filter!r}", file=sys.stderr)
        return 2

    jobs = [(s, st, i, a.seed) for s in seeds for st in STRATEGIES for i in range(a.iters)]
    random.Random(a.seed).shuffle(jobs)
    print(f"fuzz: {len(seeds)} archives x {len(STRATEGIES)} strategies x {a.iters} "
          f"= {len(jobs)} mutations", flush=True)

    tally, runs, done = {}, 0, 0
    with open(log_path, "w") as fh, ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for fut in as_completed([ex.submit(one_case, j) for j in jobs]):
            done += 1
            for r in fut.result():
                runs += 1
                tally[(r["tool"], r["verdict"])] = tally.get((r["tool"], r["verdict"]), 0) + 1
                fh.write(json.dumps(r) + "\n")
            if done % 500 == 0:
                bad = sum(v for (_, vd), v in tally.items() if vd in FAILING)
                print(f"  {done}/{len(jobs)} mutations, {runs} runs, {bad} failures",
                      flush=True)
                fh.flush()

    print(f"\n{runs} runs over {len(jobs)} mutated archives")
    head = " ".join(f"{v:>8}" for v in VERDICTS)
    print(f"{'tool':<10}{head}")
    for tool in sorted({t for t, _ in tally}):
        row = " ".join(f"{tally.get((tool, v), 0):>8}" for v in VERDICTS)
        print(f"{tool:<10}{row}")

    bad = sum(v for (_, vd), v in tally.items() if vd in FAILING)
    oom = sum(v for (_, vd), v in tally.items() if vd == "OOM")
    if oom:
        print(f"\n{oom} runs hit the {AS_LIMIT // 1024**3} GiB address-space cap "
              f"(reported as an allocator panic, not a safety violation)")
    if bad:
        print(f"\nFAIL: {bad} memory-safety failures; reproducers in {FINDINGS}")
        return 1
    print("\nPASS: no memory-safety failures, signals, or hangs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
