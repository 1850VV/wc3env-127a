"""Playback of a recorded game with building, heroes, spells and deaths must reproduce it exactly.

The test records a fresh 1.27a match through the public session API, captures its
live digest and event kinds, then checks independent playback against that evidence.
"""

import tempfile
import unittest
from pathlib import Path

from tests.e2e.support import state
from wc3env.game import launch

from .record_combat_replay import PLAYERS, digest, record

RECORDED_KINDS = {"construct_finish", "train_finish", "hero_learn", "spell_effect", "attacked", "death"}


class CombatReplayTest(unittest.TestCase):
    def test_playback_matches_the_live_game(self):
        temporary = tempfile.TemporaryDirectory(prefix="wc3-combat-replay-")
        self.addCleanup(temporary.cleanup)
        fixture = Path(temporary.name) / "combat.w3g"
        live_digest, seconds, recorded = record(fixture)
        for player in PLAYERS:
            self.assertLessEqual(RECORDED_KINDS, set(recorded[player]), f"live player {player}")
        game = launch(map=fixture, agents=PLAYERS, render=False)
        self.addCleanup(game.close)
        rpc = game.rpc
        rpc.create_game(str(fixture), [{"slot": p, "control": "agent"} for p in PLAYERS])
        rpc.debug("speed", factor=64)
        rpc.debug("waitfloor", ms=1)
        observations = {p: rpc.observe(p) for p in PLAYERS}
        trace, kinds = [state(observations)], {p: set() for p in PLAYERS}
        for second in range(seconds):
            result = rpc.step(1000)
            self.assertEqual(result["reason"], "replay_end" if second == seconds - 1 else "target")
            observations = {p: rpc.observe(p) for p in PLAYERS}
            for p in PLAYERS:
                kinds[p] |= {e["kind"] for e in observations[p]["events"]}
            trace.append(state(observations))
        for p in PLAYERS:
            self.assertLessEqual(RECORDED_KINDS, kinds[p], f"player {p}")
        self.assertEqual(digest(trace), live_digest)
        self.assertEqual(rpc.status, "ended")


if __name__ == "__main__":
    unittest.main()
