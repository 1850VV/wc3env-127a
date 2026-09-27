"""List the JASS natives the exe registers: name, prototype, implementation RVA.

    python tools/natives.py                 # every native
    python tools/natives.py GetPlayerState Player   # just these

The 1.29 registration binder receives three stack arguments; 1.27a's Game.dll uses
ECX/EDX for implementation/name and pushes the prototype. Registration ABI is separate
from each native's calling convention. --registrations retains all duplicate/stub sites.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.disasm import Image


@dataclass(frozen=True)
class Registration:
    name: str
    prototype: str
    implementation: int
    site: int
    binder: int
    convention: str


def registrations(img: Image) -> list[Registration]:
    """Decode both known registration sequences, retaining duplicate/stub entries.

    These are static candidates, not proof of runtime calling conventions or compatibility.
    1.27a passes the implementation in ECX and name in EDX; only the prototype is pushed.
    The 1.29 build pushes all three. Both end in a direct call to the binder.
    """
    d = img.d
    base = img.image_base

    # rva <-> file offset helpers over the sections
    def rva_of(off: int) -> int | None:
        for _, va, vsize, rptr, rsize in img.sections:
            if rptr <= off < rptr + rsize:
                return va + (off - rptr)
        return None

    def off_of(rva: int) -> int | None:
        for _, va, vsize, rptr, rsize in img.sections:
            if va <= rva < va + rsize:
                return rptr + (rva - va)
        return None

    def cstring(va: int) -> str | None:
        off = off_of(va - base)
        if off is None:
            return None
        end = d.find(b"\0", off, min(off + 512, len(d)))
        if end < 0:
            return None
        try:
            return d[off:end].decode("ascii")
        except UnicodeDecodeError:
            return None

    out = []
    patterns = (
        (rb"\x68(....)\x68(....)\x68(....)\xe8(....)", "stack"),
        (rb"\x68(....)\xba(....)\xb9(....)\xe8(....)", "fastcall"),
    )
    for pattern, convention in patterns:
        for m in re.finditer(pattern, d, re.S):
            proto_va, name_va, fn_va = (struct.unpack("<I", m.group(i))[0] for i in (1, 2, 3))
            site = rva_of(m.start())
            if site is None or not any(
                name == ".text" and va <= site and site + 20 <= va + rs for name, va, _, _, rs in img.sections
            ):
                continue
            prototype, name = cstring(proto_va), cstring(name_va)
            if not name or not re.fullmatch(r"[A-Z][A-Za-z0-9]{1,63}", name):
                continue
            if not prototype or not re.fullmatch(r"\([A-Za-z0-9;]*\)[A-Za-z0-9;]+", prototype):
                continue
            impl = fn_va - base
            binder = site + 20 + struct.unpack("<i", m.group(4))[0]
            if not all(
                any(sec == ".text" and va <= rva < va + rs for sec, va, _, _, rs in img.sections)
                for rva in (impl, binder)
            ):
                continue
            out.append(Registration(name, prototype, impl, site, binder, convention))
    return sorted(out, key=lambda r: r.site)


def natives(img: Image) -> dict[str, tuple[str, int]]:
    """Select unique implementations; never resolve ambiguous real implementations silently."""
    sites = registrations(img)
    users = Counter(r.implementation for r in sites)
    grouped: dict[str, set[tuple[str, int]]] = {}
    for r in sites:
        grouped.setdefault(r.name, set()).add((r.prototype, r.implementation))
    out = {}
    for name, candidates in grouped.items():
        if len(candidates) > 1:
            # 1.27a has a second table binding names to `xor eax,eax; ret`.
            # Retain it in registrations(), but do not mistake it for a real implementation.
            real = {
                c for c in candidates if users[c[1]] <= 1 or img.read(c[1], 3) not in (b"\x33\xc0\xc3", b"\x31\xc0\xc3")
            }
            if real:
                candidates = real
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous native {name}: {sorted(candidates)}; inspect registration sites")
        out[name] = next(iter(candidates))
    return out


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    from disasm import EXE, Image

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--exe", type=Path, default=EXE, help="PE image, including Game.dll on 1.27a")
    ap.add_argument("--registrations", action="store_true", help="JSON of every registration, including stubs")
    a = ap.parse_args()
    img = Image(a.exe)
    if a.registrations:
        print(json.dumps([asdict(r) for r in registrations(img) if not a.names or r.name in a.names], indent=2))
        return
    table = natives(img)
    want = a.names
    for name in sorted(table):
        if want and name not in want:
            continue
        proto, rva = table[name]
        print(f"{rva:08x}  {name:40s} {proto}")
    if not want:
        print(f"; {len(table)} natives")


if __name__ == "__main__":
    main()
