"""Observation-only Archmage attack/retreat policy. No game mutation or model calls."""

import math


def retreat_point(hero, enemy, radius=1800.0):
    """Choose an open-arena escape direction while avoiding the arena perimeter."""
    candidates = []
    for i in range(32):
        angle = i * math.tau / 32
        x, y = hero["x"] + 320 * math.cos(angle), hero["y"] + 320 * math.sin(angle)
        separation = math.hypot(x - enemy["x"], y - enemy["y"])
        edge = max(0.0, math.hypot(x, y) - radius)
        candidates.append((separation - 4 * edge, x, y))
    _, x, y = max(candidates)
    return x, y


class KitingPolicy:
    def __init__(self):
        self.phase = "ready"
        self.attack_started = None
        self.shot_started = None
        self.last_shot = -100.0
        self.last_move = -100.0

    def act(self, now, hero, enemy, events):
        if not hero or not enemy or hero["hp"] <= 0 or enemy["hp"] <= 0:
            self.phase = "finished"
            return []
        distance = math.hypot(hero["x"] - enemy["x"], hero["y"] - enemy["y"])
        for event in events:
            if event["kind"] == "attacked" and event.get("attacker_id") == hero["unit_id"]:
                self.shot_started = now
        if self.phase == "attack":
            # 'attacked' marks wind-up, not a landed projectile. Preserve the attack point.
            if self.shot_started is not None and now - self.shot_started >= 0.50:
                self.last_shot = self.shot_started
                self.phase = "retreat"
            elif now - self.attack_started < 1.5:
                return []
            else:
                # An accepted order can fail to fire. Retreat, then retry from observed state.
                self.phase = "retreat"
        if now - self.last_shot >= 3.8 and 500 <= distance <= 590:
            self.phase = "attack"
            self.attack_started = now
            self.shot_started = None
            return [{"unit_id": hero["unit_id"], "command": "attack", "arguments": {"target_id": enemy["unit_id"]}}]
        self.phase = "retreat"
        if now - self.last_move < 0.35:
            return []
        self.last_move = now
        if distance > 575:
            # Let the pursuer close without accidentally auto-attacking.
            return [{"unit_id": hero["unit_id"], "command": "cast", "arguments": {"order": "holdposition"}}]
        x, y = retreat_point(hero, enemy)
        return [{"unit_id": hero["unit_id"], "command": "move", "arguments": {"x": x, "y": y}}]
