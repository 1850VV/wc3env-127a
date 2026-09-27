"""Run the separately built 1.27a research DLL in private offline installations.

python -m tools.port127.probe --game-dir G:\\war3\\... --instances 2
This is a research harness, not a supported wc3env API adapter. Optional experiments
cover native step/producer budgets, object readback, command packets and replay recording.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from wc3env.inject import _export_rva, _launch_verified, k32

from .identity import verify_pair

ROOT = Path(__file__).resolve().parents[2]


def read_game_time(handle: int, address: int) -> int:
    """Independent host readback of the disassembled simulation-time field."""
    value = ctypes.c_uint32()
    read = ctypes.c_size_t()
    k32.ReadProcessMemory.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    k32.ReadProcessMemory.restype = ctypes.c_int
    if (
        not k32.ReadProcessMemory(handle, address + 0x1C70, ctypes.byref(value), 4, ctypes.byref(read))
        or read.value != 4
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return value.value


def prepare_runtime(source: Path, destination: Path, map_path: Path) -> Path:
    """Private writable EXE/DLL/map/output. MPQ archives may share read-only backing."""
    destination.mkdir(parents=True, exist_ok=False)
    for file in source.iterdir():
        if not file.is_file() or file.suffix.lower() not in (".dll", ".mpq") and file.name.lower() != "war3.exe":
            continue
        target = destination / file.name
        if file.suffix.lower() == ".mpq":
            try:
                os.link(file, target)
                continue
            except OSError:
                pass  # different volumes; a private copy is still correct
        shutil.copy2(file, target)
    for folder in ("Replay", "Logs", "Save", "CustomMapData", "Maps"):
        (destination / folder).mkdir()
    target_map = destination / "Maps" / map_path.name
    shutil.copy2(map_path, target_map)
    verify_pair(destination)
    return target_map


def run(
    game_dir: Path,
    output: Path,
    instances: int,
    seconds: float,
    steps: bool = False,
    speed: int = 0,
    actions: bool = False,
    record: bool = False,
    replay: Path | None = None,
    budget: bool = False,
    players: int = 1,
    events: bool = False,
    episodes: int = 1,
    objects: bool = False,
) -> dict:
    identity = verify_pair(game_dir)
    dll = ROOT / "wc3hook/out/probe127/wc3probe127.dll"
    # Do not accidentally run the 1.29 production hook through the research launcher.
    _export_rva(str(dll), b"WC3Probe127")
    map_path = game_dir / "Maps/FrozenThrone/(2)EchoIsles.w3x"
    if not map_path.is_file():
        raise FileNotFoundError(map_path)
    if replay and not replay.is_file():
        raise FileNotFoundError(replay)
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "kind": "live_native_research_probe",
        "wc3env_game_acceptance": "NOT_RUN",
        "binary_hashes": identity,
        "started_utc": datetime.now(UTC).isoformat(),
        "mode": "playback" if replay else "record" if record else "live",
        "producer_budget": budget,
        "players": players,
        "episodes": episodes,
        "staged_object_fixture": objects,
        "instances": [],
    }
    owned = []
    started = time.monotonic()
    try:
        for index in range(instances):
            runtime = output / f"instance-{index}"
            target_map = prepare_runtime(game_dir, runtime, map_path)
            load_path = target_map
            if replay:
                load_path = runtime / "Replay" / "playback.w3g"
                shutil.copy2(replay, load_path)
            saved_replay = runtime / "Replay" / "probe.w3g"
            pid, handle = _launch_verified(
                runtime / "War3.exe",
                dll,
                ["-window", "-loadfile", str(load_path)],
                15,
                {
                    "WC3HOOK_LOG_DIR": str(runtime / "Logs"),
                    "WC3HOOK_DOCS": str(runtime / "UserData"),
                    "WC3HOOK_WINDOW_MODE": "background",
                    "WC3HOOK_BACKGROUND_VISIBLE": "0",
                    "WC3HOOK_SOUND": "0",
                    "WC3PROBE_STEP": str(int(steps)),
                    "WC3PROBE_SPEED": str(speed),
                    "WC3PROBE_ACTION": str(int(actions)),
                    "WC3PROBE_SAVE_REPLAY": str(saved_replay) if record else "",
                    "WC3PROBE_REPLAY": str(int(replay is not None)),
                    "WC3PROBE_BUDGET": str(int(budget)),
                    "WC3PROBE_PLAYERS": str(players),
                    "WC3PROBE_EVENTS": str(int(events)),
                    "WC3PROBE_EPISODES": str(episodes),
                    "WC3PROBE_OBJECTS": str(int(objects)),
                },
            )
            owned.append(handle)
            item = {"pid": pid, "runtime": str(runtime), "windowed": True, "clock_speed": speed or None}
            if replay:
                item["replay_sha256"] = hashlib.sha256(load_path.read_bytes()).hexdigest()
            report["instances"].append(item)
            print(f"Started owned probe PID {pid}: {runtime}", flush=True)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if any(k32.WaitForSingleObject(h, 0) == 0 for h in owned):
                break
            time.sleep(0.1)
        for item, handle in zip(report["instances"], owned):
            code = ctypes.c_ulong()
            k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            k32.GetExitCodeProcess(handle, ctypes.byref(code))
            log = Path(item["runtime"]) / "Logs" / f"probe-{item['pid']}.log"
            content = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            item.update(
                exit_code_before_cleanup=code.value,
                engine_loaded="phase=wc3probe-engine" in content,
                native_readbacks=content.count("native_unit "),
                failure="FAIL " in content or "exception code=" in content,
                consumer_steps=content.count("phase=wc3probe-steps") == episodes if steps else None,
                completed_episodes=content.count("phase=wc3probe-steps"),
                observed_restarts=content.count("restart_observed"),
                executed_move=content.count("phase=wc3probe-action") == episodes if actions else None,
                staged_damage_death=content.count("phase=wc3probe-events") == episodes if events else None,
                object_layouts=(
                    content.count("phase=wc3probe-objects\n") == episodes
                    and content.count("object127_checkpoint ") == 5 * episodes
                    if objects
                    else None
                ),
                spell_samples=[
                    {
                        "game_time_ms": int(gt),
                        "target_hp": float(hp),
                        "caster_mana": float(mana),
                        "cooldown_seconds": float(cd),
                    }
                    for gt, hp, mana, cd in re.findall(
                        r"holybolt_state target=(\d+) hp=([-\d.]+) mana=([-\d.]+) remaining=([-\d.]+)", content
                    )
                ],
                fixture_event_counts={
                    "spell_effect": content.count("object127_spell ability=41486862"),
                    "item_pickup": content.count("object127_event kind=80231 "),
                    "item_drop": content.count("object127_event kind=80230 "),
                }
                if objects
                else None,
                step_measurements=[
                    {"game_time_ms": int(actual), "target_ms": int(target), "wall_ms": int(wall)}
                    for actual, target, wall in re.findall(
                        r"step_target actual=(\d+) target=(\d+) wall_ms=(\d+)", content
                    )
                ],
                worker_states=[
                    {"game_ms": int(gt), "x": float(x), "y": float(y), "order": int(order)}
                    for gt, x, y, order in re.findall(
                        r"(?<!other_)worker_state game_ms=(\d+) x=([-\d.]+) y=([-\d.]+) order=(\d+)", content
                    )
                ],
                other_worker_states=[
                    {"game_ms": int(gt), "x": float(x), "y": float(y), "order": int(order)}
                    for gt, x, y, order in re.findall(
                        r"other_worker_state game_ms=(\d+) x=([-\d.]+) y=([-\d.]+) order=(\d+)", content
                    )
                ],
                producer_budgets=[
                    {
                        "enabled": bool(int(enabled)),
                        "target_ms": int(target),
                        "sent_ms": int(sent),
                        "credit_ms": int(credit),
                    }
                    for enabled, target, sent, credit in re.findall(
                        r"producer_budget enabled=(\d+) target=(\d+) sent_ms=(\d+) credit=(\d+)", content
                    )
                ],
                object_snapshots=[
                    {
                        "phase": phase,
                        "target_ms": int(target),
                        "count": int(count),
                        "hash": checksum,
                        "own": int(own),
                        "visible": int(visible),
                        "worker": int(worker),
                    }
                    for phase, target, count, checksum, own, visible, worker in re.findall(
                        r"object_snapshot phase=(\w+) target=(\d+) count=(\d+) hash=([0-9a-f]+) own=(\d+) visible=(\d+) worker=(\d+)",
                        content,
                    )
                ],
                log=str(log),
            )
            if record:
                saved_replay = Path(item["runtime"]) / "Replay" / "probe.w3g"
                header = saved_replay.read_bytes()[:68] if saved_replay.exists() else b""
                item["replay_recorded"] = "replay_saved result=1" in content and header.startswith(
                    b"Warcraft III recorded game"
                )
                item["replay_path"] = str(saved_replay)
                if saved_replay.is_file():
                    item["replay_sha256"] = hashlib.sha256(saved_replay.read_bytes()).hexdigest()
            addresses = re.findall(r"game_object address=([0-9a-fA-F]+)", content)
            address = addresses[-1] if addresses else None
            if steps and item["consumer_steps"] and address and code.value == 259:
                pointer = int(address, 16)
                before = read_game_time(handle, pointer)
                at = time.monotonic()
                time.sleep(0.55)
                after = read_game_time(handle, pointer)
                item["frozen_readback"] = {
                    "before_ms": before,
                    "after_ms": after,
                    "wall_ms": (time.monotonic() - at) * 1000,
                    "passed": before == after == 7275,
                }
        report["passed"] = len(owned) == instances and all(
            i["engine_loaded"]
            and i["native_readbacks"] >= 12
            and not i["failure"]
            and i["exit_code_before_cleanup"] == 259
            and (not steps or i["consumer_steps"])
            and (not steps or i.get("frozen_readback", {}).get("passed", False))
            and (not actions or i["executed_move"])
            and (not record or i["replay_recorded"])
            and (not events or i["staged_damage_death"])
            and (not objects or i["object_layouts"])
            and (
                not steps or not speed or sum(s["phase"] == "frame_wait" for s in i["object_snapshots"]) == 5 * episodes
            )
            and i["observed_restarts"] == episodes - 1
            for i in report["instances"]
        )
    except Exception as exc:
        report.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        cleanup = []
        for handle in owned:
            # Exact retained process handles: never find/kill processes by name or stale PID.
            terminated = bool(k32.TerminateProcess(handle, 0)) if k32.WaitForSingleObject(handle, 0) != 0 else True
            waited = k32.WaitForSingleObject(handle, 10000) == 0
            cleanup.append(terminated and waited)
            k32.CloseHandle(handle)
        report["owned_processes_cleaned"] = cleanup
        report["wall_seconds_including_setup"] = time.monotonic() - started
        if not all(cleanup):
            report["passed"] = False
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--instances", type=int, choices=(1, 2, 4), default=1)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--steps", action="store_true", help="fixed consumer-side stepping experiment")
    ap.add_argument("--speed", type=int, choices=(0, 1, 8, 64), default=0, help="optional virtual clock experiment")
    ap.add_argument("--actions", action="store_true", help="recordable local-player movement packet experiment")
    ap.add_argument("--record", action="store_true", help="save native replay after movement probe")
    ap.add_argument("--replay", type=Path, help="play a replay produced by this probe")
    ap.add_argument("--budget", action="store_true", help="bound native turn production to the published target")
    ap.add_argument("--players", type=int, choices=(1, 2), default=1, help="number of commanded players")
    ap.add_argument("--events", action="store_true", help="staged UnitDamageTarget death-event probe (not recorded)")
    ap.add_argument("--episodes", type=int, choices=(1, 2, 5), default=1, help="repeat through native map reload")
    ap.add_argument("--objects", action="store_true", help="staged hero/item/ability accessor checks (not recorded)")
    args = ap.parse_args()
    if not 1 <= args.seconds <= 120:
        ap.error("--seconds must be between 1 and 120")
    if (args.speed or args.actions or args.budget) and not args.steps:
        ap.error("--speed, --actions and --budget require --steps")
    if args.players == 2 and not args.actions:
        ap.error("two-player control requires --actions")
    if args.events and (not args.actions or args.record or args.replay):
        ap.error("--events requires --actions and cannot record or replay staged changes")
    if args.objects and (not args.steps or args.record or args.replay):
        ap.error("--objects requires --steps and cannot record or replay staged changes")
    if args.episodes > 1 and (not args.steps or not args.speed or args.record or args.replay):
        ap.error("reload probes need --steps --speed and do not yet support recording or playback")
    if (args.record or args.replay) and (not args.actions or not args.steps):
        ap.error("record/playback checks require --steps --actions")
    if args.record and args.replay:
        ap.error("record and playback are separate runs")
    output = args.output or ROOT / "runs" / f"probe127-{time.time_ns()}"
    report = run(
        args.game_dir.resolve(),
        output.resolve(),
        args.instances,
        args.seconds,
        args.steps,
        args.speed,
        args.actions,
        args.record,
        args.replay.resolve() if args.replay else None,
        args.budget,
        args.players,
        args.events,
        args.episodes,
        args.objects,
    )
    print(
        json.dumps(
            {
                "report": str(output / "report.json"),
                "passed": report["passed"],
                "wc3env_game_acceptance": report["wc3env_game_acceptance"],
                "processes": [i["pid"] for i in report["instances"]],
                "owned_processes_cleaned": report["owned_processes_cleaned"],
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
