"""Predictive four-cardinal surround, with two front flank reserves, on open ground."""

import math
from itertools import combinations

ROLES = ("east", "north", "west", "south", "northeast", "southeast")
SPREAD = ((190, 0), (60, 145), (-70, 0), (60, -145), (190, 100), (190, -100))
CLOSED = ((62, 0), (0, 62), (-62, 0), (0, -62), (118, 100), (118, -100))


def ring_metrics(units, target):
    near = [u for u in units if math.hypot(u["x"] - target["x"], u["y"] - target["y"]) <= 145]
    angles = sorted(math.atan2(u["y"] - target["y"], u["x"] - target["x"]) for u in near)
    gap = (
        max((b - a for a, b in zip(angles, angles[1:] + [angles[0] + math.tau])), default=math.tau)
        if angles
        else math.tau
    )
    sealed = False
    max_edge = None
    for count in range(4, len(near) + 1):
        for group in combinations(near, count):
            ordered = sorted(group, key=lambda u: math.atan2(u["y"] - target["y"], u["x"] - target["x"]))
            a = [math.atan2(u["y"] - target["y"], u["x"] - target["x"]) for u in ordered]
            if max(b - c for c, b in zip(a, a[1:] + [a[0] + math.tau])) >= math.pi:
                continue
            edge = max(math.hypot(u["x"] - v["x"], u["y"] - v["y"]) for u, v in zip(ordered, ordered[1:] + ordered[:1]))
            if edge <= 94:
                sealed = True
                max_edge = edge
    return {
        "nearby": len(near),
        "largest_gap_degrees": math.degrees(gap),
        "enclosed": len(near) >= 4 and gap < math.radians(125),
        "conservative_circle_sealed": sealed,
        "max_sealed_edge": max_edge,
    }


class SurroundPolicy:
    def __init__(self, ids):
        self.ids = ids
        self.phase = "intercept"
        self.previous = None
        self.velocity = (190.0, 0.0)
        self.last_send = -100
        self.hold_since = None
        self.hold_position = None
        self.anchor = None
        self.block_since = None
        self.block_point = None

    def act(self, now, units, target):
        if not target or target["hp"] <= 0:
            return []
        by_id = {u["unit_id"]: u for u in units}
        if self.previous:
            t, x, y = self.previous
            dt = now - t
            if dt > 0:
                measured = ((target["x"] - x) / dt, (target["y"] - y) / dt)
                self.velocity = tuple(0.65 * a + 0.35 * b for a, b in zip(self.velocity, measured))
        self.previous = (now, target["x"], target["y"])
        vx, vy = self.velocity
        east = by_id.get(self.ids[0])
        north, south = by_id.get(self.ids[1]), by_id.get(self.ids[3])
        if self.phase == "intercept" and east and north and south:
            front = east["x"] - target["x"]
            if (
                front >= 130
                and abs(east["y"] - target["y"]) < 110
                and all(math.hypot(u["x"] - target["x"], u["y"] - target["y"]) < 230 for u in (north, south))
            ):
                self.phase = "close"
                self.anchor = (target["x"] + 90, target["y"])
        metrics = ring_metrics(list(by_id.values()), target)
        if self.phase == "close" and metrics["enclosed"]:
            if (
                self.block_since is None
                or math.hypot(target["x"] - self.block_point[0], target["y"] - self.block_point[1]) > 35
            ):
                self.block_since = now
                self.block_point = (target["x"], target["y"])
            if now - self.block_since >= 2:
                self.phase = "hold"
                self.hold_since = now
                self.hold_position = (target["x"], target["y"])
        elif self.phase == "close":
            self.block_since = None
        if self.phase == "hold":
            if math.hypot(target["x"] - self.hold_position[0], target["y"] - self.hold_position[1]) > 100:
                self.phase = "close"
                self.hold_since = None
        if now - self.last_send < 0.15:
            return []
        self.last_send = now
        actions = []
        for index, uid in enumerate(self.ids):
            unit = by_id.get(uid)
            if not unit:
                continue
            dx, dy = (SPREAD if self.phase == "intercept" else CLOSED)[index]
            lead = 0.15
            if self.phase == "intercept":
                gap = max(0, target["x"] + dx - unit["x"])
                lead = min(5.0, gap / max(65, 270 - max(0, vx))) if index in (0, 4, 5) else 0.5
            if self.phase in ("close", "hold"):
                x, y = self.anchor[0] + dx, self.anchor[1] + dy
            else:
                x = target["x"] + dx + vx * lead
                y = target["y"] + dy + vy * lead
            # Front runner approaches above the fleeing unit instead of chasing its back.
            if index == 0 and self.phase == "intercept" and unit["x"] < target["x"] + 50:
                y += 100
            actions.append({"unit_id": uid, "command": "move", "arguments": {"x": x, "y": y}})
        return actions
