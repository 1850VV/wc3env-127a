# 1.27a API compatibility

This document describes original `85fcefd` source (filtered-history counterpart
`4f2b661`) plus documentation and validation scripts. See the
[commit mapping](HISTORY_REWRITE.md). It does not claim parity with newer upstream `d45a7b5`.

| API/capability | Local interface | Evidence and limit |
|---|---|---|
| Single-player wrapper | `WC3Env(GameConfig(...))` | Implemented; single-agent view over GameSession |
| Shared game | `GameSession`, `PlayerConfig`, `PlayerView` | One simulation clock, combined player actions; minimal native validation PASS |
| Reset | `GameSession.reset()` | Map reload at the initial 1-second hold; normal in-process reload and process replacement tested; not arbitrary save-state restoration |
| Step | `GameSession.step(actions_by_slot, ms=None)` | Returns `(observations, done, info)`; 25ms multiples, 25..60000ms; exact 25ms native check PASS |
| Wrapper step | `WC3Env.step(actions, seconds=None)` | Returns `(observation, done, info)`; no reward field/Gymnasium five-value contract |
| Multiple independent games | `StepPool.launch/launch_configs`, `step_all` | Two distinct processes/directories/clocks passed; round-based thread fan-out |
| VectorSession | Not provided | New upstream async `send/recv`, worker recycling and remote/Wine workers are not ported |
| Binary observations | Not provided | JSON named-pipe RPC is available; new upstream shared-memory binary API is not ported |
| Move/attack/build | `Action(unit_id, command, arguments)` | Real displacement, HP decrease and construction start/finish verified; ACK alone is not completion |
| Other actions | train/research/cast/items/revive/etc. | Implemented with historical native coverage; not all rerun during 2026-10-18 minimal validation |
| Observations | `Observation` or raw dictionaries | Own units, visible other units, inside units, resources, positions, orders and events; fog rules apply |
| HP/death | Integer HP in base observation | Zero integer HP or disappearance is not a death callback; no general projectile-release/damage-event API |
| Pause and speed | Stepping hold; `debug("speed", factor=...)` | Hold and short samples verified; factor is not a guaranteed wall-clock throughput |
| Reproducibility | `MatchSetup(seed=...)` | Fixed-seed combat fixture repeated across reset and process replacement; arbitrary matches not revalidated |
| Legacy bundled replay fixtures | Two upstream version-29 recordings | FAIL against the version-27 parser gate; omitted from the proposed tree. Current native replay tests generate fresh temporary recordings; not rerun during synchronization preparation |
| Graphics/OS | Windows x64 host, x86 game, D3D9 | `render=False` still needs a window/device; this port's Wine/headless/network support is not established |

The precise supported `War3.exe` and `Game.dll` hashes are in the
[port report](port-127a.md). Do not replace them with another version's hashes or
memory offsets. [Chinese API guide](features-127a.md) contains normal usage.

## Reproduce the bounded audit

The verification tools are independent of the core Hook. Use an existing prepared
environment and a **new** output directory:

```powershell
python tools/validate_127a_recovery.py snapshot --output runs/my-audit
python tools/validate_127a_recovery.py build --output runs/my-audit
New-Item -ItemType Directory -Force src/wc3env/native | Out-Null
Copy-Item runs/my-audit/build-source/src/wc3env/native/wc3hook.dll src/wc3env/native/wc3hook.dll
python tools/validate_127a_recovery.py offline --output runs/my-audit
$env:WC3_HOOK_DLL=(Resolve-Path runs/my-audit/build-source/src/wc3env/native/wc3hook.dll).Path
$env:WC3_OUTPUT_DIR='D:/wc3env-runs/my-audit'
python tools/validate_127a_native.py --output runs/my-audit/native --runtime D:/wc3env-runs/my-audit
python tools/validate_127a_recovery.py preserve --output runs/my-audit
```

Snapshot/offline/build are host/static/build checks. On a clean checkout, the
generated DLL is copied to the ignored package-native path because launch unit
tests expect the normal build-before-test prerequisite. Do this in a dedicated
verification checkout so an existing local DLL is preserved. The native command starts
isolated offline games and must only be run when that game execution is authorized.
It preserves failures and closes its owned games. It does not train an RL model.

See [the full validation report](WC3ENV_127A_VALIDATION.md) and the portable
[evidence summary](evidence/2026-10-18/README.md). Local raw-log links in the full
report intentionally remain local; missing hosted logs are not newly run tests.
