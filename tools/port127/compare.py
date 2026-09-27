"""Compare a native research recording with its playback, without claiming full API acceptance."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TARGETS = (1000, 1025, 1275, 2275, 7275)
FIELDS = ("type", "owner", "x", "y", "hp", "visible")
ROW = re.compile(
    r"unit_observation target=(\d+) id=([0-9a-f]+) type=([0-9a-f]+) owner=(\d+) "
    r"x=([0-9a-f]+) y=([0-9a-f]+) hp=([0-9a-f]+) visible=([01])"
)


def observations(log: str) -> dict[tuple[int, str], dict[str, str]]:
    """Keep float bit patterns, not rounded decimal coordinates or diagnostic hashes."""
    rows = {}
    for target, object_id, *values in ROW.findall(log):
        key = (int(target), object_id)
        if key in rows:
            raise ValueError(f"Duplicate unit observation: {key}")
        rows[key] = dict(zip(FIELDS, values))
    if {key[0] for key in rows} != set(TARGETS):
        raise ValueError("Missing or unexpected observation targets")
    return rows


def compare(record: dict, playback: dict, record_log: str, playback_log: str, index: int = 0) -> dict:
    for report, mode in ((record, "record"), (playback, "playback")):
        if report.get("kind") != "live_native_research_probe" or report.get("mode") != mode:
            raise ValueError(f"Expected a {mode} research probe report")
        if (
            not report.get("passed")
            or not report.get("owned_processes_cleaned")
            or not all(report["owned_processes_cleaned"])
        ):
            raise ValueError(f"The {mode} probe did not pass and clean up")
    if record.get("binary_hashes") != playback.get("binary_hashes"):
        raise ValueError("Different engine identities")
    a, b = record["instances"][index], playback["instances"][0]
    if not a.get("replay_recorded") or not a.get("replay_sha256") or a["replay_sha256"] != b.get("replay_sha256"):
        raise ValueError("Playback did not load the recorded replay bytes")
    left, right = observations(record_log), observations(playback_log)
    for item, rows in ((a, left), (b, right)):
        reported = {s["target_ms"]: s["count"] for s in item.get("object_snapshots", []) if s["phase"] == "update"}
        if reported != {target: sum(key[0] == target for key in rows) for target in TARGETS}:
            raise ValueError("Unit log is incomplete relative to its reported snapshot counts")
    keys = sorted(left.keys() | right.keys())
    differences = [
        {"target_ms": key[0], "unit_id": key[1], "recorded": left.get(key), "played": right.get(key)}
        for key in keys
        if left.get(key) != right.get(key)
    ]
    worker_equal = bool(a.get("worker_states")) and a["worker_states"] == b.get("worker_states")
    worker_equal = worker_equal and a.get("other_worker_states", []) == b.get("other_worker_states", [])
    if record.get("players", 1) != playback.get("players", 1):
        raise ValueError("Different agent configurations")
    return {
        "kind": "native_research_replay_comparison",
        "wc3env_game_acceptance": "NOT_RUN",
        "passed": not differences and worker_equal,
        "targets_ms": list(TARGETS),
        "compared_unit_snapshots": len(keys),
        "fields": list(FIELDS),
        "worker_orders_equal": worker_equal,
        "different_unit_snapshots": len(differences),
        "first_differences": differences[:20],
        "scope": "Five checkpoints of unit type/owner/position/HP/player-0 visibility and commanded workers' current orders. Not complete state or match determinism.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("playback", type=Path)
    parser.add_argument("--record-instance", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    playback = json.loads(args.playback.read_text(encoding="utf-8"))
    result = compare(
        record,
        playback,
        Path(record["instances"][args.record_instance]["log"]).read_text(encoding="utf-8"),
        Path(playback["instances"][0]["log"]).read_text(encoding="utf-8"),
        args.record_instance,
    )
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
