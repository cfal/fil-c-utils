#!/usr/bin/env python3
"""Scan DWARF for pointer-typed struct members at non-pointer-aligned offsets.

Fil-C stores a capability alongside every pointer slot and requires those slots
to keep their natural alignment.  A packed struct that puts a pointer at, say,
offset 2 compiles fine and then panics the first time the field is written.
This finds those layouts statically, before any input has to trigger them.
"""
import re, subprocess, sys
from pathlib import Path

PTR_ALIGN = 8


def dwarf(binary):
    p = subprocess.run(["readelf", "--debug-dump=info", str(binary)],
                       capture_output=True, text=True, errors="replace")
    return p.stdout.splitlines()


DIE = re.compile(r"^\s*<(\d+)><([0-9a-f]+)>: Abbrev Number: \d+ \((DW_TAG_\w+)\)")
ATTR_NAME = re.compile(r"DW_AT_name\s*:\s*(?:\(.*?\)\s*:\s*)?(\S+)")
ATTR_TYPE = re.compile(r"DW_AT_type\s*:\s*<0x([0-9a-f]+)>")
ATTR_LOC = re.compile(r"DW_AT_data_member_location:\s*(\d+)")


def scan(binary):
    lines = dwarf(binary)
    # Pass 1: which DIE offsets are pointer types (following typedef/cv chains).
    kind, typeref = {}, {}
    cur = None
    for l in lines:
        m = DIE.match(l)
        if m:
            cur = int(m.group(2), 16)
            kind[cur] = m.group(3)
            continue
        if cur is not None:
            t = ATTR_TYPE.search(l)
            if t:
                typeref[cur] = int(t.group(1), 16)

    def is_pointer(off, depth=0):
        while depth < 16:
            k = kind.get(off)
            if k == "DW_TAG_pointer_type":
                return True
            if k in ("DW_TAG_typedef", "DW_TAG_const_type", "DW_TAG_volatile_type",
                     "DW_TAG_restrict_type", "DW_TAG_atomic_type"):
                off = typeref.get(off)
                if off is None:
                    return False
                depth += 1
                continue
            return False
        return False

    # Pass 2: walk struct/class/union DIEs and check their members.
    findings = []
    i = 0
    n = len(lines)
    while i < n:
        m = DIE.match(lines[i])
        if not m or m.group(3) not in ("DW_TAG_structure_type", "DW_TAG_class_type"):
            i += 1
            continue
        depth = int(m.group(1))
        sname = None
        j = i + 1
        while j < n:
            dm = DIE.match(lines[j])
            if dm:
                d = int(dm.group(1))
                if d <= depth:
                    break
                if d == depth + 1 and dm.group(3) == "DW_TAG_member":
                    mname = moff = mtype = None
                    k = j + 1
                    while k < n and not DIE.match(lines[k]):
                        a = ATTR_NAME.search(lines[k])
                        if a and mname is None:
                            mname = a.group(1)
                        b = ATTR_LOC.search(lines[k])
                        if b and moff is None:
                            moff = int(b.group(1))
                        c = ATTR_TYPE.search(lines[k])
                        if c and mtype is None:
                            mtype = int(c.group(1), 16)
                        k += 1
                    if moff is not None and mtype is not None and moff % PTR_ALIGN \
                            and is_pointer(mtype):
                        findings.append((sname or "<anon>", mname or "<anon>", moff))
            else:
                a = ATTR_NAME.search(lines[j])
                if a and sname is None:
                    sname = a.group(1)
            j += 1
        i = j if j > i else i + 1
    return findings


def main():
    for b in sys.argv[1:]:
        p = Path(b)
        if p.is_symlink() or not p.is_file():
            continue
        f = scan(p)
        uniq = sorted(set(f))
        status = f"{len(uniq)} misaligned pointer field(s)" if uniq else "clean"
        print(f"{p.name:<14} {status}")
        for s, mem, off in uniq:
            print(f"                 {s}.{mem} @ offset {off}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
