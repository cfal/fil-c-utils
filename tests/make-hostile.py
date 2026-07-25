#!/usr/bin/env python3
"""Craft archives that try to write outside the extraction directory.

Each archive is paired with the paths it attempts to create.  The test driver
extracts into a jail and fails if any of them appear.
"""
import io, json, os, sys, tarfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rar5

OUTDIR = Path(sys.argv[1] if len(sys.argv) > 1
              else os.environ.get("HOSTILE_DIR", "/tmp/fil-c-utils-tests/hostile"))
OUTDIR.mkdir(parents=True, exist_ok=True)
BODY = b"PWNED\n"
manifest = []


def tar_case(name, entries, fmt=tarfile.GNU_FORMAT):
    """entries: list of dicts with name/type/linkname/mode."""
    path = OUTDIR / name
    with tarfile.open(path, "w", format=fmt) as tf:
        for e in entries:
            ti = tarfile.TarInfo(e["name"])
            ti.type = e.get("type", tarfile.REGTYPE)
            ti.mode = e.get("mode", 0o644)
            if ti.type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                ti.linkname = e["linkname"]
                tf.addfile(ti)
            elif ti.type == tarfile.DIRTYPE:
                tf.addfile(ti)
            else:
                ti.size = len(BODY)
                tf.addfile(ti, io.BytesIO(BODY))
    return path


def zip_case(name, entries):
    path = OUTDIR / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for e in entries:
            zi = zipfile.ZipInfo(e["name"])
            zi.external_attr = e.get("attr", 0o644 << 16)
            zf.writestr(zi, e.get("body", BODY))
    return path


def add(path, escapes, tools):
    manifest.append({"archive": str(path), "escapes": escapes, "tools": tools})


TAR = ["tar"]
SEVENZ = ["7z"]
BOTH = ["tar", "7z"]

# --- tar: relative traversal -------------------------------------------------
add(tar_case("tar-dotdot.tar", [{"name": "../escaped-dotdot"}]),
    ["escaped-dotdot"], TAR)
add(tar_case("tar-deep-dotdot.tar", [{"name": "../../../escaped-deep"}]),
    ["escaped-deep"], TAR)
add(tar_case("tar-embedded-dotdot.tar", [{"name": "sub/../../escaped-embedded"}]),
    ["escaped-embedded"], TAR)

# --- tar: absolute path ------------------------------------------------------
add(tar_case("tar-absolute.tar", [{"name": "/tmp/fil-c-utils-escape-absolute"}]),
    ["/tmp/fil-c-utils-escape-absolute"], TAR)
add(tar_case("tar-absolute-slashes.tar", [{"name": "///tmp/fil-c-utils-escape-slashes"}]),
    ["/tmp/fil-c-utils-escape-slashes"], TAR)

# --- tar: symlink then write through it --------------------------------------
add(tar_case("tar-symlink-escape.tar", [
    {"name": "hop", "type": tarfile.SYMTYPE, "linkname": ".."},
    {"name": "hop/escaped-symlink"},
]), ["escaped-symlink"], TAR)

add(tar_case("tar-symlink-abs.tar", [
    {"name": "hop", "type": tarfile.SYMTYPE, "linkname": "/tmp"},
    {"name": "hop/fil-c-utils-escape-symabs"},
]), ["/tmp/fil-c-utils-escape-symabs"], TAR)

# Directory symlink planted first, then a nested member underneath it.
add(tar_case("tar-symlink-dir.tar", [
    {"name": "d", "type": tarfile.SYMTYPE, "linkname": "../"},
    {"name": "d/sub", "type": tarfile.DIRTYPE, "mode": 0o755},
    {"name": "d/sub/escaped-symdir"},
]), ["sub/escaped-symdir", "escaped-symdir"], TAR)

# --- tar: hard link to a file outside the tree -------------------------------
add(tar_case("tar-hardlink-outside.tar", [
    {"name": "grab", "type": tarfile.LNKTYPE, "linkname": "/etc/hostname"},
]), [], TAR)   # checked separately: must not materialise host content

# --- tar: Windows-style separators and odd names -----------------------------
add(tar_case("tar-backslash.tar", [{"name": "..\\..\\escaped-backslash"}]),
    ["escaped-backslash"], BOTH)
add(tar_case("tar-dotdot-pax.tar",
             [{"name": "../escaped-pax"}], fmt=tarfile.PAX_FORMAT),
    ["escaped-pax"], TAR)

# --- zip (read by 7-Zip) -----------------------------------------------------
add(zip_case("zip-dotdot.zip", [{"name": "../escaped-zip-dotdot"}]),
    ["escaped-zip-dotdot"], SEVENZ)
add(zip_case("zip-deep-dotdot.zip", [{"name": "../../../escaped-zip-deep"}]),
    ["escaped-zip-deep"], SEVENZ)
add(zip_case("zip-absolute.zip", [{"name": "/tmp/fil-c-utils-escape-zipabs"}]),
    ["/tmp/fil-c-utils-escape-zipabs"], SEVENZ)
add(zip_case("zip-backslash.zip", [{"name": "..\\..\\escaped-zip-backslash"}]),
    ["escaped-zip-backslash"], SEVENZ)
add(zip_case("zip-embedded.zip", [{"name": "a/b/../../../escaped-zip-embedded"}]),
    ["escaped-zip-embedded"], SEVENZ)
