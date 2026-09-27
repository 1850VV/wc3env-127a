# Design

Warcraft owns the simulation. Python owns agents and processes; an injected DLL exposes
game state, commands and time control. [Architecture](architecture.md) has the overview
and diagrams. [Roadmap](roadmap.md) owns unfinished work.
Contracts: [RPC](specs/protocol.md), [observations](specs/observations.md),
[actions](specs/actions.md), [match setup and pools](specs/configuration.md).

## Compatibility

Supported in this fork: offline Warcraft III **1.27a, x86 1.27.0.52240**, on Windows x64
with 64-bit Python 3.11+. The launcher validates the PE architecture and full SHA-256
of both `War3.exe` and `Game.dll` before injection. Exact identities and current
live evidence are in [the port report](port-127a.md). Other binaries need verified
bindings and calling conventions, not a changed hash or version label.

The bootstrap installs API hooks before `War3.exe` resumes. A LoadLibraryA detour
installs engine hooks when `Game.dll` appears, before its entry point is called.
Each process gets a private runtime containing copied executable/DLL images,
read-only game archives shared by hardlink when possible, copied selected maps,
and independent Replay/Save/log files. Original installation files are not edited.

Maps accept absolute paths, install-relative paths or unique filenames under `Maps/`.
The loaded map establishes active slots, controllers, races and starting state;
configuration validates those facts by default. Opt-in `MatchSetup` applies race/controller
choices, activates map-defined slots and seeds starting locations before melee startup.
Paths must fit the engine's 260-character buffers,
including generated replay paths. Map paths must round-trip through the Windows code page
because Warcraft reads `-loadfile` as ANSI. DLL injection uses UTF-16.

## Ownership and lifecycle

```text
agent -> WC3Env -> GameSession -> RpcClient -> named pipe -> wc3hook.dll -> Warcraft III
StepPool -> independent games, each with its own process, pipe and simulation clock
```

- `GameSession` owns launch, reset, close and one clock. It validates every agent's batch,
  advances once and observes each player. `PlayerView` reads cached observations;
  `WC3Env` wraps a session for one agent.
- RPC round trips are serialized. Game-object reads and mutations run on the game thread,
  during updates or the frame pacing wait. Between frames, jobs temporarily install cached
  component TLS; arbitrary wait callbacks are unsafe.
- A short-held ownership lock lets close detach and cancel a process during a blocked
  round trip. A concurrent launch owns its result until publication and disposes it if
  close wins. Retaining the process handle prevents PID-reuse mistakes.
- Each launch gets unique writable data for logs, replays and custom files. Hooks isolate
  named mutexes/events and redirect Documents before the main thread resumes.
- `StepPool` accepts one or several `GameConfig` values through one startup path. It
  preserves instance order, closes failed games and measures actual simulated time.

The game holds at **1000 ms** before `create_game` validates setup and selects stepping or
realtime. States are `launched -> in_game -> ended`; final observations remain readable.
Each player's result is retained; the session ends when all agents have results.

Reset calls `RestartGame(false)` (`0x1f31e0`) to reload the same map in-process. Unregister
added agent identities first: retaining them stalls teardown. Check membership before
unregistering. Clear actions, selections, events, results, staging and game/TLS pointers;
preserve hooks, pipe, speed, wait floor and rendering settings. Ignore teardown results and
register identities at the new hold. Failed reloads or suspect connections need a fresh process.
`GameSession` also recycles before episode 33 by default;
configure `max_episodes_per_process` to change this limit. Seed and RPC tuning survive the
replacement. Raw RPC resets remain in-process. See the [measured matrix](compatibility.md).

Stepping replay playback stops at the recorded duration and preserves final observations;
EOF does not invent player results. Actions come from the recording. Session reset relaunches
the replay: `RestartGame` is a map reload, not a replay restart.

The 1.27a native allocator passes the 2,048-unit regression without the predecessor's
binary-specific allocator or UI teardown patches. Those 1.29 detours are not installed.
The default 32-episode process recycling policy bounds retained engine/GPU caches.

