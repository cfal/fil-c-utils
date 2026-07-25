#!/usr/bin/env python3
"""Synthesise containers for 7-Zip handlers no Linux tool can produce.

The Docker generator in tests/formats covers every format some package still
builds. What is left is mostly Windows and Apple formats, plus a few obsolete
ones. Each container here is written by hand from its published layout: small,
structurally valid enough that 7-Zip identifies the type and enters the
handler, and therefore a usable seed for mutation.

Each writer returns the 7-Zip type name it targets, and the caller keeps only
the files 7-Zip actually recognises, so a writer that drifts out of spec drops
out of the corpus instead of silently testing nothing.
"""
import struct, sys, zlib
from pathlib import Path

PAYLOAD = b"the quick brown fox jumps over the lazy dog\n" * 24


# --------------------------------------------------------------------- Apple
def macho(path):
    """64-bit Mach-O with one __TEXT segment."""
    seg = struct.pack("<II16sQQQQiiII",
                      0x19, 72 + 0, b"__TEXT", 0, 0x1000, 0, len(PAYLOAD),
                      7, 5, 0, 0)
    hdr = struct.pack("<IiiIIII I", 0xFEEDFACF, 0x01000007, 3, 2,
                      1, len(seg), 0x200085, 0)
    path.write_bytes(hdr + seg + PAYLOAD)
    return "MachO"


