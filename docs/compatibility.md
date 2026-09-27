# Compatibility evidence: Warcraft III 1.27a

This fork is pinned to the x86 `War3.exe` / `Game.dll` pair in [the port report](port-127a.md).
The predecessor's 1.29 measurements do not establish compatibility with this build.

Verified on the local Windows machine on 2026-09-27:

- All 12 focused real-game modules and all four core scenarios passed.
- All 16 extended scenarios passed together after fixing the 1.27a fixture prerequisites.
- All three native AI difficulties, AI-backed agent startup, D3D9 presentation toggles and native text display passed.
- Complete native matches repeated across in-process reload and process replacement.
- Three additional map/race/seed combinations reproduced their complete state sequences.
- Fresh movement, building and combat recordings matched independent native replay playback.
- Two, four and eight map slots supported independent control and observation.
- 2,048 additional flying units remained observable and controllable with presentation on and off.
- 64 session resets passed using the default 32-episode recycle policy; sampled private memory
  at reset 10/20/30 was 254.3/255.9/257.0 MiB, and at reset 40/50/60 was 249.2/251.0/253.3 MiB.
  These are measurements from this workload, not universal bounds.
- The wheel installed in a fresh virtual environment; its bundled DLL moved a real unit,
  advanced four exact 250 ms steps and reset the map in the same process.

Raw evidence is retained locally in `runs/formal-*.log` and `runs/compatibility-127a-soak.json`.
The latter records machine details, timings and individual reset samples.
Tests distinguish native acceptance from observed execution and real time from simulation time.

## Reproduce

```powershell
wc3hook/build.bat
python -m tests.e2e
python -m tests.e2e.extended
python tools/check_compatibility.py --only reset-soak --soak-resets 64 --output runs/compatibility-127a-soak.json
```

Warcraft files and maps stay local. Other patches, graphics backends, Windows installations,
custom-map modifications and Linux/Wine require separate validation. Network play is not part
of this offline adapter. The inherited Docker workflow has not been validated for 1.27a.