add(zip_case("zip-drive.zip", [{"name": "C:/fil-c-utils-escape-drive"}]),
    ["C:/fil-c-utils-escape-drive"], SEVENZ)
# Symlink stored in a zip (unix mode bits mark it), then a write through it.
zi_path = OUTDIR / "zip-symlink.zip"
with zipfile.ZipFile(zi_path, "w") as zf:
    zi = zipfile.ZipInfo("hop")
    zi.create_system = 3                       # unix
    zi.external_attr = (0o120777 << 16)        # S_IFLNK | 0777
    zf.writestr(zi, "..")
    zf.writestr("hop/escaped-zipsym", BODY)
add(zi_path, ["escaped-zipsym"], SEVENZ)


# --- RAR 5 (read by unrar, and by 7-Zip's rar handler) -----------------------
def rar_case(name, entries):
    return rar5.write(str(OUTDIR / name), entries)


UNRAR_7Z = ["unrar", "7z"]

add(rar_case("rar-dotdot.rar", [{"name": "../escaped-rar-dotdot", "body": BODY}]),
    ["escaped-rar-dotdot"], UNRAR_7Z)
add(rar_case("rar-deep-dotdot.rar",
             [{"name": "../../../escaped-rar-deep", "body": BODY}]),
    ["escaped-rar-deep"], UNRAR_7Z)
add(rar_case("rar-embedded-dotdot.rar",
             [{"name": "a/b/../../../escaped-rar-embedded", "body": BODY}]),
    ["escaped-rar-embedded"], UNRAR_7Z)
add(rar_case("rar-absolute.rar",
             [{"name": "/tmp/fil-c-utils-escape-rarabs", "body": BODY}]),
    ["/tmp/fil-c-utils-escape-rarabs"], UNRAR_7Z)
add(rar_case("rar-backslash.rar",
             [{"name": "..\\..\\escaped-rar-backslash", "body": BODY}]),
    ["escaped-rar-backslash"], UNRAR_7Z)
add(rar_case("rar-drive.rar",
             [{"name": "C:/fil-c-utils-escape-rardrive", "body": BODY}]),
    ["C:/fil-c-utils-escape-rardrive"], UNRAR_7Z)

# Symlink planted first, then a member written through it (CVE-2022-30333 shape).
add(rar_case("rar-symlink-escape.rar", [
    {"name": "hop", "symlink_target": ".."},
    {"name": "hop/escaped-rarsym", "body": BODY},
]), ["escaped-rarsym"], UNRAR_7Z)

add(rar_case("rar-symlink-abs.rar", [
    {"name": "hop", "symlink_target": "/tmp"},
    {"name": "hop/fil-c-utils-escape-rarsymabs", "body": BODY},
]), ["/tmp/fil-c-utils-escape-rarsymabs"], UNRAR_7Z)

# Symlink whose own target escapes, with a deeper write through it.
add(rar_case("rar-symlink-deep.rar", [
    {"name": "d", "directory": True},
    {"name": "d/hop", "symlink_target": "../.."},
    {"name": "d/hop/escaped-rarsymdeep", "body": BODY},
]), ["escaped-rarsymdeep"], UNRAR_7Z)


# --- cpio and ar, which 7-Zip extracts through their own handlers ------------
# Both store member names as plain text with no escaping, so a traversal name
# costs nothing to construct and exercises a different sanitiser from the zip
# and tar paths above.
def cpio_case(name, members):
    """Portable ASCII (newc) cpio."""
    out = bytearray()

    def entry(path, body):
        raw = path.encode() + b"\x00"
        hdr = (b"070701"
               + b"".join(b"%08X" % v for v in (
                   1, 0o100644, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(raw), 0)))
        out.extend(hdr + raw)
        out.extend(b"\x00" * (-len(out) % 4))
        out.extend(body)
        out.extend(b"\x00" * (-len(out) % 4))

    for path in members:
        entry(path, BODY)
    entry("TRAILER!!!", b"")
    path = OUTDIR / name
    path.write_bytes(bytes(out))
    return path


def ar_case(name, members):
    out = bytearray(b"!<arch>\n")
    for member in members:
        # The 16-byte name field is why ar traversal names stay short.
        out.extend(f"{member + '/':<16}{0:<12}{0:<6}{0:<6}{0o100644:<8o}"
                   f"{len(BODY):<10}".encode() + b"`\n")
        out.extend(BODY)
        if len(BODY) % 2:
            out.extend(b"\n")
    path = OUTDIR / name
    path.write_bytes(bytes(out))
    return path


add(cpio_case("cpio-dotdot.cpio", ["../escaped-cpio-dotdot"]),
    ["escaped-cpio-dotdot"], SEVENZ)
add(cpio_case("cpio-deep.cpio", ["../../../escaped-cpio-deep"]),
    ["escaped-cpio-deep"], SEVENZ)
add(cpio_case("cpio-absolute.cpio", ["/tmp/fil-c-utils-escape-cpioabs"]),
    ["/tmp/fil-c-utils-escape-cpioabs"], SEVENZ)
add(ar_case("ar-dotdot.a", ["../escaped-ar"]), ["escaped-ar"], SEVENZ)
add(ar_case("ar-absolute.a", ["/tmp/fil-c-esc"]), ["/tmp/fil-c-esc"], SEVENZ)

(OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"{len(manifest)} hostile archives in {OUTDIR}")
