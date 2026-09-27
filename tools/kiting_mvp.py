"""Real WC3 1.27a Archmage versus Footman, with standing baseline and JSON evidence."""

import argparse
import json
import math
import time
from contextlib import ExitStack
from pathlib import Path

from tools.kiting_policy import KitingPolicy
from wc3env import GameConfig, GameSession, MatchSetup, PlayerConfig


def run(mode, out, seed=42, visible=False, realtime=False, ready_wait=0, record=False):
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
    trace, damage, rejections = [], [], []
    orders = {"attack": 0, "move": 0}
    policy = KitingPolicy()
    with GameSession(config) as session, ExitStack() as resources:
        session.reset()
        session.debug("speed", factor=1 if realtime else 64)
        session.debug("waitfloor", ms=1)
        hero_id = session.debug("spawn", type_id="Hamg", player=0, x=0, y=0)["unit_ids"][0]
        enemy_id = session.debug("spawn", type_id="hfoo", player=1, x=520, y=0)["unit_ids"][0]
        session.debug("camera", x=150, y=0)
        if visible:
            session.game.resize(1280, 800)
        session.step({0: [], 1: []})
        obs, _, _ = session.step({0: [{"unit_id": hero_id, "command": "select"}], 1: []})
        print(
            json.dumps({"ready": True, "pid": session.game.pid, "windows": session.game.windows(), "mode": mode}),
            flush=True,
        )
        if ready_wait:
            time.sleep(ready_wait)
        capture = None
        if record:
            from tools.kiting_video import Capture

            capture = Capture(session.game, out)
            resources.callback(capture.close)
        start = obs[0]["game_time_seconds"]
        wall_start = time.monotonic()
        hero = next(u for u in obs[0]["units"] if u["unit_id"] == hero_id)
        enemy = next(u for u in obs[1]["units"] if u["unit_id"] == enemy_id)
        initial = {"hero_hp": hero["hp"], "enemy_hp": enemy["hp"], "hero": hero, "enemy": enemy}
        last_hero_hp, last_enemy_hp = hero["hp"], enemy["hp"]
        last_camera = -1.0
        for tick in range(3600):
            now = obs[0]["game_time_seconds"] - start
            hero = next((u for u in obs[0]["units"] if u["unit_id"] == hero_id and u["hp"] > 0), None)
            enemy = next((u for u in obs[1]["units"] if u["unit_id"] == enemy_id and u["hp"] > 0), None)
            hp, ehp = (hero["hp"] if hero else 0), (enemy["hp"] if enemy else 0)
            if hp < last_hero_hp - 0.1 or ehp < last_enemy_hp - 0.1:
                damage.append({"t": now, "hero_hp": hp, "enemy_hp": ehp})
            last_hero_hp, last_enemy_hp = hp, ehp
            row = {
                "t": round(now, 3),
                "hero_hp": hp,
                "enemy_hp": ehp,
                "phase": policy.phase,
                "hero": {k: hero[k] for k in ("x", "y", "order")} if hero else None,
                "enemy": {k: enemy[k] for k in ("x", "y", "order")} if enemy else None,
            }
            trace.append(row)
            if capture is not None and tick % 2 == 0:
                capture.frame(row, mode)
            if not hero or not enemy:
                break
            if mode == "baseline":
                ours = (
                    [{"unit_id": hero_id, "command": "attack", "arguments": {"target_id": enemy_id}}]
                    if tick == 0
                    else []
                )
            else:
                # Controller reads player 0's fog-filtered view, never player 1's privileged state.
                seen = next((u for u in obs[0]["visible_enemies"] if u["unit_id"] == enemy_id), None)
                ours = policy.act(now, hero, seen, obs[0]["events"])
            theirs = (
                [{"unit_id": enemy_id, "command": "attack", "arguments": {"target_id": hero_id}}] if tick == 0 else []
            )
            for action in ours:
                if action["command"] in orders:
                    orders[action["command"]] += 1
            row["actions"] = ours
            if visible and now - last_camera >= 0.25:
                last_camera = now
                session.debug("camera", x=(hero["x"] + enemy["x"]) / 2, y=(hero["y"] + enemy["y"]) / 2)
                session.game.rpc.overlay(
                    f"{mode.upper()}  {now:.1f}s | Archmage {hp:.0f}/{initial['hero_hp']:.0f} HP | Footman {ehp:.0f} HP | {policy.phase}",
                    x=-0.30,
                    y=0.55,
                    seconds=1,
                )
            obs, done, info = session.step({0: ours, 1: theirs})
            for player, rejected in info["rejected"].items():
                rejections.extend({"t": now, "player": player, **r} for r in rejected)
            if realtime:
                time.sleep(max(0, wall_start + (obs[0]["game_time_seconds"] - start) - time.monotonic()))
            if tick % 200 == 0:
                print(
                    f"{mode} t={now:.1f} hp={hp:.1f} enemy={ehp:.1f} gap={math.hypot(hero['x'] - enemy['x'], hero['y'] - enemy['y']):.0f} phase={policy.phase}",
                    flush=True,
                )
            if done:
                break
        if capture is not None:
            for _ in range(20):
                capture.frame(trace[-1], mode)
            capture.close()
        result = {
            "mode": mode,
            "seed": seed,
            "scope": "Real Warcraft III 1.27a; staged flat arena; level-1 units; no items/spells/stat changes",
            "elapsed_game_seconds": trace[-1]["t"],
            "wall_seconds": time.monotonic() - wall_start,
            "initial": initial,
            "hero_hp": trace[-1]["hero_hp"],
            "enemy_hp": trace[-1]["enemy_hp"],
            "won": trace[-1]["enemy_hp"] == 0 and trace[-1]["hero_hp"] > 0,
            "orders": orders,
            "rejected": rejections,
            "damage_samples": damage,
            "game_info": session.game.rpc.info(),
            "game_dir": str(session.game.data_dir),
        }
        result["observed_damage_taken"] = sum(max(0, a["hero_hp"] - b["hero_hp"]) for a, b in zip(trace, trace[1:]))
        result["observed_enemy_damage"] = sum(max(0, a["enemy_hp"] - b["enemy_hp"]) for a, b in zip(trace, trace[1:]))
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (out / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in ("mode", "won", "hero_hp", "enemy_hp", "elapsed_game_seconds", "orders", "rejected")
                }
            ),
            flush=True,
        )
        if visible:
            session.game.rpc.overlay(
                f"FINISHED: {mode} | Archmage HP {result['hero_hp']:.0f} | Footman HP {result['enemy_hp']:.0f}",
                seconds=30,
            )
            time.sleep(5)
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "kite"), default="kite")
    parser.add_argument("--out", type=Path, default=Path("runs/kiting-mvp/kite"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--ready-wait", type=float, default=0)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if args.record and not args.visible:
        parser.error("--record requires --visible")
    result = run(args.mode, args.out, args.seed, args.visible, args.realtime, args.ready_wait, args.record)
    if result["rejected"] or (args.mode == "kite" and not result["won"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
