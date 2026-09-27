"""Exact paired identity for local 1.27a research, never a production allowlist."""

import hashlib
import struct
from pathlib import Path

VERSION = "1.27.0.52240"
HASHES = {
    "War3.exe": "ea8f5192efede23f84bc60140c2d4a0085ea68b86f430c1d60c354a555922def",
    "Game.dll": "e04d1716603c075eb0c8e1e21cf1093a664adc5249efab396bfa08d7b09d0c3a",
}


def verify_pair(game_dir: Path) -> dict[str, str]:
    """Require both pinned PE32/x86 images before any diagnostic process starts."""
    found = {}
    for name, expected in HASHES.items():
        data = (game_dir / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        try:
            pe = struct.unpack_from("<I", data, 0x3C)[0]
            valid = (
                data[:2] == b"MZ"
                and data[pe : pe + 4] == b"PE\0\0"
                and struct.unpack_from("<H", data, pe + 4)[0] == 0x14C
                and struct.unpack_from("<H", data, pe + 24)[0] == 0x10B
            )
        except struct.error:
            valid = False
        if not valid or digest != expected:
            raise ValueError(f"1.27a research requires pinned x86 {name}: expected {expected}, found {digest}")
        found[name] = digest
    return found
