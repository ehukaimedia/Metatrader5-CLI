# Codex Review - Phase 4 Strategy Tester Driver

Review target: `mt5-universal` at `07636ce` (`origin/mt5-universal`)
Compared against: `78399d9` (`phase-3-complete`)

Decision: **NO-GO**. I found no P1 bridge/trading-safety issue, but the Phase 4 tester surface has P2 contract gaps: required result data is missing, parser errors can escape the CLI envelope, direct library calls can raise instead of returning envelopes, and the optimization `.set`/parameter surface is not implemented.

## Findings

### P2 - Result envelopes never include the required `equity_curve`

`mt5_cli/tester/results.py:108` through `mt5_cli/tester/results.py:169` parses only `metadata`, `stats`, and `deals` from the HTML report. `mt5_cli/tester/results.py:217` through `mt5_cli/tester/results.py:225` then assembles only `stats` and `deals`; there is no `equity_curve` key in either the parser output or final envelope.

Probe:

```text
parse keys ['deals', 'metadata', 'stats']
env data keys ['deals', 'journal_events', 'metadata', 'optimization', 'run_id', 'stats']
equity_curve in parsed? False
equity_curve in envelope? False
```

Why it matters: Phase 4's chosen design is for `tester.results` to be the single JSON-serving parser for MT5 Strategy Tester artifacts. The spec's result contract includes `equity_curve`, and the review dispatch explicitly called out HTML parsing into deals plus equity curve plus stats. Without this field, agents still need to scrape or reconstruct balance/equity data themselves, which is exactly what Phase 4 is meant to prevent.

### P2 - Malformed or headered journal CSV can crash `mt5 tester show` instead of emitting an envelope

`mt5_cli/tester/results.py:180` through `mt5_cli/tester/results.py:186` accepts any comma-split 3-column row and passes the first field to `_to_iso()`. `_to_iso()` at `mt5_cli/tester/results.py:81` through `mt5_cli/tester/results.py:84` blindly unpacks `stamp.split(" ", 1)`. A normal CSV header like `time,level,msg`, or any malformed timestamp, raises `ValueError`. `mt5/cli.py:1313` through `mt5/cli.py:1320` calls `assemble()` directly, so the exception escapes Click and prints a traceback instead of the CLI's structured JSON envelope.

Probe with an existing run containing `report.html` and `journal.csv` whose first line is `time,level,msg`:

```text
ValueError: not enough values to unpack (expected 2, got 1)
  File "...mt5_cli\tester\results.py", line 186, in parse_journal
    "time": _to_iso(stamp),
  File "...mt5_cli\tester\results.py", line 83, in _to_iso
    date, time = stamp.strip().split(" ", 1)
```

Why it matters: the CLI contract is always exit 0 with an envelope, and Phase 4's parser is the trust boundary for real MT5 artifacts. A single unexpected journal row should be skipped or returned as a parse-failure envelope, not bypass `emit()` with a traceback.

### P2 - Direct tester library calls can raise `ValueError` instead of returning fail envelopes

`mt5_cli/tester/ea.py:59` through `mt5_cli/tester/ea.py:73` and `mt5_cli/tester/indicator.py:40` through `mt5_cli/tester/indicator.py:48` call the INI builder without guarding invalid modelling values. `mt5_cli/tester/ini_builder.py:27` through `mt5_cli/tester/ini_builder.py:31` raises `ValueError` for unknown modelling. The CLI masks this with `click.Choice`, but the package is library-first and future MCP tools call these library functions directly.

Probe:

```text
ea.single ValueError Unknown modelling 'bad-model'. Known: ['every-tick', 'math', 'ohlc-1m', 'open-only', 'real-ticks']
indicator.visual ValueError Unknown modelling 'bad-model'. Known: ['every-tick', 'math', 'ohlc-1m', 'open-only', 'real-ticks']
```

Why it matters: Phase 4 surfaces are supposed to compose `mt5_cli.reports.ok/fail` envelopes. Library callers should get `UNKNOWN_MODELLING` or `MT5_INVALID_PARAMS` style envelopes, not raw exceptions and partially-created run directories.

### P2 - Optimization has no `.set` generation or parameter input surface

Phase 4 calls for `ini_builder` to generate tester `.ini` plus `.set` files and the spec shows optimization with `--param`. The shipped code only accepts an optional pre-existing `set_file` in the library and writes `ExpertParameters=<basename>` into the INI at `mt5_cli/tester/ini_builder.py:80` through `mt5_cli/tester/ini_builder.py:83`. It never writes a `.set` file, and the CLI optimize command at `mt5/cli.py:1217` through `mt5/cli.py:1228` exposes only `--expert`, `--symbol`, `--tf`, dates, `--mode`, and `--forward`; there is no `--param` or `--set-file` path.

Probe:

```text
Usage: python -m mt5.cli tester ea optimize [OPTIONS]

Options:
  --expert TEXT                   [required]
  --symbol TEXT                   [required]
  --tf TEXT                       [required]
  --from TEXT                     [required]
  --to TEXT                       [required]
  --mode [complete|genetic|math]
  --forward TEXT
  --help                          Show this message and exit.
```

Why it matters: the optimization driver is nominally present, but users cannot provide tester parameter ranges through the CLI, and the library does not generate the `.set` artifact that MT5 needs for reproducible optimization inputs. This leaves the Phase 4 optimize/forward mode incomplete for agent-driven use.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
484 passed in 2.46s
```

```text
python -m pytest tests/test_cli_tester.py tests/test_tester_cache.py tests/test_tester_ini_builder.py tests/test_tester_launcher.py tests/test_tester_results_html.py tests/test_tester_results_journal.py tests/test_tester_results_envelope.py tests/test_tester_ea.py tests/test_tester_indicator.py -q
```

Output:

```text
51 passed in 0.21s
```

```text
python -m pytest tests/test_bridge_singleton.py -q
```

Output:

```text
15 passed in 0.09s
```

```text
git diff --check 78399d9..07636ce
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

The `mql5` and `tester` lines are docstring false positives. `tests/test_bridge_singleton.py` passed.

```text
git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
```

Output: both exit `1`, no output.

```text
python -c "from mt5_cli.tester import cache, ini_builder, launcher, results, ea, indicator; print('tester imports OK')"
```

Output:

```text
tester imports OK
```

```text
python -m mt5.cli --json tester list
```

Output:

```text
{"ok": true, "data": []}
```

```text
python -m mt5.cli --json tester ea single --expert alpha --symbol AUDUSD --tf M5 --from 2024-01-01 --to 2024-06-30 --modelling bad-model
```

Output:

```text
{"ok": false, "error": {"code": "MT5_INVALID_PARAMS", "message": "Invalid value for '--modelling': 'bad-model' is not one of 'real-ticks', 'every-tick', 'ohlc-1m', 'open-only', 'math'."}}
```

Additional targeted probes are included under the findings above.

## Open Questions / Assumptions

- I treated the inherited Kirk files and worker-attributed launcher/parser code as part of Scotty's submitted checkpoint, per the orchestration handoff.
- I did not run a real MT5 Strategy Tester live smoke. That remains Bones' demo-only E2E step after Spock GO.
- I did not object to the hardcoded `C:\Program Files\...terminal64.exe` fallback because the Phase 4 plan explicitly sketched the same known-path fallback and the pre-existing compiler uses the same convention.
- I did not raise the absence of `mt5 tester results <run-id>` because the Phase 4 task dispatch requested `ea/indicator/list/show`, even though the spec still mentions a `results` command.
