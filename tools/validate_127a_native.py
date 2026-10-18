"""Bounded real-game recovery check: isolated offline sessions, no source changes.

Preserves observations/actions and failures. Combat units are explicitly staged
using existing debug spawn; movement and construction use normal starting units.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

from wc3env import Action, GameConfig, GameSession, MatchSetup, PlayerConfig, StepPool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["WC3_SOUND"] = "0"
    results, processes = {}, []
    started = time.perf_counter()

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(kind, **value):
        with (out / "trace.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind, **value}, ensure_ascii=False) + "\n")

    def check(name, passed, **evidence):
        results[name] = {"status": "PASS" if passed else "FAIL", **evidence}
        save("result.json", {"checks": results, "processes": processes})
        print(json.dumps({name: results[name]}), flush=True)

    def remember(game):
        entry = {"pid": game.pid, "data_dir": str(game.data_dir), "map": str(game.map)}
        if entry not in processes:
            processes.append(entry)
            record("process", **entry)

    def cfg(**values):
        return GameConfig(
            map="(2)EchoIsles.w3x",
            players=(PlayerConfig(0, "human"), PlayerConfig(1, "human")),
            render=False,
            sound=False,
            step_ms=250,
            setup=MatchSetup(seed=21),
            output_dir=args.runtime,
            **values,
        )

    def observe(session, label):
        observations = {p: session.game.rpc.observe(p) for p in session.config.agent_slots}
        session.observations = observations
        record("observe", label=label, observations=observations)
        return observations

    def step(session, actions=None, ms=250, label="step"):
        actions = actions or {0: [], 1: []}
        obs, done, info = session.step(actions, ms=ms)
        record(
            "step",
            label=label,
            actions={p: [a.to_dict() for a in batch] for p, batch in actions.items()},
            observations=obs,
            done=done,
            info=info,
        )
        return obs, done, info

    def unit(observations, slot, uid):
        return next(u for u in observations[slot]["units"] if u["unit_id"] == uid)

    def canonical(observations):
        return [
            {
                "time": o["game_time_seconds"],
                "player": o["player"],
                "score": o["score"],
                "result": o["result"],
                "units": sorted(
                    [u[k] for k in ("type_id", "owner", "x", "y", "hp", "mana", "level")] for u in o["units"]
                ),
            }
            for o in observations.values()
        ]

    try:
        with GameSession(cfg()) as s:
            initial = s.reset()
            remember(s.game)
            record("reset", observations=initial, info=s.game.rpc.info())
            check("connect", bool(initial[0]["units"]), pid=s.game.pid, rpc_info=s.game.rpc.info())
            valid = all(math.isfinite(u[k]) for o in initial.values() for u in o["units"] for k in ("x", "y", "hp"))
            check(
                "observations",
                valid and all(u["hp"] > 0 for u in initial[0]["units"]),
                player=initial[0]["player"],
                starting_units=initial[0]["units"],
            )
            t0 = initial[0]["game_time_seconds"]
            time.sleep(0.3)
            held = observe(s, "held")
            check(
                "pause",
                held[0]["game_time_seconds"] == t0,
                wall_wait_seconds=0.3,
                before=t0,
                after=held[0]["game_time_seconds"],
            )
            s.debug("speed", factor=64)
            s.debug("waitfloor", ms=1)
            before_step = held[0]["game_time_seconds"]
            after_step, _, info = step(s, ms=25, label="25ms")
            check(
                "step",
                abs(after_step[0]["game_time_seconds"] - before_step - 0.025) < 1e-9,
                before=before_step,
                after=after_step[0]["game_time_seconds"],
                info=info,
            )
            worker = next(u for u in after_step[0]["units"] if u["type_id"] == "hpea")
            hall = next(u for u in after_step[0]["units"] if u["type_id"] == "htow")
            direction = 1 if hall["x"] < 0 else -1
            move = Action(worker["unit_id"], "move", {"x": worker["x"] + direction * 400, "y": worker["y"] - 100})
            obs, _, info = step(s, {0: [move], 1: []}, label="move")
            rejected = info["rejected"]
            for _ in range(11):
                obs, _, _ = step(s)
            moved = unit(obs, 0, worker["unit_id"])
            distance = math.hypot(moved["x"] - worker["x"], moved["y"] - worker["y"])
            check(
                "move",
                distance > 100 and not rejected[0],
                distance=distance,
                before={k: worker[k] for k in ("unit_id", "x", "y", "hp")},
                after={k: moved[k] for k in ("unit_id", "x", "y", "hp", "order")},
            )
            money_before = obs[0]["player"].copy()
            build = Action(worker["unit_id"], "build", {"type_id": "hhou", "x": hall["x"], "y": hall["y"] - 640})
            events, farm = [], None
            for tick in range(120):
                obs, _, info = step(s, {0: [build] if tick == 0 else [], 1: []}, ms=500, label="build")
                events.extend(obs[0]["events"])
                farms = [u for u in obs[0]["units"] if u["type_id"] == "hhou"]
                if farms:
                    farm = farms[0]
                if any(e["kind"] == "construct_finish" and e.get("type_id") == "hhou" for e in events):
                    break
            construction_events = [e for e in events if e.get("type_id") == "hhou"]
            passed = bool(
                farm
                and farm["state"] is None
                and any(e["kind"] == "construct_start" for e in construction_events)
                and any(e["kind"] == "construct_finish" for e in construction_events)
                and obs[0]["player"]["gold"] < money_before["gold"]
            )
            check("build", passed, before=money_before, after=obs[0]["player"], farm=farm, events=construction_events)
            # Isolated combat staging is explicit; no hp mutation or damage debug call is used.
            combat_ids = [
                s.debug("spawn", type_id="hfoo", player=p, x=hall["x"] + direction * (400 + p * 60), y=hall["y"] - 400)[
                    "unit_ids"
                ][0]
                for p in (0, 1)
            ]
            obs = observe(s, "combat-staged")
            hp_before = unit(obs, 1, combat_ids[1])["hp"]
            hp_trace, combat_events = [], []
            for tick in range(32):
                batch = {
                    p: [Action(combat_ids[p], "attack", {"target_id": combat_ids[1 - p]})] if tick == 0 else []
                    for p in (0, 1)
                }
                obs, _, _ = step(s, batch, label="attack")
                hp_trace.append([unit(obs, p, combat_ids[p])["hp"] for p in (0, 1)])
                combat_events.extend(obs[0]["events"])
            check(
                "attack",
                hp_trace[-1][1] < hp_before,
                staging="two debug-spawned Footmen; no debug damage",
                hp_before=hp_before,
                hp_trace=hp_trace,
                events=combat_events,
            )
            speed_samples = []
            for factor in (1, 64):
                s.debug("speed", factor=factor)
                begin = time.perf_counter()
                before = obs[0]["game_time_seconds"]
                obs, _, _ = step(s, ms=1000, label=f"speed-{factor}")
                speed_samples.append(
                    {
                        "factor": factor,
                        "wall_seconds": time.perf_counter() - begin,
                        "simulated_seconds": obs[0]["game_time_seconds"] - before,
                    }
                )
            check(
                "acceleration",
                speed_samples[1]["wall_seconds"] < speed_samples[0]["wall_seconds"],
                samples=speed_samples,
            )
            pid = s.game.pid
            reset = s.reset()
            record("reset-after-mutation", observations=reset)
            check(
                "reset",
                s.game.pid == pid and canonical(reset) == canonical(initial),
                before_pid=pid,
                after_pid=s.game.pid,
                time=reset[0]["game_time_seconds"],
                player=reset[0]["player"],
                types=sorted(u["type_id"] for u in reset[0]["units"]),
            )
        # Direct script invocation puts tools/, rather than the repository, on sys.path.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        # Existing native regression checks seeded combat, in-process reset and process recycling.
        import unittest

        from tests.e2e.test_match_setup import MatchSetupTest

        test = MatchSetupTest("test_seed_repeats_races_positions_and_combat_after_reset")
        native_result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([test]))
        check(
            "determinism",
            native_result.wasSuccessful(),
            test="tests.e2e.test_match_setup.MatchSetupTest.test_seed_repeats_races_positions_and_combat_after_reset",
            scope="3 seeded combat traces, 32 samples each, same process then replacement; not arbitrary full matches",
        )
        configs = [
            GameConfig(
                map="(2)EchoIsles.w3x",
                players=(PlayerConfig(0, race),),
                render=False,
                sound=False,
                step_ms=250,
                setup=MatchSetup(seed=seed),
                output_dir=args.runtime,
            )
            for race, seed in (("orc", 31), ("undead", 73))
        ]
        pool = StepPool.launch_configs(configs, speed=64)
        try:
            for game in pool.games:
                remember(game)
            initial = [g.rpc.observe(0) for g in pool.games]
            pool.games[0].rpc.step(250)
            isolated = [g.rpc.observe(0) for g in pool.games]
            steps = [pool.step_all() for _ in range(4)]
            final = [g.rpc.observe(0) for g in pool.games]
            record("pool", initial=initial, isolated=isolated, steps=steps, final=final)
            passed = len({g.pid for g in pool.games}) == 2 and len({str(g.data_dir) for g in pool.games}) == 2
            passed = passed and isolated[1]["game_time_seconds"] == initial[1]["game_time_seconds"]
            passed = passed and all(r["elapsed_ms"] == 250 and r["reason"] == "target" for row in steps for r in row)
            check(
                "two_instances",
                passed,
                pids=[g.pid for g in pool.games],
                directories=[str(g.data_dir) for g in pool.games],
                initial_times=[o["game_time_seconds"] for o in initial],
                isolated_times=[o["game_time_seconds"] for o in isolated],
                final_times=[o["game_time_seconds"] for o in final],
                steps=steps,
            )
        finally:
            pool.close()
    except Exception:
        results["exception"] = {"status": "FAIL", "traceback": traceback.format_exc()}
        traceback.print_exc()
    finally:
        for name in (
            "connect",
            "observations",
            "move",
            "attack",
            "build",
            "pause",
            "step",
            "reset",
            "determinism",
            "two_instances",
        ):
            results.setdefault(name, {"status": "NOT RUN"})
        save(
            "result.json",
            {
                "checks": results,
                "processes": processes,
                "wall_seconds": time.perf_counter() - started,
                "hook_path": os.environ.get("WC3_HOOK_DLL"),
                "trace_sha256": hashlib.sha256((out / "trace.jsonl").read_bytes()).hexdigest(),
            },
        )
    return 0 if all(v["status"] == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
