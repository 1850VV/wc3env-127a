"""Localized extraction preserves bytes and existing command names, not stale balance."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.prepare.gamedata import read_all
from tools.prepare.reference import preserve_names


class ReferencePreparationTest(unittest.TestCase):
    def test_localized_text_and_binary_texture_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "War3Patch.mpq").touch()
            archive = MagicMock()
            archive.__enter__.return_value = archive
            archive.has.return_value = True
            text = 'Name="农民"\nDescription="采集金矿"'
            texture = bytes(range(256))
            archive.read.side_effect = [text.encode("utf-8-sig"), texture]
            with patch("tools.prepare.gamedata.Archive", return_value=archive):
                files = read_all(["Units.txt", "Texture.tga"], root)
            self.assertEqual(files["Units.txt"], text)
            self.assertEqual(files["Texture.tga"].encode("latin-1"), texture)

    def test_name_reference_does_not_replace_mechanics_or_reorder_abilities(self):
        target = {"units": {"hpea": {"name": "农民", "gold": 75, "description": "current patch"}}}
        source = {"units": {"hpea": {"name": "Peasant", "gold": 999, "description": "old patch"}}}
        target["abilities"] = [
            {"ability_id": "A002", "name": "二", "mana_cost": 30},
            {"ability_id": "A001", "name": "一"},
        ]
        source["abilities"] = [
            {"ability_id": "A001", "name": "One"},
            {"ability_id": "A002", "name": "Two", "mana_cost": 999},
        ]
        preserve_names(target, source)
        self.assertEqual(target["units"]["hpea"], {"name": "Peasant", "gold": 75, "description": "current patch"})
        self.assertEqual(
            target["abilities"],
            [{"ability_id": "A002", "name": "Two", "mana_cost": 30}, {"ability_id": "A001", "name": "One"}],
        )