def mub(path):
    """Universal binary: fat header wrapping two Mach-O slices."""
    inner = Path(str(path) + ".slice")
    macho(inner)
    slice_bytes = inner.read_bytes()
    inner.unlink()
    align = 12                      # 2**12 = 4096
    offset = 4096
    archs = b""
    body = b""
    for cputype in (0x01000007, 0x0100000C):    # x86_64 and arm64
        archs += struct.pack(">IIIII", cputype, 3, offset, len(slice_bytes), align)
        body += b"\x00" * (offset - (4096 + len(body))) + slice_bytes
        offset += ((len(slice_bytes) + 4095) // 4096) * 4096
    head = struct.pack(">II", 0xCAFEBABE, 2) + archs
    path.write_bytes(head + b"\x00" * (4096 - len(head)) + body)
    return "Mub"


def apm(path):
    """Apple Partition Map: block0 'ER' plus one 'PM' entry."""
    block = 512
    b0 = struct.pack(">HHIHH", 0x4552, block, 64, 1, 0) + b"\x00" * (block - 16)
    pm = struct.pack(">HHIII32s32sII", 0x504D, 0, 1, 4, 32,
                     b"probe", b"Apple_HFS", 4, 32)
    pm += b"\x00" * (block - len(pm))
    path.write_bytes(b0 + pm + b"\x00" * (block * 62))
    return "APM"


# ------------------------------------------------------------------- Windows
def compound(path):
    """OLE2 / Compound File Binary: header, one FAT sector, one directory."""
    SECTOR = 512
    FREE, ENDOFCHAIN, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD

    header = struct.pack(
        "<8s16sHHHHH6sIIIIIIII",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"\x00" * 16,
        0x003E, 3, 0xFFFE, 9, 6, b"\x00" * 6,
        0,          # directory sector count (unused for version 3)
        1,          # FAT sector count
        1,          # first directory sector
        0,          # transaction signature
        4096,       # mini stream cutoff
        ENDOFCHAIN, # first mini FAT sector
        0,          # mini FAT sector count
        ENDOFCHAIN) # first DIFAT sector
    header += struct.pack("<I", 0)                       # DIFAT sector count
    difat = [0] + [FREE] * 108                           # DIFAT[0] -> sector 0
    header += struct.pack("<109I", *difat)
    header += b"\x00" * (SECTOR - len(header))

    fat = [FATSECT, ENDOFCHAIN, ENDOFCHAIN] + [FREE] * (SECTOR // 4 - 3)
    fat_sector = struct.pack(f"<{SECTOR // 4}I", *fat)

    def dir_entry(name, etype, colour, left, right, child, start, size):
        raw = name.encode("utf-16-le") + b"\x00\x00"
        return (raw.ljust(64, b"\x00") + struct.pack("<H", len(raw))
                + struct.pack("<BB", etype, colour)
                + struct.pack("<III", left, right, child)
                + b"\x00" * 16 + struct.pack("<I", 0)
                + b"\x00" * 16 + struct.pack("<IQ", start, size))

    root = dir_entry("Root Entry", 5, 1, FREE, FREE, 1, ENDOFCHAIN, 0)
    stream = dir_entry("Contents", 2, 1, FREE, FREE, FREE, 2, len(PAYLOAD))
    empty = b"\x00" * 128
    directory = (root + stream + empty + empty)[:SECTOR]

    data = PAYLOAD.ljust(SECTOR, b"\x00")
    path.write_bytes(header + fat_sector + directory + data)
    return "Compound"


def mslz(path):
    """SZDD compressed file: header plus a run of literal-coded bytes."""
    head = b"SZDD\x88\xf0\x27\x33" + b"A" + b"T" + struct.pack("<I", len(PAYLOAD))
    body = bytearray()
    for i in range(0, len(PAYLOAD), 8):
        chunk = PAYLOAD[i:i + 8]
        body.append(0xFF)                 # eight literal flags
        body += chunk
    path.write_bytes(head + bytes(body))
    return "MsLZ"


def lzh(path):
    """LHA level-0 header with a stored (-lh0-) member."""
    name = b"probe.txt"
    body = PAYLOAD
    rest = (b"-lh0-" + struct.pack("<I", len(body)) + struct.pack("<I", len(body))
            + struct.pack("<I", 0) + bytes([0x20]) + bytes([0])
            + bytes([len(name)]) + name
            + struct.pack("<H", zlib.crc32(body) & 0xFFFF))
    header = bytes([len(rest), sum(rest) & 0xFF]) + rest
    path.write_bytes(header + body + b"\x00")
    return "Lzh"


def te(path):
    """EFI Terse Executable header."""
    hdr = struct.pack("<2sHBBHIIQ", b"VZ", 0x8664, 1, 0, 0, 0, 0x28, 0)
    section = struct.pack("<8sIIIIIIHHI", b".text", len(PAYLOAD), 0x28,
                          len(PAYLOAD), 0x28, 0, 0, 0, 0, 0x60000020)
    path.write_bytes(hdr + section + PAYLOAD)
    return "TE"


def chm(path):
    """ITSF container header; enough for the handler to parse and reject."""
    guid1 = bytes.fromhex("10fd017ccaa7c211859e0a0ac96eb653")
    guid2 = bytes.fromhex("11fd017ccaa7c211859e0a0ac96eb653")
    hdr = (b"ITSF" + struct.pack("<III", 3, 0x60, 1)
           + struct.pack("<I", 0) + struct.pack("<I", 0x0409)
           + guid1 + guid2
           + struct.pack("<QQQQ", 0x60, 0x18, 0x78, 0x200)
           + struct.pack("<I", 0))
    hdr = hdr.ljust(0x60, b"\x00")
    section0 = struct.pack("<QQ", 0x18, 0x600)
    itsp = (b"ITSP" + struct.pack("<III", 1, 0x54, 0x0A)
            + struct.pack("<III", 0x1000, 10, 2)
            + struct.pack("<iii", -1, 0, 0)).ljust(0x54, b"\x00")
    path.write_bytes(hdr + section0 + itsp + PAYLOAD)
    return "Chm"


# ---------------------------------------------------------------------- misc
def xar(path):
    """XAR: header, zlib-compressed XML table of contents, heap."""
    toc = (b'<?xml version="1.0" encoding="UTF-8"?>\n<xar><toc>'
           b'<file id="1"><name>probe.txt</name><type>file</type>'
           b'<data><offset>0</offset>'
           + f"<size>{len(PAYLOAD)}</size><length>{len(PAYLOAD)}</length>".encode()
           + b'<encoding style="application/octet-stream"/>'
           b'</data></file></toc></xar>\n')
    packed = zlib.compress(toc)
    head = b"xar!" + struct.pack(">HHQQI", 28, 1, len(packed), len(toc), 0)
    path.write_bytes(head + packed + PAYLOAD)
    return "Xar"


def cramfs(path):
    """CramFS superblock with a single root inode."""
    body = PAYLOAD
    total = 4096
    sb = struct.pack("<III", 0x28CD3D45, total, 0x0003)
    sb += struct.pack("<I", 0)
    sb += b"Compressed ROMFS"
    sb += struct.pack("<II", 0, 1)
    sb += b"probe".ljust(16, b"\x00")
    # root inode: mode, uid, size+gid, namelen+offset
    sb += struct.pack("<HHI", 0o040755, 0, len(body) & 0xFFFFFF)
    sb += struct.pack("<I", (0 << 6) | (0x40 >> 2))
    path.write_bytes(sb.ljust(76, b"\x00") + body.ljust(total - 76, b"\x00"))
    return "CramFS"


def swf(path):
    """Uncompressed SWF: FWS signature, rect, frame rate, frame count."""
    rect = bytes([0x78, 0x00, 0x05, 0x5F, 0x00, 0x00, 0x0F, 0xA0, 0x00])
    body = rect + struct.pack("<HH", 0x1E00, 1) + PAYLOAD + b"\x00\x00"
    path.write_bytes(b"FWS" + bytes([9]) + struct.pack("<I", 8 + len(body)) + body)
    return "SWF"


def swfc(path):
    """zlib-compressed SWF, which 7-Zip treats as its own handler."""
    rect = bytes([0x78, 0x00, 0x05, 0x5F, 0x00, 0x00, 0x0F, 0xA0, 0x00])
    body = rect + struct.pack("<HH", 0x1E00, 1) + PAYLOAD + b"\x00\x00"
    path.write_bytes(b"CWS" + bytes([9]) + struct.pack("<I", 8 + len(body))
                     + zlib.compress(body))
    return "SWFc"


def flv(path):
    """FLV with one script tag."""
    tag_body = b"\x02\x00\x0aonMetaData\x08\x00\x00\x00\x00\x00\x00\x09"
    tag = (bytes([18]) + len(tag_body).to_bytes(3, "big") + b"\x00\x00\x00\x00"
           + b"\x00\x00\x00" + tag_body)
    header = b"FLV" + bytes([1, 0x05]) + struct.pack(">I", 9)
    path.write_bytes(header + struct.pack(">I", 0) + tag
                     + struct.pack(">I", len(tag)))
    return "FLV"


def ppmd(path):
    """7-Zip's .pmd container: signature, model parameters, coded data."""
    head = bytes.fromhex("8fafac84") + struct.pack("<HBB", 8, 16, 0)
    name = b"probe.txt"
    head += struct.pack("<HH", len(name), 0o644) + name
    path.write_bytes(head + PAYLOAD)
    return "Ppmd"


WRITERS = [
    ("syn-macho.macho", macho), ("syn-mub.mub", mub), ("syn-apm.apm", apm),
    ("syn-compound.doc", compound), ("syn-mslz.mslz", mslz), ("syn-lzh.lzh", lzh),
    ("syn-te.te", te), ("syn-chm.chm", chm), ("syn-xar.xar", xar),
    ("syn-cramfs.cramfs", cramfs), ("syn-swf.swf", swf), ("syn-swfc.swf", swfc),
    ("syn-flv.flv", flv), ("syn-ppmd.pmd", ppmd),
]


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, writer in WRITERS:
        path = out / name
        try:
            rows.append((name, writer(path)))
        except Exception as e:
            print(f"  skip  {name}: {e.__class__.__name__}: {e}")
            path.unlink(missing_ok=True)
    manifest = out / "manifest-synthetic.tsv"
    manifest.write_text("".join(f"{n}\t{t}\n" for n, t in rows))
    print(f"{len(rows)} synthetic containers in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