## Time and command delivery

QPC, GetTickCount, FILETIME and the `rdtsc` helper (`0x154d20`) share a virtual clock.
Seqlock readers avoid blocking timer calls inside other libraries. Integer conversions
divide before multiplying to avoid overflow. Speed scales finite waits; frozen waits keep
a 1 ms floor. RPC deadlines use real time.

`GameUpdate` (`0x30ff00`) consumes 25 ms turns. Stepping writes pending time and passes zero
elapsed time to bypass the lag clamp. Publish the producer budget after actions flush.
The offline host (`0x874a10`) emits that budget, at most 400 ms per packet; account time
before transmission and reset the total with its native counter. Warcraft retains sequencing,
delivery and acknowledgements. Realtime uses native scheduling. Receiver-side credit trimming
caused stalls; 1x settling only hid queued backlog.

A step completes after `GameUpdate` unwinds. The stall guard measures five seconds without
progress, not total duration. Replies report elapsed time and completion reason; sessions
reject unexplained short steps, and pools retire stalled games.

Actions use Warcraft's command parser. Offline agents send zero-time packets through
`0x30ba60`, splitting at record boundaries. `QueueLocalAction` (`0x30f1b0`) stamps the local
wire identity and remains the UI path. Register missing identities through the native table
(`0x306e60`, `0x312810`); suppress startup AI without changing human/computer slot types.
Selection history stores IDs, not pointers, and clears before another unit is selected.
Acceptance means queued; Warcraft still applies range, resource and ability rules.

## Observations and events

Enumerate objects (`0x02f230`) without allocating JASS handles. RPC IDs use the object's
`+0xc` ID; internal references also need its `+0x10` salt. Lookup has no fixed object-count
cap. Exclude hidden, loaded and Locust units and apply each observer's fog. The twelve playing slots and four neutral slots use IDs 0–15 directly.

Hook event dispatch (`0x245080`) and its registration check (`0x0566d0`). Spell effects need
their firing hook (`0x244300`) while the ability is valid. Snapshot values and visibility
before objects change; retain no game pointers. Death ownership precedes defeat transfers;
summon's trigger unit is the summoned unit. Each observer has a bounded visible-event
history: hidden activity affects neither retention nor loss counts. Never infer death from
disappearance. Agents select resources from visible destructables and type IDs, without a
first-base or nearest-tree shortcut.

