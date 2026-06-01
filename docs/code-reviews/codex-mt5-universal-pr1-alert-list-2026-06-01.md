# Code Review: PR #1 Read-Only Alert List

**Branch:** `mt5-universal`  
**Target:** `c5a4a30d01f8d4dbefcadd8574f50d2f2bfc7176`  
**Base for focused review:** `f8b5127`  
**Reviewer:** Codex  
**Date:** 2026-06-01  
**Verdict:** GO for read-only `mt5 alert list`

## Scope

This review focuses on the single read-only alert-list commit `c5a4a30`, compared to
the already-reviewed Phase 5 Wave A.1 head `f8b5127`.

Wave A.1 was skimmed only. Its existing Scotty review records a GO verdict and
is outside this focused re-review.

The deferred write branch `alert-write-path-deferred` was inspected only enough
to confirm it still contains `set` / `delete` work that is not present in this PR.
It was not live-validated in this review.

## Findings

No Critical or Important issues found in the read-only `alert list` PR.

### Minor / Non-Blocking

**M1 - CLI-level alert-list wiring is not directly regression-tested - fixed in follow-up**
`mt5/cli.py:279` wires the new `alert list` command, including the
`_terminal_data_path(ctx.obj["cfg"])` autoconnect/data-path lookup. The library
behavior is covered in `tests/test_alert.py`, and the top-level help surface is
covered in `tests/test_cli.py`, but there is no focused CLI invocation test that
stubs `_terminal_data_path` and asserts `alert list` passes the connected
terminal data path into `_alert_mod.list_alerts`.

This is not blocking because the production wiring is simple and live dogfood
confirmed the running-terminal path returns `resolved_via="explicit_data_path"`.
Adding the CLI seam test would make the I1 behavior cheaper to preserve.

Follow-up resolution: `tests/test_cli.py` now includes
`test_alert_list_threads_terminal_data_path_from_bridge`, which stubs
`_terminal_data_path` and asserts `alert list` passes the connected terminal
data path through to `_alert_mod.list_alerts`.

## Verification Against Requested Checks

- No machine-specific hardcoded path remains in the changed runtime code.
  `rg` found no user-profile path references in `mt5/` or `mt5_cli/`, and the
  only terminal-hash literal is the negative assertion in `tests/test_alert.py`.
- Alert path resolution funnels through the single
  `mt5_cli/alert/alert.py:_resolve_alerts_path` chokepoint.
- The read path is fail-fast: `_load_alert_records` requires
  `expected_size == len(data)` before slicing records and returns
  `ALERTS_FILE_FORMAT` otherwise.
- Runtime returns use the standard `ok()` / `fail()` envelopes from
  `mt5_cli.reports`.
- `set` / `delete` are absent from `mt5-universal` at `c5a4a30`; the only write
  in the focused code is the test fixture that creates a temporary sample
  `alerts.dat`.

## Strengths

- The write path is correctly deferred from this PR. The read-only surface avoids
  the unvalidated `alerts.dat` mutation risk.
- The parser is intentionally narrow and refuses size/layout drift instead of
  guessing.
- `resolved_via` is surfaced in the success envelope, which gives operators a
  useful audit signal for explicit data-path pinning versus fallback discovery.
- The connected-terminal data path is threaded through the CLI, preventing the
  multi-terminal newest-mtime heuristic from winning while MT5 is reachable.

## Autoconnect Recommendation

Recommendation: keep the autoconnect/data-path pin for normal `mt5 alert list`
for this PR, and add a pure-filesystem option only if a high-frequency scanner
becomes a real caller.

Reasoning: for a human/operator command, reading the connected terminal's
`alerts.dat` is more important than avoiding a small connection attempt. The
live running-terminal dogfood returned in 158 ms with
`resolved_via="explicit_data_path"`. The trade-off should be revisited if the
command is called in a tight polling loop; in that case, either skip
`_terminal_data_path` when `--alerts-path` / config / `MT5_ALERTS_PATH` is
already explicit, or add an explicit filesystem-only mode.

## Dogfood Notes

Read path with MT5 running:

- Command: `python -m mt5 --json alert list`
- Result: `ok: true`
- `resolved_via`: `explicit_data_path`
- Count: 13 alerts
- Wall-clock: 158 ms

Offline read-path timing was not captured because MT5 was still running as
`terminal64` during this review. I did not close the user's terminal.

Write-path validation was not performed. The live protocol requires MT5 closed,
a backup of the real `alerts.dat`, CLI writes from `alert-write-path-deferred`,
and human verification in the MT5 Toolbox > Alerts tab after reopening. Without
that human verification, `set` / `delete` should not graduate from the deferred
branch.

## Validation

```text
python -m pytest tests/test_alert.py -q
5 passed in 0.02s
```

```text
python -m pytest -m "not integration" -q
532 passed in 3.23s
```

```text
git diff --check f8b5127..c5a4a30
passed
```

## Merge Verdict

Ready to merge: Yes, for read-only `mt5 alert list`.

Do not merge the deferred write path yet. It still needs live round-trip
validation against MT5 plus the previously identified write-path hardening
around IDs, empty files, backup integrity, write errors, backup proliferation,
and atomicity before a follow-up PR.
