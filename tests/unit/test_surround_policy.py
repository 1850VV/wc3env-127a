import unittest

from tools.surround_policy import SurroundPolicy, ring_metrics


def unit(uid, x, y):
    return {"unit_id": uid, "x": x, "y": y, "hp": 220}


class SurroundPolicyTest(unittest.TestCase):
    def test_one_sided_pursuit_is_not_surround(self):
        target = unit(7, 0, 0)
        army = [unit(n, -50 - n * 10, n * 5) for n in range(6)]
        self.assertFalse(ring_metrics(army, target)["enclosed"])

    def test_four_cardinal_positions_cover_target(self):
        army = [unit(0, 62, 0), unit(1, 0, 62), unit(2, -62, 0), unit(3, 0, -62)]
        self.assertTrue(ring_metrics(army, unit(7, 0, 0))["enclosed"])
        self.assertTrue(ring_metrics(army, unit(7, 0, 0))["conservative_circle_sealed"])

    def test_visual_ring_alone_does_not_trigger_hold(self):
        policy = SurroundPolicy(list(range(6)))
        policy.phase = "close"
        policy.anchor = (0, 0)
        army = [unit(0, 62, 0), unit(1, 0, 62), unit(2, -62, 0), unit(3, 0, -62)]
        policy.act(0, army, unit(7, 0, 0))
        self.assertEqual(policy.phase, "close")
        policy.act(1, army, unit(7, 0, 0))
        self.assertEqual(policy.phase, "close")
        policy.act(2.1, army, unit(7, 0, 0))
        self.assertEqual(policy.phase, "hold")

    def test_closing_destinations_remain_fixed_as_target_moves(self):
        policy = SurroundPolicy(list(range(6)))
        policy.phase = "close"
        policy.anchor = (100, 0)
        army = [unit(n, -100, n * 80) for n in range(6)]
        first = policy.act(0, army, unit(7, 0, 0))
        second = policy.act(0.5, army, unit(7, 30, 0))
        self.assertEqual([a["arguments"] for a in first], [a["arguments"] for a in second])

    def test_missing_target_produces_no_actions(self):
        self.assertEqual(SurroundPolicy(list(range(6))).act(0, [], None), [])
