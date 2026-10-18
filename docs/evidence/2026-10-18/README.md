# Review evidence, 2026-10-18

The original preparation results below remain historical evidence. After approval
of scheme B, the actual filtered publication checkout was tested separately:
[filtered-checks.json](filtered-checks.json) records 116 Host tests without skips,
156 agent tests, Hook build/native regressions and Ruff, all PASS. No game was
started. [history-rewrite.json](history-rewrite.json) records old/new commit IDs;
[filtered-history-audit.json](filtered-history-audit.json) checks the fresh object
database. The older `publication-audit.json` inventory describes the pre-filter
repository; its 14 binary objects are **not** present in the published graph.

This folder is a **derived review bundle**, not a replacement for the original
local logs and not a claim that a new game was run during publication preparation.
Private configuration, installation files, full runtime output and credentials
are excluded. The full [validation report](../../WC3ENV_127A_VALIDATION.md)
records the local paths and original commands.

| File | What it proves or records |
|---|---|
| [native-summary.json](native-summary.json) | Selected observed values from the prior real-game run: connection, units/resources, movement, building, damage, reset, exact step, fixed-seed repeatability and two independent instances |
| [source-artifacts.json](source-artifacts.json) | SHA-256 and size of the original successful and failed logs/traces; originals remain in the local `runs/recovery-20261018-01` directory |
| [publication-checks.json](publication-checks.json) | Actual offline/build command results from the independent publication checkout, including both failed host runs and the successful rerun |
| [publication-audit.json](publication-audit.json) | Complete local Git object scan, historical binary inventory, obsolete replay headers and authenticated GitHub repository-existence query |

The native result comes from the source at `85fcefdf1f9019dd92a40e109d544ec656d0d158`.
Its command/trace artifacts are separate from the publication checkout checks.
The failed first native harness attempt is retained in the summary as well as
the local raw files; it is not replaced with the later PASS.

Publication preparation used the existing Python 3.12 environment, with
`PYTHONPATH` pointing to this checkout's `src` and `wc3agent/src`. Placeholder
paths in `publication-checks.json` stand for that interpreter and checkout;
original command JSON files retain the literal paths locally.

- Host unit coverage: **PASS**, 116 tests in two commands. Discovery reported
  114 entries, including one skipped module (`test_scenario_steps`) because its
  import passes through the e2e package's installation-path gate. The 113 actual
  tests passed. Supplying the existing installation path only through the process
  environment let the skipped module's 3 synthetic unit tests pass separately;
  those tests do not launch a game. No game configuration file was copied.
- Agent unit suite: **PASS**, 156 run.
- Hook compilation and native JSON/clock/allocator regressions: **PASS**.
- Ruff check and format check: **PASS**.
- New native game execution and clean wheel installation: **NOT RUN** in this
  preparation task. The production Hook and SDK source were not changed.
- Initial host unit checks: **FAIL**, two `FileNotFoundError` errors. The fresh
  checkout lacked its generated DLL; the test's mocked settings also ignore
  `WC3_HOOK_DLL`. Copying the freshly built DLL into the ignored package-native
  directory satisfied the repository's normal build-before-test prerequisite.
- Two old checked-in replay fixtures: **FAIL** against the 1.27 parser gate,
  because both are unchanged upstream version 29/build 6060 recordings. They are
  omitted from the proposed tree. Current native replay tests generate new
  temporary recordings, and were not rerun here.

A hash identifies an artifact but does not make its contents available to a
remote reviewer. The summary cannot prove arbitrary-match determinism, death
without a callback, product integration, or performance under sustained load.
