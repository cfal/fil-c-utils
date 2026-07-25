#!/usr/bin/env python3
"""Create the deterministic input tree that every valid corpus archive holds."""
import os, random, sys
from pathlib import Path

SEED = Path(os.environ.get("SEED_DIR") or sys.argv[1])
rng = random.Random(20260725)


def write(rel, data, mode=0o644):
    path = SEED / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, mode)


def main():
    if SEED.exists():
        import shutil
        shutil.rmtree(SEED)
    SEED.mkdir(parents=True)

    # Entropy extremes: the compressors take very different paths through each.
    write("text/repeat.txt", b"the quick brown fox jumps over the lazy dog\n" * 4000)
    write("text/zeros.bin", b"\x00" * 200000)
    write("bin/random.bin", bytes(rng.getrandbits(8) for _ in range(120000)))
    write("bin/mixed.bin", b"".join(bytes([i & 0xFF]) * (i % 97 + 1) for i in range(3000)))

    # Sizes that sit on block and window boundaries.
    write("edge/empty", b"")
    write("edge/one", b"A")
    write("edge/exact64k", b"Q" * 65536)
    write("edge/off_by_one", b"Q" * 65537)

    # Names that exercise quoting, encoding, and option parsing.
    write("names/with space.txt", b"space\n")
    write("names/éà中文.txt", b"unicode\n")
    write("names/quote'and\"dq.txt", b"quotes\n")
    write("names/dash-start.txt", b"dash\n")

    # Long paths, and enough members to make solid blocks and indexes non-trivial.
    write("deep/" + "/".join("l%02d" % i for i in range(24)) + "/leaf.txt", b"deep\n")
    for i in range(200):
        write("many/f%03d.dat" % i, bytes([i]) * (i * 7 % 511 + 1))

    write("perm/exec.sh", b"#!/bin/sh\necho hi\n", 0o755)
    write("perm/readonly.txt", b"ro\n", 0o444)

    links = SEED / "links"
    links.mkdir()
    (links / "target.txt").write_bytes(b"target\n")
    os.symlink("target.txt", links / "sym.txt")
    os.symlink("/etc/hostname", links / "symabs.txt")
    os.link(links / "target.txt", links / "hard.txt")
    (SEED / "emptydir").mkdir()

    files = [p for p in SEED.rglob("*") if p.is_file() and not p.is_symlink()]
    print(f"seed: {sum(1 for _ in SEED.rglob('*'))} entries, "
          f"{sum(p.stat().st_size for p in files)} bytes in {SEED}")


if __name__ == "__main__":
    main()
