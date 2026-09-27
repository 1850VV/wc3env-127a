"""Read the pinned legacy replay's map reference before creating its private install."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path, PureWindowsPath


def replay_map(path: Path) -> PureWindowsPath:
    """Decode the first game-info record. Warcraft validates the actual replay/map.

    The stat string groups seven bytes behind a mask so no encoded byte is zero.
    The first thirteen decoded bytes are flags, dimensions and map checksum.
    Limit inflation and reject traversal before using this reference as a destination.
    """
    with path.open("rb") as stream:
        header = stream.read(68)
        if (
            len(header) != 68
            or header[:28] != b"Warcraft III recorded game\x1a\0"
            or struct.unpack_from("<I", header, 28)[0] != 68
            or struct.unpack_from("<I", header, 36)[0] != 1
            or struct.unpack_from("<I", header, 52)[0] != 27
        ):
            raise ValueError("Replay must be a Warcraft III 1.27 recording")
        block = stream.read(8)
        if len(block) != 8:
            raise ValueError("Replay has no game-info block")
        compressed, expanded = struct.unpack_from("<HH", block)
        raw = stream.read(compressed)
        if len(raw) != compressed or not expanded or expanded > 8192:
            raise ValueError("Invalid replay game-info block")
        try:
            payload = zlib.decompressobj().decompress(raw, expanded + 1)
        except zlib.error as exc:
            raise ValueError("Invalid compressed replay game-info block") from exc
    try:
        if len(payload) != expanded or payload[0] != 0x10:
            raise ValueError("Invalid replay game-info record")
        cursor = payload.index(0, 6) + 1  # host name, after record prefix and player ID
        cursor += 1 + payload[cursor]  # host's counted extra data
        cursor = payload.index(0, cursor) + 1  # game name
        cursor = payload.index(0, cursor) + 1  # password
        encoded = payload[cursor : payload.index(0, cursor)]
        decoded = bytearray()
        for offset in range(0, len(encoded), 8):
            mask = encoded[offset]
            for bit, byte in enumerate(encoded[offset + 1 : offset + 8], 1):
                decoded.append(byte if mask & (1 << bit) else byte - 1)
        reference = PureWindowsPath(decoded[13 : decoded.index(0, 13)].decode("utf-8"))
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        raise ValueError("Malformed replay map reference") from exc
    if (
        reference.root
        or reference.drive
        or ".." in reference.parts
        or any(":" in part for part in reference.parts)
        or reference.is_reserved()
        or reference.suffix.lower() not in (".w3x", ".w3m")
    ):
        raise ValueError("Replay map must be a relative map path within its installation")
    return reference


def find_replay_map(source: Path, reference: PureWindowsPath) -> Path:
    direct = source.joinpath(*reference.parts)
    if direct.is_file():
        return direct
    matches = list((source / "Maps").rglob(reference.name))
    if len(matches) != 1:
        raise ValueError(f"Replay needs {reference}; found {len(matches)} matching maps under {source / 'Maps'}")
    return matches[0]
