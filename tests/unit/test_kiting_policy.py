import math
import unittest

from tools.kiting_policy import KitingPolicy, retreat_point


class KitingPolicyTest(unittest.TestCase):
    def setUp(self):
        self.hero = {"unit_id": 1, "hp": 450, "x": 0, "y": 0}
        self.enemy = {"unit_id": 2, "hp": 420, "x": 520, "y": 0}

    def test_preserves_windup_then_retreats(self):
        policy = KitingPolicy()
        self.assertEqual(policy.act(0, self.hero, self.enemy, [])[0]["command"], "attack")
        event = {"kind": "attacked", "attacker_id": 1}
        self.assertEqual(policy.act(0.05, self.hero, self.enemy, [event]), [])
        self.assertEqual(policy.act(0.4, self.hero, self.enemy, []), [])
        action = policy.act(0.6, self.hero, self.enemy, [])[0]
        self.assertEqual(action["command"], "move")
        self.assertLess(action["arguments"]["x"], 0)

    def test_enemy_attack_does_not_acknowledge_our_shot(self):
        policy = KitingPolicy()
        policy.act(0, self.hero, self.enemy, [])
        self.assertEqual(policy.act(0.6, self.hero, self.enemy, [{"kind": "attacked", "attacker_id": 2}]), [])
        self.assertEqual(policy.act(1.6, self.hero, self.enemy, [])[0]["command"], "attack")

    def test_close_pursuer_causes_retreat_and_missing_target_no_action(self):
        policy = KitingPolicy()
        self.enemy["x"] = 180
        self.assertEqual(policy.act(0, self.hero, self.enemy, [])[0]["command"], "move")
        self.assertEqual(policy.act(1, self.hero, None, []), [])

    def test_turns_before_open_arena_boundary(self):
        self.hero.update(x=-1800, y=0)
        self.enemy.update(x=-1400, y=0)
        x, y = retreat_point(self.hero, self.enemy)
        self.assertLess(math.hypot(x, y), 1850)
        self.assertGreater(abs(y), 100)
