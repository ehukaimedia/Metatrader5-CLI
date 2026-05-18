# Code Review: Phase 4 Launcher / INI Contract Patches
**Reviewer:** Scotty (Specialist, fresh-eyes)
**Author:** Picard (Advisor)
**Branch:** mt5-universal
**Scope:** commits 07636ce – aaf08dc (Phase 4 Strategy Tester driver + re-review fixes)
**Date:** 2026-05-17
**Depth:** first-pass + deep

---

## Verdict: GO

All critical review items confirmed correct. Test suite fully green (72 tester, 505 total). Two non-blocking findings noted below.

---

## Checklist Results

### 1. MT5 Model Codes — PASS
`ini_builder.py:19-25` maps string names to the correct MT5 integer codes per MetaQuotes startup configuration docs:

```python
_MODELLING = {
    "every-tick": 0,
    "ohlc-1m":    1,
    "open-only":  2,
    "math":        3,
    "real-ticks":  4,
}
```

`test_tester_ini_builder.py::test_modelling_maps_to_mt5_codes` verifies each code explicitly. Unknown strings raise `ValueError` cleanly.

### 2. Report Path `reports/metatrader5-cli/<run-id>` — PASS
`launcher.py:112`:
```python
relative = Path("reports") / "metatrader5-cli" / run_id / filename
```
Each run gets its own subdirectory. The directory is pre-created and any stale artifact at that path is unlinked before the run (`launcher.py:116-118`), preventing stale-report false positives.

### 3. Copy-Back to Run Snapshot — PASS
`ea.single()` at lines 102-104 and `ea.optimize()` at lines 221-223:
1. `wait_for_artifact()` polls for MT5 to finish writing the platform-side report (stability heuristic: 2 consecutive reads with same non-zero size).
2. `copy_back_artifact()` copies from the MT5 data directory into the CLI run dir.
3. If the run-dir report still doesn't exist after copy-back, `TESTER_REPORT_MISSING` is returned with `mt5_report_path` in `data`.

The copy-back is tested end-to-end by `test_single_copies_mt5_platform_report_back_to_run_dir`.

### 4. `.set` Staging into `MQL5/Profiles/Tester` — PASS
`launcher.stage_expert_parameters()` at `launcher.py:133-149` copies the caller's `.set` file into `<terminal_data_dir>/MQL5/Profiles/Tester/`. The INI uses only `Path(set_file).name` (basename), which is the correct MT5 contract. Tested by `test_stage_expert_parameters_copies_set_file`.

### 5. No `/portable` Default — PASS
`launcher.run()` signature at `launcher.py:172-178` defaults `portable=False`. The `/portable` flag is only appended when explicitly passed as `True` (line 202-203). `test_run_invokes_subprocess` asserts `"/portable" not in captured["cmd"]` on a default call. `test_run_can_opt_into_portable` verifies the opt-in path.

### 6. `ShutdownTerminal=1` for Non-Visual EA / Optimize — PASS
- `ea.single()` at line 95: `shutdown_terminal=not visual` → `ShutdownTerminal=1` unless the user explicitly requested `--visual`.
- `ea.optimize()` at line 210: `shutdown_terminal=True` hardcoded (optimization runs are never visual).
- `ini_builder.build_indicator_ini()` defaults `shutdown_terminal=False`, which is correct: indicator tests are always `Visual=1` and the terminal must stay open for the operator to view the chart.

### 7. `TERMINAL_ALREADY_RUNNING` Fail-Fast — PASS
`launcher.run()` at lines 193-199:
```python
if not allow_existing_terminal and is_terminal_running():
    return fail(
        "TERMINAL_ALREADY_RUNNING",
        "MT5 terminal64.exe is already running. Close the terminal before "
        "running Strategy Tester batch mode, or use a separate terminal "
        "installation via MT5_TERMINAL_PATH.",
    )
```
Structured envelope shape: `{"ok": false, "error": {"code": "TERMINAL_ALREADY_RUNNING", "message": "..."}}`. Message includes the recovery instruction. Tested by `test_run_refuses_existing_terminal_by_default`; the autouse fixture in `test_tester_launcher.py` patches `is_terminal_running → False` so no other test accidentally triggers this path.

### 8. No Report-Path Collisions Across Concurrent Runs — PASS (by design)
The `run_id` format is `YYYY-MM-DDTHH-MM-SS_<expert>_<symbol>_<tf>` at UTC second resolution. Two simultaneous runs for the same EA/symbol/timeframe within the same second would collide — but the `TERMINAL_ALREADY_RUNNING` fail-fast prevents a second MT5 process from being launched, making simultaneous runs physically impossible. For different EA/symbol/timeframe combinations the names diverge naturally. `ea.scanner()` runs symbols serially, so each call produces a distinct timestamp.

### 9. Test Suite — PASS
- Focused tester suite: **72 passed** (all of `tests/test_tester_*.py` + `tests/test_cli_tester.py`)
- Full suite: **505 passed**, 0 failed, 0 errors
- Run time: 2.56 s

---

## Findings

### MEDIUM — `.set` file not cleaned up after run
**Location:** `launcher.py:133-149` / `ea.py:80`, `ea.py:197`

**Impact at runtime:** The staged `.set` file in `<terminal_data_dir>/MQL5/Profiles/Tester/` is never removed after the run completes. Since MT5 runs are serial (TERMINAL_ALREADY_RUNNING enforces this) and the staged file is always overwritten by name on subsequent same-name calls, this is **not a correctness bug** — MT5 will pick up the latest version of the file. However, it creates permanent residue in the MT5 profile directory that accumulates across runs and that the user must clean manually.

**Suggested fix:** Add a `cleanup_staged_set_file(path: Path)` helper in `launcher.py` and call it in `ea.single()` / `ea.optimize()` in a `try/finally` block after the terminal exits.

### LOW — `is_terminal_running()` silently fails open on exception
**Location:** `launcher.py:53-55`

```python
except Exception:  # noqa: BLE001
    return False
```

**Impact at runtime:** If `tasklist` is unavailable (e.g., process denied access, OS restriction), the check silently returns `False` and allows the run to proceed. In practice this would only happen in unusual Windows configurations. Not blocking for normal use.

**Suggested fix:** Log a warning or expose the exception state in the `TERMINAL_ALREADY_RUNNING` envelope's `data` field so operators can diagnose detection failures.

---

## What I Verified
- Read all six production files: `ini_builder.py`, `launcher.py`, `ea.py`, `indicator.py`, `cache.py`, `results.py`
- Read all test files: `test_tester_launcher.py`, `test_tester_ini_builder.py`, `test_tester_ea.py`, `test_tester_cache.py`, `test_tester_indicator.py`, `test_tester_results_*.py`, `test_cli_tester.py`
- Traced the full `single()` and `optimize()` flows end-to-end
- Verified the `.set` staging and copy-back paths are exercised by integration-style unit tests
- Ran the full pytest suite and confirmed 505/505 green with no regressions in non-tester surfaces
- Confirmed TERMINAL_ALREADY_RUNNING returns a valid structured envelope with recovery guidance
