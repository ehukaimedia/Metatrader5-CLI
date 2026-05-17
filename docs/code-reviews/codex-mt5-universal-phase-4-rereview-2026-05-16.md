# Codex Re-review - Phase 4 Strategy Tester Driver Fixes

Review target: `mt5-universal` at `6ba5c80` (`6ba5c80108a5e49ae445bd1b534a833d5c3f7467`)
Fix range: `dbe3a0f..6ba5c80`
Full Phase 4 context: `78399d9..6ba5c80`

Decision: **GO**. All four prior P2 findings from `docs/code-reviews/codex-mt5-universal-phase-4-review-2026-05-16.md` are closed. No new findings.

## Findings

No findings.

## Verified Closures

- **P2 #1, missing `equity_curve`: closed.** `mt5_cli/tester/results.py:116` through `mt5_cli/tester/results.py:181` now derives a balance/equity curve from deals or prefers an explicit balance/equity table. `mt5_cli/tester/results.py:245` through `mt5_cli/tester/results.py:256` returns `equity_curve` from `parse_html_report()`, and `mt5_cli/tester/results.py:308` through `mt5_cli/tester/results.py:318` always emits `equity_curve` in assembled envelopes. Regression coverage exists in `tests/test_tester_results_html.py:36` through `tests/test_tester_results_html.py:58`.

- **P2 #2, journal parse traceback:** closed. `_to_iso()` now returns `None` for malformed timestamps instead of raising at `mt5_cli/tester/results.py:82` through `mt5_cli/tester/results.py:92`, and `parse_journal()` now uses `csv.reader`, skips headers, skips malformed rows, and preserves comma-bearing messages at `mt5_cli/tester/results.py:259` through `mt5_cli/tester/results.py:282`. `mt5/cli.py:1326` through `mt5/cli.py:1335` also wraps `tester show` parsing in a `TESTER_PARSE_ERROR` envelope as a belt-and-suspenders guard.

- **P2 #3, invalid modelling raw `ValueError`: closed.** `mt5_cli/tester/ea.py:20` through `mt5_cli/tester/ea.py:26` centralizes `UNKNOWN_MODELLING`, and `ea.single()` / `ea.optimize()` return that envelope before discovery, run-dir creation, or launcher calls at `mt5_cli/tester/ea.py:58` through `mt5_cli/tester/ea.py:60` and `mt5_cli/tester/ea.py:134` through `mt5_cli/tester/ea.py:136`. `mt5_cli/tester/indicator.py:24` through `mt5_cli/tester/indicator.py:28` does the same for indicator visual tests.

- **P2 #4, optimize `.set` / parameter surface:** closed. `mt5_cli/tester/ini_builder.py:148` through `mt5_cli/tester/ini_builder.py:177` now renders/writes `.set` files from fixed inputs or optimization ranges. `mt5_cli/tester/ea.py:142` through `mt5_cli/tester/ea.py:167` rejects `params` plus `set_file`, checks missing set files, and generates a run-dir `.set` when `params` are supplied; `mt5_cli/tester/ea.py:169` through `mt5_cli/tester/ea.py:181` threads that effective file into the INI. `mt5/cli.py:1225` through `mt5/cli.py:1241` exposes `--set-file`, repeated `--param`, and the CLI mutual-exclusion envelope.

## Replayed Probes

Prior `equity_curve` probe:

```text
parse keys ['deals', 'equity_curve', 'metadata', 'stats']
env data keys ['deals', 'equity_curve', 'journal_events', 'metadata', 'optimization', 'run_id', 'stats']
equity_curve in parsed? True 3
equity_curve in envelope? True 3
```

Prior headered journal probe:

```text
{"ok": true, "data": {"run_id": "bad_run", "metadata": {"symbol": "AUDUSD"}, "stats": {}, "deals": [], "equity_curve": [], "journal_events": [], "optimization": []}}
```

Prior direct-library invalid modelling probe:

