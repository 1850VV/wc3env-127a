"""Real-game surround acceptance: six Footmen physically block a moving Peasant."""

import argparse
import json
import math
import time
from pathlib import Path

from tools.surround_policy import SurroundPolicy, ring_metrics
from wc3env import GameConfig, GameSession, MatchSetup, PlayerConfig

STARTS = ((-1100, 110), (-1180, 230), (-1260, 80), (-1180, -230), (-1260, -80), (-1100, -110))


def run(out, seed=42, visible=False, record=False, wait=0):
    out.mkdir(parents=True, exist_ok=True)
    config = GameConfig(
        map=str(Path("build/maps/(2)KitingArena.w3x").resolve()),
        players=(PlayerConfig(0, "human"), PlayerConfig(1, "human")),
        setup=MatchSetup(seed=seed),
        computer_agents=(1,),
        step_ms=50,
        render=visible,
        background_visible=visible,
        sound=False,
    )
    trace = []
    rejected = []
    with GameSession(config) as session:
        session.reset()
        session.debug("speed", factor=64)
        session.debug("waitfloor", ms=1)
        hero = session.debug("spawn", type_id="Hamg", player=0, x=-1550, y=0)["unit_ids"][0]
        footmen = [session.debug("spawn", type_id="hfoo", player=0, x=x, y=y)["unit_ids"][0] for x, y in STARTS]
        farmer = session.debug("spawn", type_id="hpea", player=1, x=-750, y=0)["unit_ids"][0]
        session.debug("camera", x=-1050, y=0)
        obs, _, _ = session.step({0: [], 1: []})
        policy = SurroundPolicy(footmen)
        if visible:
            session.game.resize(1280, 800)
        print(json.dumps({"ready": True, "pid": session.game.pid, "windows": session.game.windows()}), flush=True)
        if wait:
            time.sleep(wait)
        capture = None
        if record:
            from tools.surround_video import Capture

            capture = Capture(session.game, out)
        start = obs[0]["game_time_seconds"]
        initial = None
        stable_since = None
        stable_point = None
        trapped = None
        peak_stable = 0
        last_phase = None
        try:
            for tick in range(1000):
                now = obs[0]["game_time_seconds"] - start
                target = next((u for u in obs[1]["units"] if u["unit_id"] == farmer and u["hp"] > 0), None)
                army = [u for u in obs[0]["units"] if u["unit_id"] in footmen and u["hp"] > 0]
                if initial is None and target:
                    initial = {"target": target, "army": army}
                metrics = (
                    ring_metrics(army, target)
                    if target
                    else {"enclosed": False, "nearby": 0, "largest_gap_degrees": 360}
                )
                if target and metrics["enclosed"] and (target.get("order") or {}).get("name") == "move":
                    if (
                        stable_since is None
                        or math.hypot(target["x"] - stable_point[0], target["y"] - stable_point[1]) > 35
                    ):
                        stable_since, stable_point = now, (target["x"], target["y"])
                    stable = now - stable_since
                    peak_stable = max(peak_stable, stable)
                    if stable >= 2 and trapped is None:
                        trapped = {
                            "t": now,
                            "duration": stable,
                            "position": stable_point,
                            "hp": target["hp"],
                            "order": target["order"],
                            **metrics,
                        }
                else:
                    stable_since = None
                row = {
                    "t": round(now, 3),
                    "phase": policy.phase,
                    "target": target,
                    "army": army,
                    "metrics": metrics,
                    "stable_seconds": 0 if stable_since is None else round(now - stable_since, 3),
                    "trapped": trapped is not None,
                }
                trace.append(row)
                if capture and tick % 2 == 0:
                    capture.frame(row)
                if target is None or (trapped and now - trapped["t"] >= 3):
                    break
                seen = next((u for u in obs[0]["visible_enemies"] if u["unit_id"] == farmer), None)
                ours = policy.act(now, army, seen)
                # The Archmage follows well behind, out of attack range; only Footmen surround.
                if tick % 20 == 0 and seen:
                    ours.append(
                        {"unit_id": hero, "command": "move", "arguments": {"x": seen["x"] - 850, "y": seen["y"]}}
                    )
                theirs = [{"unit_id": farmer, "command": "move", "arguments": {"x": 3100, "y": 0}}] if tick == 0 else []
                row["actions"] = ours
                if visible and tick % 6 == 0:
                    session.debug("camera", x=target["x"] - 180, y=target["y"])
                obs, done, info = session.step({0: ours, 1: theirs})
                rejected.extend({"t": now, "player": p, **r} for p, rs in info["rejected"].items() for r in rs)
                if policy.phase != last_phase or tick % 100 == 0:
                    print(
                        f"t={now:.2f} phase={policy.phase} farmer=({target['x']:.0f},{target['y']:.0f}) hp={target['hp']:.0f} near={metrics['nearby']} gap={metrics['largest_gap_degrees']:.0f} stable={peak_stable:.2f}",
                        flush=True,
                    )
                    last_phase = policy.phase
                if done:
                    break
            result = {
                "seed": seed,
                "success": trapped is not None and not rejected,
                "trapped": trapped,
                "elapsed_game_seconds": trace[-1]["t"],
                "initial": initial,
                "final": trace[-1],
                "peak_stable_seconds": peak_stable,
                "rejected": rejected,
                "game_info": session.game.rpc.info(),
                "scope": "Real 1.27a; native unit stats; open arena; 6 footmen + passive rear Archmage; Peasant receives one rightward move order",
            }
            (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
            (out / "trace.json").write_text(json.dumps(trace), encoding="utf8")
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in ("success", "trapped", "elapsed_game_seconds", "peak_stable_seconds", "rejected")
                    }
                ),
                flush=True,
            )
            if capture:
                for _ in range(20):
                    capture.frame(trace[-1])
            return result
        finally:
            if capture:
                capture.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("runs/surround-mvp/run1"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--ready-wait", type=float, default=0)
    args = parser.parse_args()
    if args.record and not args.visible:
        parser.error("--record requires --visible")
    result = run(args.out, args.seed, args.visible, args.record, args.ready_wait)
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
