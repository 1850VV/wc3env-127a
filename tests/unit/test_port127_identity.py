"""Binary gates use synthetic fixtures, not Warcraft binaries."""

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.port127.identity import verify_pair
from wc3env.compatibility import verify_executable


def image_bytes(machine=0x14C):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, machine)
    struct.pack_into("<H", data, 0x98, 0x10B)
    return bytes(data)


class PairIdentityTest(unittest.TestCase):
    def test_both_hashes_are_required_and_architecture_is_independent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hashes = {}
            for name in ("War3.exe", "Game.dll"):
                data = image_bytes()
                (root / name).write_bytes(data)
                hashes[name] = hashlib.sha256(data).hexdigest()
            with patch("tools.port127.identity.HASHES", hashes):
                self.assertEqual(verify_pair(root), hashes)
                (root / "Game.dll").write_bytes(data + b"changed")
                with self.assertRaisesRegex(ValueError, "Game.dll"):
                    verify_pair(root)
                data = image_bytes(0x8664)
                (root / "Game.dll").write_bytes(data)
                hashes["Game.dll"] = hashlib.sha256(data).hexdigest()
                with self.assertRaisesRegex(ValueError, "x86 Game.dll"):
                    verify_pair(root)

    def test_research_identity_does_not_enable_production_injection(self):
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "War3.exe"
            exe.write_bytes(image_bytes())
            with self.assertRaisesRegex(ValueError, "No process was started"):
                verify_executable(exe)
