"""Replay recorded RPC movement for both players, then handle EOF without a result.

Record native orders on the pinned installation, then independently replay them.
The live trace covers both players at every second from 1 through 51; neither
setup mutations nor a digest from another game version can satisfy this test.
"""

import tempfile
import unittest
from pathlib import Path

from wc3env import Action
from wc3env.game import launch
from wc3env.rpc import RpcError
from wc3env.session import GameConfig, GameSession, PlayerConfig

from .support import state


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="wc3-replay-")
        cls.addClassCleanup(temporary.cleanup)
        cls.replay = Path(temporary.name) / "self_play.w3g"
        config = GameConfig(players=(PlayerConfig(0), PlayerConfig(1)), render=False, sound=False)
        with GameSession(config) as session:
            views = session.reset()
            session.debug("speed", factor=64)
            session.debug("waitfloor", ms=1)
            cls.trace = [state(views)]
            for tick in range(50):
                batches = {0: [], 1: []}
                if tick in (0, 10, 20, 30):
                    for player, obs in views.items():
                        unit = next(u for u in obs["units"] if not u["structure"])
                        batches[player] = [
                            Action(
                                unit["unit_id"],
                                "move",
                                dict(x=unit["x"] + (200 if tick % 20 == 0 else -200), y=unit["y"] - 100),
                            )
                        ]
                views, done, info = session.step(batches)
                assert not done and not any(info["rejected"].values()), info
                cls.trace.append(state(views))
            session.save_replay(cls.replay)

    def test_recorded_two_player_actions_and_eof(self):
        replay = self.replay
        game = launch(map=replay, agents=(0, 1), render=False)
        self.addCleanup(game.close)
        rpc = game.rpc
        players = [{"slot": p, "control": "agent"} for p in (0, 1)]
        with self.assertRaisesRegex(RpcError, "requires stepping mode"):
            rpc.create_game(str(replay), players, "realtime")
        rpc.create_game(str(replay), players)
        rpc.debug("speed", factor=64)
        rpc.debug("waitfloor", ms=1)
        trace = [state({p: rpc.observe(p) for p in (0, 1)})]
        with self.assertRaisesRegex(RpcError, "replay actions"):
            rpc.act(0, [])
        for tick in range(50):
            result = rpc.step(1000)
            self.assertEqual(result["elapsed_ms"], 1000)
            self.assertEqual(result["reason"], "replay_end" if tick == 49 else "target")
            trace.append(state({p: rpc.observe(p) for p in (0, 1)}))
        self.assertEqual(trace, self.trace)
        self.assertEqual(rpc.status, "ended")
        with self.assertRaises(RpcError):
            rpc.step(1000)
        with self.assertRaisesRegex(RpcError, "replay reset requires a new process"):
            rpc.reset()
        self.assertEqual(state({p: rpc.observe(p) for p in (0, 1)}), trace[-1])

    def test_session_step_stops_at_replay_end_without_inventing_results(self):
        replay = self.replay
        with GameSession(
            GameConfig(
                map=str(replay),
                players=(PlayerConfig(0), PlayerConfig(1)),
                render=False,
                step_ms=60000,
                max_episodes_per_process=None,
            )
        ) as session:
            pids = []
            starts = []
            for _ in range(2):
                starts.append(state(session.reset()))
                pids.append(session.game.pid)
                session.game.rpc.debug("speed", factor=64)
                session.game.rpc.debug("waitfloor", ms=1)
                observations, done, info = session.step({0: [], 1: []})
                self.assertTrue(done)
                self.assertEqual((info["elapsed_ms"], info["step_reason"]), (50000, "replay_end"))
                self.assertEqual([observations[p]["result"] for p in (0, 1)], ["", ""])
            self.assertNotEqual(*pids)
            self.assertEqual(*starts)


if __name__ == "__main__":
    unittest.main()
