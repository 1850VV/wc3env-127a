"""Private writable 1.27a installations; the engine stores replays beside War3.exe."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .compatibility import verify_executable


def prepare_runtime(source: Path, destination: Path) -> Path:
    """Copy executable images, share read-only MPQs when on the same volume.

    Each launch gets a new directory and its own Replay, Save and log files.
    Keep it after closing so diagnostics and native replay output remain available.
    """
    verify_executable(source / "War3.exe")
    destination.mkdir(parents=True, exist_ok=False)
    for file in source.iterdir():
        if not file.is_file() or (file.suffix.lower() not in (".dll", ".mpq") and file.name.lower() != "war3.exe"):
            continue
        target = destination / file.name
        if file.suffix.lower() == ".mpq":
            try:
                os.link(file, target)
                continue
            except OSError:
                pass
        shutil.copy2(file, target)
    for folder in ("Replay", "Logs", "Save", "CustomMapData", "Maps"):
        (destination / folder).mkdir()
    executable = destination / "War3.exe"
    verify_executable(executable)
    return executable
