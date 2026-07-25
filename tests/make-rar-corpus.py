#!/usr/bin/env python3
"""Add RAR archives to the corpus.

unrar cannot create archives, so valid RAR 5 headers are synthesised locally.
The pinned markokr/rarfile fixture set covers RAR 1.5/2/3/5 and is fetched when
the network allows; without it the corpus keeps only the synthesised archives.
"""
import hashlib, io, re, sys, tarfile, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rar5

# Same pin the unrar Dockerfile uses.
FIXTURE_COMMIT = "09fd4f216ef502e478f1aeb6f0e193b49056eee8"
FIXTURE_SHA256 = "ddcc0da3ee181763a8bc42d1cab55abca2f0f994380a81435c932ab24603f430"
FIXTURE_URL = f"https://github.com/markokr/rarfile/archive/{FIXTURE_COMMIT}.tar.gz"


def synth(corpus: Path):
    body = b"the quick brown fox jumps over the lazy dog\n" * 64
    cases = {
        "synth-basic.rar": [
            {"name": "hello.txt", "body": b"hello rar5\n"},
            {"name": "empty.txt", "body": b""},
            {"name": "big.txt", "body": body},
        ],
        "synth-dirs.rar": [
            {"name": "d", "directory": True},
            {"name": "d/sub", "directory": True},
            {"name": "d/sub/leaf.txt", "body": b"leaf\n"},
        ],
        "synth-links.rar": [
            {"name": "target.txt", "body": b"target\n"},
            {"name": "rel.lnk", "symlink_target": "target.txt"},
            {"name": "abs.lnk", "symlink_target": "/etc/hostname"},
        ],
        "synth-names.rar": [
            {"name": "with space.txt", "body": b"space\n"},
            {"name": "éà中文.txt", "body": b"unicode\n"},
            {"name": "a/b/c/d/e/f/g/deep.txt", "body": b"deep\n"},
        ],
        "synth-many.rar": [
            {"name": "f%03d.dat" % i, "body": bytes([i]) * (i * 3 % 251 + 1)}
            for i in range(120)
        ],
    }
    for name, entries in cases.items():
        rar5.write(str(corpus / name), entries)
    return len(cases)


def fixtures(corpus: Path):
    try:
        with urllib.request.urlopen(FIXTURE_URL, timeout=60) as r:
            blob = r.read()
    except Exception as e:                                  # offline is fine
        print(f"  rarfile fixtures unavailable ({e.__class__.__name__}); "
              f"using synthesised RAR archives only")
        return 0
    got = hashlib.sha256(blob).hexdigest()
    if got != FIXTURE_SHA256:
        print(f"  rarfile fixture checksum mismatch: {got}", file=sys.stderr)
        return 0
    n = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            parts = Path(m.name).parts
            if not m.isfile() or len(parts) < 4:
                continue
            if parts[1:3] != ("test", "files"):
                continue
            name = Path(m.name).name
            # Old-style multi-volume sets need their .rNN parts alongside the
            # .rar or unrar cannot follow the volume chain.
            if not (name.endswith(".rar") or re.fullmatch(r".+\.r\d\d", name)):
                continue
            src = tf.extractfile(m)
            if src is None:
                continue
            (corpus / ("rarfile-" + name)).write_bytes(src.read())
            n += name.endswith(".rar")
    return n


def main():
    corpus = Path(sys.argv[1])
    corpus.mkdir(parents=True, exist_ok=True)
    s = synth(corpus)
    f = fixtures(corpus)
    print(f"rar: {s} synthesised + {f} pinned fixture archives")
    return 0


if __name__ == "__main__":
    sys.exit(main())
