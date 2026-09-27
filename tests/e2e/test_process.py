"""Game processes: independent launches from any DLL path, and a server that cannot be stalled."""

import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from wc3env import GameConfig, GameSession, MatchSetup, PlayerConfig
from wc3env.game import hook_dll, launch
from wc3env.pipe import OverlappedPipeFile


class ProcessTest(unittest.TestCase):
    def test_presentation_switch_and_overlay_run_on_the_real_device(self):
        game = launch(render=True)
        self.addCleanup(game.close)
        game.rpc.create_game(str(game.map), [{"slot": 0, "control": "agent"}])
        game.rpc.debug("overlay", panel="Warcraft III 1.27a native adapter")
        game.rpc.debug("render", on=0)
        game.rpc.step(1000)
        game.rpc.debug("render", on=1)
        game.rpc.step(1000)
        log = game.log()
        self.assertIn("D3D9 presentation: suppressed", log)
        self.assertIn("D3D9 presentation: enabled", log)
        self.assertNotIn("native exception", log)

    def test_all_ai_difficulties_and_ai_backed_agent_startup(self):
        for difficulty in (0, 1, 2):
            with (
                self.subTest(difficulty=difficulty),
                GameSession(
                    GameConfig(
                        players=(PlayerConfig(0, "human"), PlayerConfig(1, "orc", "computer")),
                        ai_agents=(0,),
                        ai_difficulty=difficulty,
                        setup=MatchSetup(seed=41),
                        render=False,
                    )
                ) as session,
            ):
                before = session.reset()
                session.debug("speed", factor=64)
                session.debug("waitfloor", ms=1)
                for player in (0, 1):
                    self.assertEqual(session.debug("ai_difficulty", player=player)["ai_difficulty"], difficulty)
                for _ in range(30):
                    views, done, _ = session.step({0: []})
                    self.assertFalse(done)
                self.assertGreater(views[0]["score"]["gold_mined"], before[0]["score"]["gold_mined"])
                self.assertIn(f"original MeleeDifficulty()={difficulty + 1}", session.game.log())

    def test_unicode_dll_and_independent_default_launches(self):
        with tempfile.TemporaryDirectory(prefix="wc3 runtime ") as temp:
            dll = Path(temp) / "測試-hook.dll"
            shutil.copyfile(hook_dll(), dll)
            games = []
            try:
                with patch("wc3env.game.hook_dll", return_value=dll):
                    for _ in range(2):
                        games.append(launch(render=False, output_dir=temp))
                self.assertNotEqual(games[0].data_dir, games[1].data_dir)
                for g in games:
                    g.rpc.create_game(str(g.map), [{"slot": 0, "control": "agent"}], "stepping")
                    self.assertEqual(g.rpc.step(25)["elapsed_ms"], 25)
            finally:
                for g in games:
                    g.close()

    def test_server_disconnects_a_client_that_stops_reading(self):
        g = launch(render=False)
        self.addCleanup(g.close)
        g.pipe.close()
        deadline = time.monotonic() + 5
        while True:
            try:
                raw = OverlappedPipeFile(g.pipe.path)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        self.addCleanup(raw.close)
        start = time.monotonic()
        with self.assertRaises(OSError):
            for _ in range(64):
                raw.write(b"echo " + b"x" * 60000 + b"\n", timeout=12)
        self.assertLess(time.monotonic() - start, 10)
        self.assertIn("client stopped reading", g.log())
