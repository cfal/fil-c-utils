#!/usr/bin/env python3
"""Static checks that do not need the input, or the CPU, that would trip them.

Three defects share a shape: they compile cleanly, survive functional tests,
and then abort at run time on a machine or an input that reaches them.

  misaligned pointer field
      Fil-C stores a capability alongside every pointer slot and requires those
      slots to keep their natural alignment.  A packed struct that puts a
      pointer at, say, offset 2 panics the first time that field is written.

  unhandled intrinsic
      Fil-C compiles an intrinsic it cannot lower into a trap, embedding the
      LLVM IR text as the panic message.  Programs that pick a SIMD
      implementation from CPUID only reach those traps on a CPU with the
      relevant feature, so a build can be clean on one machine and abort on
      another.  The embedded strings are visible without that CPU.

  unsupported inline assembly
      Fil-C likewise leaves a trap when a target cannot compile an inline
      assembly block.  Optional architecture-specific paths can hide it until
      a particular input selects them.
"""
import re, subprocess, sys
from pathlib import Path

PTR_ALIGN = 8
INTRINSIC = re.compile(rb"@llvm\.[a-z0-9._]+")
INLINE_ASM = b"cannot handle inline asm"


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


def unhandled_intrinsics(binary):
    """Distinct LLVM intrinsics Fil-C compiled into a trap."""
    return sorted({m.decode() for m in INTRINSIC.findall(binary.read_bytes())})


def has_unsupported_inline_asm(binary):
    """Whether Fil-C compiled unsupported inline assembly into a trap."""
    return INLINE_ASM in binary.read_bytes()


def has_dwarf(binary):
    """Whether the binary still carries the debug info this scan reads.

    A stripped binary yields no DIEs, so every pass below finds nothing and the
    scan would report `clean` while having examined no structure at all. That
    is the one result this must never produce, so absence of DWARF is reported
    as its own outcome rather than as success.
    """
    p = subprocess.run(["readelf", "--debug-dump=info", str(binary)],
                       capture_output=True, text=True, errors="replace")
    return "DW_TAG_" in p.stdout


NO_DEBUG_INFO = 2


def main():
    findings = 0
    stripped = []
    for b in sys.argv[1:]:
        p = Path(b)
        if p.is_symlink() or not p.is_file():
            continue

        # The intrinsic check reads raw bytes, so it still works on a stripped
        # binary. Only the alignment scan needs DWARF.
        scannable = has_dwarf(p)
        if not scannable:
            stripped.append(p.name)
        misaligned = sorted(set(scan(p))) if scannable else []
        intrinsics = unhandled_intrinsics(p)
        inline_asm = has_unsupported_inline_asm(p)

        notes = []
        if misaligned:
            notes.append(f"{len(misaligned)} misaligned pointer field(s)")
        if intrinsics:
            notes.append(f"{len(intrinsics)} unhandled intrinsic(s)")
        if inline_asm:
            notes.append("unsupported inline assembly")
        findings += len(misaligned) + len(intrinsics) + int(inline_asm)

        if not scannable:
            notes.append("no debug info, alignment not scanned")
        print(f"{p.name:<14} {', '.join(notes) if notes else 'clean'}")
        for s, mem, off in misaligned:
            print(f"                 {s}.{mem} @ offset {off}")
        for name in intrinsics:
            print(f"                 {name}")
        if inline_asm:
            print("                 Fil-C cannot handle inline asm")

    if stripped:
        print(f"\n{len(stripped)} binary(ies) carry no debug info, so nothing was "
              f"scanned in them: {', '.join(stripped)}")
        print("Scan an unstripped build instead, for example the Dockerfile's "
              "`build` stage, which keeps DWARF.")
        return NO_DEBUG_INFO
    return 0


if __name__ == "__main__":
    sys.exit(main())