```text
ea.single {'ok': False, 'error': {'code': 'UNKNOWN_MODELLING', 'message': "Unknown modelling 'bad-model'. Known: ['every-tick', 'math', 'ohlc-1m', 'open-only', 'real-ticks']"}}
ea.optimize {'ok': False, 'error': {'code': 'UNKNOWN_MODELLING', 'message': "Unknown modelling 'bad-model'. Known: ['every-tick', 'math', 'ohlc-1m', 'open-only', 'real-ticks']"}}
indicator.visual {'ok': False, 'error': {'code': 'UNKNOWN_MODELLING', 'message': "Unknown modelling 'bad-model'. Known: ['every-tick', 'math', 'ohlc-1m', 'open-only', 'real-ticks']"}}
```

Prior optimize surface probe:

```text
Options:
  --mode [complete|genetic|math]
  --forward TEXT
  --set-file FILE
  --param TEXT                    EA input as Name=value or optimization range
                                  Name=value,start,step,stop.
```

Generated `.set` probe:

```text
ExpertParameters=alpha.AUDUSD.M5.set
set files [('alpha.AUDUSD.M5.set', 'Fast=9||5||1||20||Y\nLots=0.1\n')]
```

CLI mutual-exclusion probe:

```text
{"ok": false, "error": {"code": "MT5_INVALID_PARAMS", "message": "Pass either --param or --set-file, not both."}}
```

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
499 passed in 2.45s
```

```text
python -m pytest tests/test_cli_tester.py tests/test_tester_cache.py tests/test_tester_ini_builder.py tests/test_tester_launcher.py tests/test_tester_results_html.py tests/test_tester_results_journal.py tests/test_tester_results_envelope.py tests/test_tester_ea.py tests/test_tester_indicator.py -q
```

Output:

```text
66 passed in 0.27s
```

```text
python -m pytest tests/test_bridge_singleton.py -q
```

Output:

```text
15 passed in 0.08s
```

```text
git diff --check dbe3a0f..6ba5c80
```

Output: exit `0`, no output.

```text
git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5 mt5_mcp
```

Output:

```text
mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
mt5_cli/mql5/__init__.py:7:Bridge isolation: this package MUST NOT import MetaTrader5. All MT5
mt5_cli/tester/__init__.py:15:Bridge isolation: this package MUST NOT import MetaTrader5. terminal64.exe
```

The `mql5` and `tester` lines are docstring false positives; `tests/test_bridge_singleton.py` passed.

```text
git grep -n "from mt5_cli.bridge\|import mt5_cli.bridge\|mt5_call\|MetaTrader5" -- mt5_cli/tester
```

Output:

```text
mt5_cli/tester/__init__.py:15:Bridge isolation: this package MUST NOT import MetaTrader5. terminal64.exe
mt5_cli/tester/ea.py:5:It intentionally does not import the MetaTrader5 Python SDK.
```

Both are docstring/comment false positives.

```text
git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
```

Output: both exit `1`, no output.

```text
python -m mt5.cli --json tester list
```

Output:

```text
{"ok": true, "data": [{"run_id": "2026-05-17T02-41-15_ind-ind_AUDUSD_M5", "path": "results\\2026-05-17T02-41-15_ind-ind_AUDUSD_M5"}, {"run_id": "2026-05-17T02-41-15_alpha_AUDUSD_M5", "path": "results\\2026-05-17T02-41-15_alpha_AUDUSD_M5"}]}
```

The listed runs are local ignored artifacts created by targeted review probes; the command still emitted a valid envelope.

## Open Questions / Assumptions

- I scoped this re-review to the four prior P2 findings and the immediate fix delta `dbe3a0f..6ba5c80`, while keeping the full Phase 4 context in mind.
- I did not run a real MT5 Strategy Tester live smoke. That remains Bones' demo-only E2E/tag step after GO.
- The untracked `shared/bones-phase-4-orchestrator-handoff-2026-05-16.md` file is coordination context from the harness handoff and was not part of the code checkpoint.
