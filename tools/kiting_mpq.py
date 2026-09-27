"""Minimal MPQ v0 writer: uncompressed single-unit files, encrypted index tables.

Format: https://wowdev.wiki/MPQ ; independently read back using mpyq in tests.
This intentionally supports only the map builder's small, generated archives.
"""

import struct

MASK = 0xFFFFFFFF


def crypt_table():
    table = [0] * 0x500
    seed = 0x100001
    for low in range(0x100):
        for high in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            a = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            table[low + high * 0x100] = a | (seed & 0xFFFF)
    return table


TABLE = crypt_table()


def hash_name(name, kind):
    a, b = 0x7FED7FED, 0xEEEEEEEE
    for c in name.replace("/", "\\").upper().encode("ascii"):
        a = (TABLE[kind * 256 + c] ^ (a + b)) & MASK
        b = (c + a + b + (b << 5) + 3) & MASK
    return a


def encrypt(data, key):
    result = bytearray()
    seed = 0xEEEEEEEE
    for (value,) in struct.iter_unpack("<I", data):
        seed = (seed + TABLE[0x400 + (key & 0xFF)]) & MASK
        result += struct.pack("<I", value ^ ((key + seed) & MASK))
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & MASK
        seed = (value + seed + (seed << 5) + 3) & MASK
    return result


def archive(files):
    files = dict(files)
    files["(listfile)"] = ("\r\n".join(sorted([*files, "(listfile)"])) + "\r\n").encode("ascii")
    slots = 1
    while slots < len(files) * 2:
        slots *= 2
    hashes = [b"\xff" * 16 for _ in range(slots)]
    blocks = bytearray()
    payload = bytearray()
    for index, (name, data) in enumerate(sorted(files.items())):
        slot = hash_name(name, 0) % slots
        while hashes[slot] != b"\xff" * 16:
            slot = (slot + 1) % slots
        hashes[slot] = struct.pack("<IIHHI", hash_name(name, 1), hash_name(name, 2), 0, 0, index)
        blocks += struct.pack("<4I", 32 + len(payload), len(data), len(data), 0x81000000)
        payload += data
    hash_offset = 32 + len(payload)
    block_offset = hash_offset + slots * 16
    header = struct.pack(
        "<4sIIHH4I", b"MPQ\x1a", 32, block_offset + len(blocks), 0, 3, hash_offset, block_offset, slots, len(files)
    )
    return (
        header
        + payload
        + encrypt(b"".join(hashes), hash_name("(hash table)", 3))
        + encrypt(blocks, hash_name("(block table)", 3))
    )
