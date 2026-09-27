"""Build an original flat JASS arena with Python standard library only."""

import struct
from pathlib import Path

from tools.kiting_mpq import archive

SIZE = 64
FLAGS = (1 << 5) | (1 << 6) | (1 << 14)


def i(*v):
    return struct.pack("<" + "i" * len(v), *v)


def f(*v):
    return struct.pack("<" + "f" * len(v), *v)


def s(v):
    return v.encode() + b"\0"


def main():
    info = i(25, 1, 6059) + s("Archmage Kiting MVP") + s("Warcraft Agent") + s("Offline micro arena") + s("2")
    info += f(-3584, -3584, 3584, 3584, -3584, 3584, 3584, -3584) + i(4, 4, 4, 4, SIZE - 8, SIZE - 8, FLAGS) + b"L"
    info += i(-1) + s("") + s("Archmage versus Footman") + s("Micro MVP") + s("Python controller")
    info += i(0) + s("") * 4 + i(0) + f(3000, 5000, 0) + bytes([0, 0, 0, 255]) + i(0)
    info += s("Default") + b"L" + bytes([255] * 4) + i(2)
    for p, x in ((0, 0), (1, 520)):
        info += i(p, 1, 1, 1) + s(f"Player {p + 1}") + f(x, 0) + i(0, 0)
    info += i(2) + i(0, 1) + s("Archmage") + i(0, 2) + s("Footman") + i(0, 0, 0, 0)
    terrain = b"W3E!" + i(11) + b"L" + i(0, 2) + b"LgrsLdrt" + i(2) + b"CLdiCLgr"
    terrain += i(SIZE + 1, SIZE + 1) + f(-SIZE * 64, -SIZE * 64)
    for y in range(SIZE + 1):
        for x in range(SIZE + 1):
            edge = x < 4 or y < 4 or x > SIZE - 4 or y > SIZE - 4
            terrain += struct.pack("<HHBBB", 8192, 8192 | (0x4000 if edge else 0), int(edge), 0, 2)
    config = []
    for p, x in ((0, 0), (1, 520)):
        config += [
            f"call DefineStartLocation({p},{x},0)",
            f"call SetPlayerStartLocation(Player({p}),{p})",
            f"call ForcePlayerStartLocation(Player({p}),{p})",
            f"call SetPlayerColor(Player({p}),ConvertPlayerColor({p}))",
            f"call SetPlayerRacePreference(Player({p}),RACE_PREF_HUMAN)",
            f"call SetPlayerRaceSelectable(Player({p}),false)",
            f"call SetPlayerController(Player({p}),MAP_CONTROL_USER)",
            f"call SetPlayerTeam(Player({p}),{p})",
            f"call SetPlayerSlotAvailable(Player({p}),MAP_CONTROL_USER)",
        ]
    script = (
        """function config takes nothing returns nothing
call SetMapName("Archmage Kiting MVP")
call SetMapDescription("Offline micro arena")
call SetPlayers(2)
call SetTeams(2)
call SetGamePlacement(MAP_PLACEMENT_USE_MAP_SETTINGS)
"""
        + "\n".join(config)
        + r"""
endfunction
function main takes nothing returns nothing
call SetCameraBounds(-3584,-3584,3584,3584,-3584,3584,3584,-3584)
call SetDayNightModels("Environment\\DNC\\DNCLordaeron\\DNCLordaeronTerrain\\DNCLordaeronTerrain.mdl", "Environment\\DNC\\DNCLordaeron\\DNCLordaeronUnit\\DNCLordaeronUnit.mdl")
call InitBlizzard()
call StartMeleeAI(Player(1),"human.ai")
call SetFloatGameState(GAME_STATE_TIME_OF_DAY,12)
call SuspendTimeOfDay(true)
call SetCameraField(CAMERA_FIELD_TARGET_DISTANCE,1800,0)
endfunction
"""
    )
    n = SIZE * 4
    files = {
        "war3map.w3i": info,
        "war3map.w3e": terrain,
        "war3map.wpm": b"MP3W"
        + i(0, n, n)
        + bytes(255 if x < 16 or y < 16 or x >= n - 16 or y >= n - 16 else 0 for y in range(n) for x in range(n)),
        "war3map.shd": bytes(n * n),
        "war3map.doo": b"W3do" + i(8, 11, 0, 0, 0),
        "war3mapUnits.doo": b"W3do" + i(8, 11, 0),
        "war3map.w3r": i(5, 0),
        "war3map.w3c": i(0, 0),
        "war3map.wts": b"",
        "war3map.j": script.encode(),
    }
    output = Path("build/maps/(2)KitingArena.w3x")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((b"HM3W" + i(0) + s("Archmage Kiting MVP") + i(FLAGS, 2)).ljust(512, b"\0") + archive(files))
    print(output.resolve())


if __name__ == "__main__":
    main()
