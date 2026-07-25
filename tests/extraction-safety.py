#!/usr/bin/env python3
"""Extract hostile archives into a jail and report anything written outside it.

Fil-C stops memory-safety violations; it does nothing about an archive whose
member is named `../../etc/cron.d/root`.  This covers that separate risk for
tar, 7-Zip, and unRAR: relative traversal, absolute paths, Windows separators
and drive letters, and symlinks planted so a later member writes through them.

The suite verifies its own detector first: a run with tar's `-P` (which is
documented to allow escapes) must escape.  If that control stays contained the
harness is broken and everything after it is meaningless.
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FILC_OUT") or ROOT / "out")
WORK = Path(os.environ.get("WORK_DIR") or "/tmp/fil-c-utils-tests")
HOSTILE = Path(os.environ.get("HOSTILE_DIR") or WORK / "hostile")
JAIL = WORK / "jail"

# Absolute targets the archives aim at; cleared before and after every run.
ABS_PROBES = [Path(p) for p in (
    "/tmp/fil-c-utils-escape-absolute", "/tmp/fil-c-utils-escape-slashes",
    "/tmp/fil-c-utils-escape-symabs", "/tmp/fil-c-utils-escape-zipabs",
    "/tmp/fil-c-utils-escape-rarabs", "/tmp/fil-c-utils-escape-rarsymabs",
    "/tmp/fil-c-utils-escape-cpioabs", "/tmp/fil-c-esc",
)]

COMMANDS = {
    "tar":   [("tar -xf",  ["tar", "-xf", "{f}", "-C", "{d}"]),
              ("tar -xkf", ["tar", "-xkf", "{f}", "-C", "{d}"])],
    "7z":    [("7z x",     ["7z", "x", "-y", "-bso0", "-bsp0", "-o{d}", "{f}"]),
              ("7z e",     ["7z", "e", "-y", "-bso0", "-bsp0", "-o{d}", "{f}"])],
    # x keeps stored paths, e flattens them; neither may leave {d}.
    "unrar": [("unrar x",  ["unrar", "x", "-y", "-idq", "{f}", "{d}/"]),
              ("unrar e",  ["unrar", "e", "-y", "-idq", "{f}", "{d}/"])],
}


def snapshot(root):
    out = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for n in dirnames + filenames:
            out.add(str(Path(dirpath, n).relative_to(root)))
    return out


def clear_probes():
    for p in ABS_PROBES:
        if p.is_symlink() or p.exists():
            p.unlink()


def extract(argv_tmpl, archive):
    """Run one extraction in a fresh jail; return the observed escape evidence."""
    if JAIL.exists():
        shutil.rmtree(JAIL)
    dest = JAIL / "dest"
    dest.mkdir(parents=True)
    (JAIL / "canary.txt").write_text("original\n")
    (JAIL / "sub").mkdir()
    clear_probes()

    before = snapshot(JAIL)
    argv = [a.replace("{f}", str(archive)).replace("{d}", str(dest)) for a in argv_tmpl]
    argv[0] = str(OUT / argv[0])
    proc = subprocess.run(argv, cwd=str(dest), capture_output=True, timeout=120,
                          env={"PATH": f"{OUT}:/usr/bin:/bin", "LC_ALL": "C",
                               "HOME": str(WORK / "home")})
    after = snapshot(JAIL)

    outside = sorted(p for p in (after - before) if not p.startswith("dest"))
    absolute = [str(p) for p in ABS_PROBES if p.is_symlink() or p.exists()]
    clobbered = (JAIL / "canary.txt").read_text() != "original\n"
    clear_probes()
    return {
        "rc": proc.returncode,
        "outside": outside,
        "abs": absolute,
        "canary_clobbered": clobbered,
        "escaped": bool(outside or absolute or clobbered),
        "filc": "filc safety error" in proc.stderr.decode("utf-8", "replace").lower(),
        "stderr": proc.stderr.decode("utf-8", "replace").strip().splitlines()[:2],
    }


def self_check():
    """tar -P is supposed to escape.  If it does not, the detector is broken."""
    control = HOSTILE / "tar-absolute.tar"
    if not control.exists():
        print("self-check skipped: tar-absolute.tar missing", file=sys.stderr)
        return False
    r = extract(["tar", "-Pxf", "{f}", "-C", "{d}"], control)
    if not r["escaped"]:
        print("SELF-CHECK FAILED: `tar -Pxf` did not escape the jail, so this "
              "harness cannot detect escapes.", file=sys.stderr)
        return False
    print(f"self-check: `tar -Pxf` escaped as expected "
          f"({', '.join(r['outside'] + r['abs'])}); detector works\n")
    return True


def main():
    manifest_path = HOSTILE / "manifest.json"
    if not manifest_path.exists():
        print(f"no hostile archives at {HOSTILE}; run make-hostile.py first",
              file=sys.stderr)
        return 2
    if not self_check():
        return 2

    rows = []
    for entry in json.loads(manifest_path.read_text()):
        archive = Path(entry["archive"])
        for tool in entry["tools"]:
            for label, tmpl in COMMANDS[tool]:
                r = extract(tmpl, archive)
                r.update(archive=archive.name, tool=tool, cmd=label)
                rows.append(r)

    width = max(len(r["archive"]) for r in rows) + 1
    print(f"{'archive':<{width}} {'command':<10} {'rc':>4}  result")
    for r in rows:
        if r["escaped"]:
            detail = "ESCAPED -> " + ", ".join(r["outside"] + r["abs"])
            if r["canary_clobbered"]:
                detail += " (canary clobbered)"
        elif r["filc"]:
            detail = "FILC PANIC"
        else:
            detail = "contained"
        print(f"{r['archive']:<{width}} {r['cmd']:<10} {r['rc']:>4}  {detail}")

    escapes = sum(1 for r in rows if r["escaped"])
    panics = sum(1 for r in rows if r["filc"])
    (WORK / "extraction-safety.json").write_text(json.dumps(rows, indent=2))
    print(f"\n{len(rows)} extractions, {escapes} escapes, {panics} Fil-C panics")
    if escapes or panics:
        print("FAIL")
        return 1
    print("PASS: every hostile archive stayed inside the destination directory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
