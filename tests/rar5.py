#!/usr/bin/env python3
"""Minimal RAR 5.0 writer: stored files and unix symlinks.

Only enough of the format to build hostile archives for extraction-safety
testing.  unrar is the reference decoder, so the archives are validated by
listing them before use.
"""
import struct, zlib

SIG = bytes([0x52, 0x61, 0x72, 0x21, 0x1A, 0x07, 0x01, 0x00])

HEAD_MAIN, HEAD_FILE, HEAD_ENDARC = 1, 2, 5
HFL_EXTRA, HFL_DATA = 0x0001, 0x0002
FHFL_DIRECTORY, FHFL_UTIME, FHFL_CRC32 = 0x0001, 0x0002, 0x0004
FHEXTRA_REDIR = 0x05
FSREDIR_UNIXSYMLINK = 1


def vint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def block(htype, hflags, body, data=b""):
    """CRC32 | HeadSize(vint) | HeadType | HeadFlags | [sizes] | body | data"""
    head = vint(htype) + vint(hflags) + body
    out = struct.pack("<I", zlib.crc32(vint(len(head)) + head) & 0xFFFFFFFF)
    return out + vint(len(head)) + head + data


def main_header():
    return block(HEAD_MAIN, 0, vint(0))  # ArchiveFlags = 0


def end_header():
    return block(HEAD_ENDARC, 0x0004, vint(0))  # SKIPIFUNKNOWN, flags = 0


def _comp_info(store=True):
    # bits 0-5 version(0), bit 6 solid, bits 7-9 method(0=store), bits 10-13 dict
    return 0 if store else 0
def file_entry(name, body=b"", directory=False, symlink_target=None, mtime=0x60000000):
    nb = name.encode("utf-8")
    flags = FHFL_UTIME
    if directory:
        flags |= FHFL_DIRECTORY
    if body and not directory:
        flags |= FHFL_CRC32

    fields = bytearray()
    fields += vint(flags)
    fields += vint(0 if directory else len(body))     # UnpackedSize
    fields += vint(0o40755 if directory else 0o100644)  # Attributes (unix mode)
    fields += struct.pack("<I", mtime)                 # mtime
    if flags & FHFL_CRC32:
        fields += struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    fields += vint(_comp_info())                       # CompressionInfo: store
    fields += vint(3)                                  # HostOS: unix
    fields += vint(len(nb))
    fields += nb

    hflags = 0
    extra = b""
    if symlink_target is not None:
        tb = symlink_target.encode("utf-8")
        rec = vint(FHEXTRA_REDIR) + vint(FSREDIR_UNIXSYMLINK) + vint(0) + vint(len(tb)) + tb
        extra = vint(len(rec)) + rec
        hflags |= HFL_EXTRA
        # A symlink's "data" is empty; the target lives in the extra area.
        body = b""
        fields = bytearray()
        fields += vint(FHFL_UTIME)
        fields += vint(0)
        fields += vint(0o120777)
        fields += struct.pack("<I", mtime)
        fields += vint(_comp_info())
        fields += vint(3)
        fields += vint(len(nb))
        fields += nb

    data = b"" if directory else body
    if data:
        hflags |= HFL_DATA

    head_body = bytearray()
    if hflags & HFL_EXTRA:
        head_body += vint(len(extra))
    if hflags & HFL_DATA:
        head_body += vint(len(data))
    head_body += fields
    head_body += extra
    return block(HEAD_FILE, hflags, bytes(head_body), data)


def write(path, entries):
    """entries: list of dicts accepted by file_entry()."""
    with open(path, "wb") as f:
        f.write(SIG)
        f.write(main_header())
        for e in entries:
            f.write(file_entry(**e))
        f.write(end_header())
    return path
