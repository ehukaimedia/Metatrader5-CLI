# Codex Re-review 2 - Phase 3a CLI Fixes

Review target: `mt5-universal` at `6515738`
Compared against: `8fc6227` (round-2 Codex re-review checkpoint)

Decision: **GO**. No findings.

## Findings

No findings.

The single remaining P2 from the round-2 review is closed: `attach_ea(chart_id=...)` now verifies the supplied `chart_id` against `enumerate_chart_children(match.hwnd)` before attempting activation or posting the EA menu command.

## Verified Closure

The prior failure mode was: a stale or wrong-parent `chart_id` could pass through `activate_chart()` because `WM_MDIACTIVATE` can return normally even when the hwnd is not an MDI chart child. `attach_ea()` then posted the Expert Advisor `WM_COMMAND` to the MT5 parent, risking attachment to whichever chart was actually active.

Current trace:

- `mt5_cli/chart/attach_ea.py:114` enters the explicit `chart_id` branch.
- `mt5_cli/chart/attach_ea.py:126` enumerates chart children for the matched MT5 parent before activation.
- `mt5_cli/chart/attach_ea.py:134` fails with `CHART_ID_NOT_FOUND` if the requested hwnd is not in the enumerated child set.
- `mt5_cli/chart/attach_ea.py:144` calls `activate_chart()` only after the child membership check passes.
- `tests/test_chart_attach_ea.py:269` adds the stale/non-child regression test and asserts both `WM_MDIACTIVATE` and `WM_COMMAND` do not fire.
- `tests/test_chart_attach_ea.py:237` updates the happy path so a real enumerated chart child still exercises activation.
- `tests/test_chart_attach_ea.py:318` keeps the second gate where activation can still fail after a verified child and must not post `WM_COMMAND`.

Replay of my prior stale-hwnd probe with `chart_id=9999` absent from the enumerated set:

```text
{'ok': False, 'error': {'code': 'CHART_ID_NOT_FOUND', 'message': 'chart_id 9999 is not an open MDI child of the matched MT5 window. Detected charts: 2000:EURUSD,M15 ([EURUSD,M15])'}}
mdi_activate_calls= []
wm_command_calls= []
```

That is the desired fail-closed behavior.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
367 passed in 2.07s
```

```text
python -m pytest tests/test_chart_attach_ea.py -q
```

Output:

```text
15 passed in 0.50s
```

```text
git diff --check 8fc6227..HEAD
```

Output: exit `0`, no output.

```text
git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5
```

Output:

```text
mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
```

```text
git diff 8fc6227..HEAD -- mt5_cli/chart/attach_ea.py tests/test_chart_attach_ea.py
```

Output reviewed: the range only changes `attach_ea.py` and `tests/test_chart_attach_ea.py`, adding the enumerate-then-verify gate plus the stale-hwnd regression test.

## Open Questions / Assumptions

- I scoped this round-3 review to the single remaining P2 from the round-2 NO-GO, per the dispatch directive.
- I did not re-run live MT5 GUI operations. The stale-hwnd behavior was verified with the same isolated fake-Win32 probe that reproduced the prior failure, plus the focused unit test and the full suite.
