"""Read-only recovery audit runner; writes only new evidence/build/runtime directories.

Run with the existing repository venv. No installs, git writes, or game-source edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(out, label, argv, *, cwd=ROOT, timeout=180, extra_env=None):
    out.mkdir(parents=True, exist_ok=True)
    log = out / f"{label}.log"
    if log.exists():
        raise FileExistsError(log)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "WC3_SOUND": "0", **(extra_env or {})}
    started = time.perf_counter()
    result = {"argv": list(map(str, argv)), "cwd": str(cwd), "started_utc": datetime.now(UTC).isoformat()}
    with log.open("w", encoding="utf-8") as stream:
        try:
            proc = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            result["exit_code"] = proc.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            result.update(exit_code=None, error=str(exc))
    result.update(wall_seconds=round(time.perf_counter() - started, 3), log=str(log))
    save(out / f"{label}.command.json", result)
    print(json.dumps({"label": label, **result}), flush=True)
    return result


def snapshot(out):
    out.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    save(out / "tracked-before.json", {name: sha(ROOT / name) for name in tracked if name and (ROOT / name).is_file()})
    for label, args in (
        ("git-status", ["status", "--short"]),
        ("git-remotes", ["remote", "-v"]),
        ("git-branches", ["branch", "-avv"]),
        ("git-log", ["log", "-10", "--oneline"]),
        ("git-worktrees", ["worktree", "list", "--porcelain"]),
        ("git-port-diff", ["diff", "--stat", "2f7ddf1", "dc2ca7b"]),
        ("git-local-commits", ["log", "--oneline", "--all", "--not", "--remotes"]),
        ("git-uncommitted", ["diff", "--", "README.md", "docs/port-127a.md"]),
    ):
        run(out, label, ["git", *args])
    sys.path.insert(0, str(ROOT / "src"))
    from wc3env.compatibility import verify_executable
    from wc3env.settings import settings

    cfg = settings()
    verify_executable(cfg.game_exe)
    game_files = [p for p in cfg.game_dir.iterdir() if p.is_file() and p.suffix.lower() in {".exe", ".dll", ".mpq"}]
    game_files += list((cfg.game_dir / "Maps").rglob("*.w3x")) + list((cfg.game_dir / "Maps").rglob("*.w3m"))
    save(out / "game-before.json", {str(p): sha(p) for p in game_files})
    save(
        out / "environment.json",
        {
            "python": sys.executable,
            "version": sys.version,
            "game_dir": str(cfg.game_dir),
            "map": str(cfg.map),
            "game_identity": {name: sha(cfg.game_dir / name) for name in ("War3.exe", "Game.dll")},
            "hook": {
                str(p): sha(p)
                for p in [ROOT / "src/wc3env/native/wc3hook.dll", ROOT / "wc3hook/out/wc3hook.dll"]
                if p.exists()
            },
        },
    )


def offline(out):
    failed = False
    for label, args in (
        ("host-unit", ["-m", "unittest", "discover", "-s", "tests/unit", "-t", "."]),
        ("agent-unit", ["-m", "unittest", "discover", "-s", "wc3agent/tests"]),
        ("ruff-check", ["-m", "ruff", "check", "."]),
        ("ruff-format-check", ["-m", "ruff", "format", "--check", "."]),
    ):
        result = run(out, label, [sys.executable, *args])
        failed = failed or result["exit_code"] != 0
    return int(failed)


def build(out):
    stage = out / "build-source"
    stage.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / "wc3hook", stage / "wc3hook", ignore=shutil.ignore_patterns("out"))
    shutil.copytree(ROOT / "tests/native", stage / "tests/native")
    (stage / "src/wc3env").mkdir(parents=True)
    result = run(out, "native-build", ["cmd.exe", "/d", "/c", str(stage / "wc3hook/build.bat")], cwd=stage)
    if result["exit_code"] == 0:
        save(out / "build-hashes.json", {str(p.relative_to(stage)): sha(p) for p in stage.rglob("*") if p.is_file()})
    return result["exit_code"] if result["exit_code"] is not None else 1


def preserve(out):
    result = {}
    for name in ("tracked", "game"):
        before = json.loads((out / f"{name}-before.json").read_text(encoding="utf-8"))
        differences = []
        for file, digest in before.items():
            path = ROOT / file if name == "tracked" else Path(file)
            if not path.is_file() or sha(path) != digest:
                differences.append(file)
        result[name] = {
            "files": len(before),
            "differences": differences,
            "status": "PASS" if not differences else "FAIL",
        }
    save(out / "preservation.json", result)
    print(json.dumps(result))
    return int(any(row["status"] != "PASS" for row in result.values()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("snapshot", "offline", "build", "preserve", "command"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == "command":
        result = run(out, args.label, args.command, timeout=args.timeout)
        return result["exit_code"] if result["exit_code"] is not None else 1
    return globals()[args.mode](out) or 0


if __name__ == "__main__":
    raise SystemExit(main())
