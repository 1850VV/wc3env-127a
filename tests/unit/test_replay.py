"""Bounded decoding and safe placement of a legacy replay's referenced map."""

import struct
import tempfile
import unittest
import zlib
from pathlib import Path, PureWindowsPath

from wc3env.replay import find_replay_map, replay_map


def recording(reference, *, version=27, inflate=8192):
    stat = bytes(13) + reference.encode("utf-8") + b"\0Creator\0"
    encoded = bytearray()
    for start in range(0, len(stat), 7):
        group = stat[start : start + 7]
        mask = 1
        values = bytearray()
        for bit, value in enumerate(group, 1):
            if value & 1:
                mask |= 1 << bit
                values.append(value)
            else:
                values.append(value + 1)
        encoded.append(mask)
        encoded.extend(values)
    payload = b"\x10\x00\x00\x00\x00\x00Host\0\x01\0Game\0\0" + encoded + b"\0"
    payload = payload.ljust(inflate, b"\0")
    compressor = zlib.compressobj()
    block = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
    header = bytearray(68)
    header[:28] = b"Warcraft III recorded game\x1a\0"
    struct.pack_into("<I", header, 28, 68)
    struct.pack_into("<I", header, 36, 1)
    struct.pack_into("<I", header, 52, version)
    return header + struct.pack("<HHI", len(block), inflate, 0) + block


class ReplayMapTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.file = self.root / "sample.w3g"

    def test_native_sync_flush_block_and_map_search(self):
        self.file.write_bytes(recording(r"Maps\FrozenThrone\(2)EchoIsles.w3x"))
        reference = replay_map(self.file)
        self.assertEqual(reference, PureWindowsPath(r"Maps\FrozenThrone\(2)EchoIsles.w3x"))
        target = self.root.joinpath(*reference.parts)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"map")
        self.assertEqual(find_replay_map(self.root, reference), target)
        self.assertEqual(find_replay_map(self.root, PureWindowsPath(r"Maps\(2)EchoIsles.w3x")), target)
        second = self.root / "Maps" / target.name
        second.write_bytes(b"another map")
        with self.assertRaisesRegex(ValueError, "2 matching"):
            find_replay_map(self.root, PureWindowsPath(r"Maps\Missing\(2)EchoIsles.w3x"))

    def test_untrusted_map_paths_cannot_escape_private_install(self):
        for name in (
            r"C:\map.w3x",
            r"\map.w3x",
            r"..\map.w3x",
            r"Maps\..\map.w3x",
            r"Maps\map:stream.w3x",
            "NUL.w3x",
            "Game.dll",
        ):
            with self.subTest(name=name):
                self.file.write_bytes(recording(name))
                with self.assertRaises(ValueError):
                    replay_map(self.file)

    def test_wrong_version_truncation_and_inflation_are_rejected(self):
        valid = recording(r"Maps\test.w3x")
        cases = [
            b"",
            valid[:68],
            valid[:-5],
            recording(r"Maps\test.w3x", version=29),
            recording(r"Maps\test.w3x", inflate=8193),
        ]
        forged = bytearray(valid)
        struct.pack_into("<H", forged, 70, 10)
        cases.append(forged)
        bad_zlib = bytearray(valid)
        bad_zlib[76] = 0
        cases.append(bad_zlib)
        for value in cases:
            with self.subTest(length=len(value)):
                self.file.write_bytes(value)
                with self.assertRaises(ValueError):
                    replay_map(self.file)
