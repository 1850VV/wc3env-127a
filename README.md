# wc3env for Warcraft III 1.27a

A gym-style environment for real Warcraft III Legacy on Windows. An injected DLL provides
deterministic stepping, fog-filtered observations and native commands on stock maps, with
offline self-play and pools of independent game processes.

This unofficial port derives from [pwang724/wc3env](https://github.com/pwang724/wc3env)
and retains its [MIT license](LICENSE). Start with the
[1.27a validation report](docs/WC3ENV_127A_VALIDATION.md),
[API compatibility matrix](docs/API_COMPATIBILITY_127A.md),
[Chinese capability guide](docs/features-127a.md), and
[upstream provenance and third-party licenses](docs/UPSTREAM_PROVENANCE.md).
The [private-repository synchronization record](docs/SYNC_PLAN.md) documents
the approved history cleanup. [Commit mappings](docs/HISTORY_REWRITE.md) retain
provenance while excluding historical demo media and obsolete replays.

```python
from wc3env import GameConfig, WC3Env

with WC3Env(GameConfig(map="(2)EchoIsles.w3x", step_ms=1000)) as env:
    obs = env.reset()
    worker = next(u for u in obs["units"] if u["type_id"] == "hpea")
    move = {"unit_id": worker["unit_id"], "command": "move", "arguments": {"x": worker["x"] - 400, "y": worker["y"]}}
    obs, done, info = env.step([move])
    print(obs["game_time_seconds"], len(obs["units"]), info["rejected"])
```

> **Unofficial and offline only.** This project is not affiliated with or endorsed by
> Blizzard Entertainment; Warcraft is their trademark. It bundles no game installation,
> archives or maps: you need your own licensed installation. It modifies a local, offline game
> process and must never be used on Battle.net or in online play. Whether that use fits
> your license agreement is your responsibility.

## Setup

1. Use your local **Warcraft III 1.27a, x86 build 1.27.0.52240** installation.
   This fork verifies both `War3.exe` and `Game.dll` before injection; see the exact
   hashes and acceptance evidence in [the port report](docs/port-127a.md).
2. Use Windows x64, 64-bit Python 3.11+ and Visual Studio Build Tools (Desktop development
   with C++) to build the 32-bit hook.
3. Copy [.env.example](.env.example) to `.env` and set `WC3_GAME_DIR`.

```powershell
wc3hook/build.bat
python -m pip install -e .
python -m unittest discover -s tests/unit -t .
python -m tests.e2e                             # real game, ~3 min; skipped without an installation
```

`render=False` still needs Direct3D 9 and a window/device; see
[rendering and input](docs/design.md#rendering-and-input). The 1.27a port is validated on Windows; the inherited Docker/Wine workflow has not been validated for this build.

## Use

Two agents sharing one simulation:

```python
from wc3env import GameConfig, GameSession, PlayerConfig

with GameSession(GameConfig(players=(PlayerConfig(0), PlayerConfig(1)))) as session:
    observations = session.reset()
    observations, done, info = session.step({0: [], 1: []})
```

`reset()` reloads the map in-process and periodically recycles the process to bound memory.
Map and agent slots are fixed at launch; `session.setup` reports the accepted configuration.
For independent games use `StepPool.launch(n, speed, config=...)`, or try the CLI:
`python -m wc3env --instances 8 --steps 200 --speed 64`.

Each game process writes logs and replays to its own directory (`game.data_dir`), by default
under `%LOCALAPPDATA%/wc3env`. Choose another parent with
`GameConfig(output_dir=...)` or `WC3_OUTPUT_DIR`; the explicit argument wins.
`session.save_replay(path)` writes the finished episode as a native `.w3g` that the game, or this
environment, can play back.

## Agent

The LLM agent in [`wc3agent/`](wc3agent/README.md) needs two keys in `.env`: `TYPESAFE_API_KEY`
for Jev (micro), and a macro model: `MACRO_PROVIDER` (`anthropic`, or `openai` for any
OpenAI-compatible endpoint), `MACRO_MODEL` and `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.

```powershell
python -m pip install -e . -e wc3agent
python -m wc3agent duels human --runs 1 --visible --realtime       # Jev in a mirror duel
python -m wc3agent melee --race orc --difficulty insane --realtime # a full game against the Insane AI
```

## Documentation

| | |
|---|---|
| [Architecture](docs/architecture.md) | Plain-language tour of how it all works; start here |
| [Design](docs/design.md) | How stepping, commands, observations, reset and rendering work |
| [RPC](docs/specs/protocol.md) · [Observations](docs/specs/observations.md) · [Actions](docs/specs/actions.md) · [Configuration](docs/specs/configuration.md) | Contracts |
| [Compatibility](docs/compatibility.md) | What has been measured, and on what |
| [1.27a 功能说明（中文）](docs/features-127a.md) | 能力清单、Python 示例、配置方式和适用范围 |
| [1.27a port and acceptance](docs/port-127a.md) | Supported binaries, native validation and installation package |
| [Roadmap](docs/roadmap.md) | Unfinished work |
| [Contributing](CONTRIBUTING.md) | Build, test and change guidelines |

## Layout

| Path | Contents |
|---|---|
| `src/wc3env/` | Python API: sessions, pools, RPC client, process launch and validation |
| `wc3hook/` | Injected DLL; `wc3hook.h` lists shared interfaces and executable offsets |
| `tests/` | `unit/` and `native/` need no game; `e2e/` drives the real one (`e2e/extended/` is a broader on-request tier) |
| [`tools/`](tools/README.md) | Game-data preparation and executable inspection |
| [`docker/`](docker/README.md) | Linux/Wine worker built from your own installation |
| [`wc3agent/`](wc3agent/README.md) | Experimental LLM agent with its realtime runner and recorder (work in progress) |

[MIT licensed](LICENSE). MinHook and yyjson keep their own licenses in
`wc3hook/minhook/LICENSE.txt` and `wc3hook/yyjson/LICENSE`.
