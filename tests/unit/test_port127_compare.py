"""Synthetic comparison validation; these tests do not run Warcraft."""

import copy
import unittest

from tools.port127.compare import compare, observations


class ReplayComparisonTests(unittest.TestCase):
    def setUp(self):
        self.log = "\n".join(
            f"unit_observation target={time} id=00001000 type=68706561 owner=0 x=3f800000 y=40000000 hp=43fa0000 visible=1"
            for time in (1000, 1025, 1275, 2275, 7275)
        )
        self.record = {
            "kind": "live_native_research_probe",
            "mode": "record",
            "passed": True,
            "owned_processes_cleaned": [True],
            "binary_hashes": {"Game.dll": "test-hash"},
            "instances": [
                {"replay_recorded": True, "replay_sha256": "same-bytes", "worker_states": [{"order": 851986}]}
            ],
        }
        self.playback = copy.deepcopy(self.record)
        self.playback["mode"] = "playback"
        for report in (self.record, self.playback):
            report["instances"][0]["object_snapshots"] = [
                {"phase": "update", "target_ms": target, "count": 1} for target in (1000, 1025, 1275, 2275, 7275)
            ]

    def test_float_bit_difference_is_not_hidden_by_decimal_rounding(self):
        result = compare(self.record, self.playback, self.log, self.log.replace("3f800000", "3f800001", 1))
        self.assertFalse(result["passed"])
        self.assertEqual(result["different_unit_snapshots"], 1)

    def test_equal_replay_is_explicitly_scoped(self):
        result = compare(self.record, self.playback, self.log, self.log)
        self.assertTrue(result["passed"])
        self.assertEqual(result["wc3env_game_acceptance"], "NOT_RUN")

    def test_missing_checkpoint_and_duplicate_unit_are_errors(self):
        for log in (self.log.split("\n", 1)[1], self.log + "\n" + self.log.splitlines()[0]):
            with self.assertRaises(ValueError):
                observations(log)

    def test_partial_unit_log_cannot_pass(self):
        self.playback["instances"][0]["object_snapshots"][0]["count"] = 2
        with self.assertRaisesRegex(ValueError, "incomplete"):
            compare(self.record, self.playback, self.log, self.log)

    def test_second_players_orders_are_compared(self):
        self.record["players"] = self.playback["players"] = 2
        self.record["instances"][0]["other_worker_states"] = [{"order": 851986}]
        self.playback["instances"][0]["other_worker_states"] = [{"order": 0}]
        self.assertFalse(compare(self.record, self.playback, self.log, self.log)["passed"])

    def test_wrong_replay_or_failed_run_cannot_pass(self):
        for invalid in ("bytes", "failed", "cleanup", "mode", "engine"):
            with self.subTest(invalid=invalid):
                playback = copy.deepcopy(self.playback)
                if invalid == "bytes":
                    playback["instances"][0]["replay_sha256"] = "different"
                elif invalid == "failed":
                    playback["passed"] = False
                elif invalid == "cleanup":
                    playback["owned_processes_cleaned"] = [False]
                elif invalid == "mode":
                    playback["mode"] = "record"
                else:
                    playback["binary_hashes"] = {}
                with self.assertRaises(ValueError):
                    compare(self.record, playback, self.log, self.log)
