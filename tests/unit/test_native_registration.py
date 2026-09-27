"""Synthetic PE sections exercise static extraction; no game compatibility claims."""

import struct
import unittest

from tools.natives import natives, registrations


class ImageFixture:
    image_base = 0x6F000000
    sections = [(".text", 0x1000, 0x1000, 0x200, 0x1000), (".rdata", 0x2000, 0x800, 0x1200, 0x500)]

    def __init__(self):
        self.d = bytearray(0x1700)
        self.next_site = 0x200
        self.next_string = 0x1200

    def read(self, rva, n):
        return self.d[rva - 0xE00 : rva - 0xE00 + n]

    def string(self, value):
        off = self.next_string
        raw = value.encode() + b"\0"
        self.d[off : off + len(raw)] = raw
        self.next_string += len(raw)
        return self.image_base + off + 0xE00

    def entry(self, name, impl, convention="fastcall", prototype="(Hunit;)R"):
        proto_va, name_va = self.string(prototype), self.string(name)
        site = self.next_site
        self.next_site += 24
        a, b = (0xBA, 0xB9) if convention == "fastcall" else (0x68, 0x68)
        self.d[site : site + 20] = (
            b"\x68"
            + struct.pack("<I", proto_va)
            + bytes([a])
            + struct.pack("<I", name_va)
            + bytes([b])
            + struct.pack("<I", self.image_base + impl)
            + b"\xe8"
            + struct.pack("<i", 0x1800 - (site + 0xE00 + 20))
        )
        return site


class RegistrationTest(unittest.TestCase):
    def test_both_register_and_stack_binders_keep_sources(self):
        image = ImageFixture()
        image.entry("GetUnitX", 0x1900)
        image.entry("GetUnitY", 0x1940, convention="stack")
        rows = registrations(image)
        self.assertEqual({r.convention for r in rows}, {"fastcall", "stack"})
        self.assertEqual({r.binder for r in rows}, {0x1800})
        self.assertEqual(natives(image), {"GetUnitX": ("(Hunit;)R", 0x1900), "GetUnitY": ("(Hunit;)R", 0x1940)})

    def test_shared_stub_does_not_hide_legitimate_zero_function(self):
        image = ImageFixture()
        for name, fn in (("GetUnitX", 0x1900), ("GetEnemyPower", 0x1940)):
            image.entry(name, 0x1980)
            image.entry(name, fn)
        for rva in (0x1940, 0x1980):
            image.d[rva - 0xE00 : rva - 0xE00 + 3] = b"\x33\xc0\xc3"
        self.assertEqual(natives(image)["GetEnemyPower"][1], 0x1940)
        self.assertEqual(len(registrations(image)), 4)

    def test_two_real_implementations_are_rejected(self):
        image = ImageFixture()
        image.entry("GetUnitX", 0x1900)
        image.entry("GetUnitX", 0x1940)
        with self.assertRaisesRegex(ValueError, "Ambiguous native GetUnitX"):
            natives(image)

    def test_malformed_registration_or_noncode_target_is_not_a_native(self):
        for invalid in ("call", "prototype", "target", "virtual_string"):
            with self.subTest(invalid=invalid):
                image = ImageFixture()
                off = image.entry(
                    "GetUnitX",
                    0x2100 if invalid == "target" else 0x1900,
                    prototype="bad" if invalid == "prototype" else "(Hunit;)R",
                )
                if invalid == "call":
                    image.d[off + 15] = 0x90
                if invalid == "virtual_string":
                    struct.pack_into("<I", image.d, off + 6, image.image_base + 0x2600)
                self.assertEqual(registrations(image), [])
