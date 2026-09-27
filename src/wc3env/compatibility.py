"""The executable supported by the native adapter. Verify before loading any hooks."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

GAME_VERSION = "1.27.0.52240"
EXE_SHA256 = "ea8f5192efede23f84bc60140c2d4a0085ea68b86f430c1d60c354a555922def"
ENGINE_SHA256 = "e04d1716603c075eb0c8e1e21cf1093a664adc5249efab396bfa08d7b09d0c3a"


def verify_executable(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"No Warcraft III executable at {path}; set WC3_GAME_DIR (see .env.example)")
    digest = _verify_image(path, EXE_SHA256)
    _verify_image(path.with_name("Game.dll"), ENGINE_SHA256)
    return digest


def _verify_image(path: Path, expected: str) -> str:
    data = path.read_bytes()
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
    digest = hashlib.sha256(data).hexdigest()
    if not valid or digest != expected:
        raise ValueError(
            f"Unsupported Warcraft executable: {path}. This adapter requires the verified "
            f"32-bit {GAME_VERSION} binary (SHA-256 {expected}); found {digest}. "
            "No process was started. Other binaries need a verified adapter."
        )
    return digest