Player categories, alliances and own scores come from runtime natives. Resource labels use
loaded object data, including custom tree types. World bounds cache four numbers per episode;
the temporary native rectangle is released immediately. See [metadata](specs/observations.md#observation-metadata).

## Rendering and input

| Window mode | Behavior |
|---|---|
| `background` (default) | Offscreen, absent from taskbar/Alt-Tab; never requests focus or captures the mouse; all input swallowed |
| `background` + `background_visible` | A normal window that never takes focus or the cursor on its own and never pauses; click it to control the game, click away and it keeps running |
| `interactive` | Normal Warcraft input and focus behavior, including pausing when the window loses focus; use realtime for human play |

Window policy is fixed per process and survives resets. Background mode requires a window;
`launch(window=False, window_mode="interactive")` allows fullscreen. `game.resize()` and
`game.offscreen()` reposition without requesting focus.
Resize requests are asynchronous and can be clamped by Warcraft's minimum window size.

`render=False` suppresses **Direct3D 9 Present** but completes GPU work through an event
query. The hook is installed through Direct3DCreate9/CreateDevice and the device vtable;
Warcraft scene cleanup and draw calls remain active.
Leaving GPU work pending retained buffers; skipping cleanup retained textures.
A window and graphics device are still required. `debug("render", on=0)` uses the same
hook. Other graphics backends are outside the validated configuration.

## Build and validation

Real-game tests skip when no supported installation is configured; CI runs only
host and native tests. The MSVC build produces the x86 hook, checks required hook installation, runs native
regressions and copies the DLL into the Python package. yyjson owns strict JSON parsing;
checked accessors enforce native ranges and string capacities. Vendor sources stay pinned
and unmodified. Wheels include the DLL and project/vendor licenses, never Warcraft assets.

```powershell
wc3hook/build.bat
python -m unittest discover -s tests/unit -t .
python -m unittest discover -s tests/e2e -t .
python -m tests.e2e
python -m pip wheel --no-deps . --wheel-dir dist
python tools/check_wheel.py dist
```

Host/native CI needs no game; the wheel check runs outside the checkout. Live tests cover
commands, fog/events, results, resets, timing and pool isolation on supported stock maps.
The fake checks contracts and lifecycle, not combat or native delivery. A complete seeded
melee match repeats across reload and process replacement; fresh two-agent movement, construction and combat recordings match playback. The [compatibility matrix](compatibility.md) bounds this evidence.
Run artifacts stay ignored; deliberate regression fixtures are tracked. Pending work belongs in the roadmap.

Native tools: `tools/disasm.py`, `imports.py`, `natives.py`.
Pipe probes: `where`, `profile`, `watch`, `scan`, `dump`, `trace`, `pktlog`.
Native calls use 32-bit argument slots, float pointers for real arguments and bits for real
returns. Staging may allocate VM handles (`0x1c3200`, `0x2651d0`); object enumeration must not.
The bounds cache uses one temporary rectangle per episode and releases it immediately.
MPQ extraction needs StormLib; see [tools](../tools/README.md).

## Agent integration and Linux workers

[`wc3agent/`](../wc3agent/README.md) is a separate Python project. Its current brief-driven
Jev controller owns context formation, memory, tactics and scheduling. Its Warcraft
policy consumes prepared reference data and supplied observations;
model transport lives in `models/jev.py`. The environment
imports no agent code. Policy evaluation is separate from engine validation.

Combat menus expose candidate actions and geometric movement choices without health-based tactical gates.
Micro receives targets, recent HP changes, individual allies and estimated summon timing. Explicit
delegation determines which units it controls throughout combat, movement, scouting and recovery.
Direct macro orders take control back and invalidate older micro replies, except a cast or item
use, which keeps the unit delegated while micro waits for it to go off. Summons join their summoner's group. Loot collection and spell
interruption are controller choices; the dispatcher does not add corrective orders or a gameplay
legality model. Native acceptance and later observed execution remain distinct.

Agent build commands use Warcraft's native site search through `wc3hook/placement.c`, without
starting an AI controller. The selected point becomes a normal recorded build order; `step()`
returns its coordinates, and later observations confirm execution. The engine owns site selection and pathing;
the hook only rejects picks that overlap sites already promised to pending build orders. See [action semantics](specs/actions.md#native-building-placement).

The shared hook provides configurable melee-AI difficulty and optional local overlays; see
[difficulty and overlays](specs/protocol.md#difficulty-and-local-overlays).
[`tools/prepare/`](../tools/README.md) extracts a reusable JSON reference and builds
scenario maps. `tools/prepare/gamedata.py` and `mpq.py` read the archives;
`STORMLIB_DLL` selects its archive library. Its [runner](../wc3agent/README.md#running) validates
the prepared artifacts, launches the standard environment DLL, supplies inputs to the
agent and records sessions. Runtime agent and
runner code require neither StormLib nor preparation modules.

[`docker/`](../docker/README.md) packages the same environment under Wine on Linux.
Its `environment` target contains the game, Wine, Windows Python and `wc3env`;
the optional `agent` target adds the policy, runner and prepared data. Builders
generate the hook and prepared inputs on Windows, then `docker/prepare.py` combines
them with allowed files from their own installation. No game files, prepared data
or images are distributed. Activation files stay outside the image and are
supplied through a read-only `/run/wc3-license` mount; retained output goes to a
mounted `/sessions` directory.

The host must support Wine's x86 syscall entry. `docker/platform_probe.py` checks
that before Wine starts, and `docker/smoke.py` verifies real engine control.
