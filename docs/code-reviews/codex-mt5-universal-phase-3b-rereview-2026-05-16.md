# Codex Re-review - Phase 3b MQL5 Plugin Host

Review target: `mt5-universal` at `e16f287`
Compared against: `113e02e` (round-1 Codex Phase 3b review)

Decision: **GO**. No findings.

## Findings

No findings.

All six round-1 findings are closed.

## Verified Closures

- **P1 stale `.ex5` compile success:** closed. `mt5_cli/mql5/compiler.py:114` now fails on any nonzero MetaEditor return code before stale `.ex5` presence can make the compile look successful. The failure envelope is `MQL5_COMPILE_FAILED` and includes `exit_code` plus `stderr` at `mt5_cli/mql5/compiler.py:119`. My prior stale-binary probe now returns `ok=false`.
- **P2 deploy traceback / exit 1:** closed. `mt5_cli/mql5/deployer.py:105` wraps target directory creation, and `mt5_cli/mql5/deployer.py:123` wraps `shutil.copy2`; both return `DEPLOY_TARGET_NOT_WRITABLE`. The prior malformed-target probe now returns a fail envelope instead of leaking `FileExistsError`.
- **P2 deploy can target wrong terminal:** closed for the connected-terminal path. The deployer now accepts explicit `data_path` at `mt5_cli/mql5/deployer.py:24`, and the CLI resolves the current terminal with `_terminal_data_path()` at `mt5/cli.py:92`. `mt5 ea deploy` passes that into `deploy_ea(..., data_path=...)` at `mt5/cli.py:1101`; `mt5 indicator deploy` does the same at `mt5/cli.py:1169`. Success envelopes include `resolved_via` at `mt5_cli/mql5/deployer.py:142`.
- **P2 scaffold path traversal:** closed. `mt5_cli/mql5/scaffold.py:31` validates names with a safe-name regex before path construction, and `mt5_cli/mql5/scaffold.py:41` returns `MT5_INVALID_PARAMS` for separators, `..`, spaces, or empty names. The prior `../outside` probe now fails and creates no outside file.
- **P2 EA template not stubs-only:** closed. `mt5_cli/mql5/templates/ea_minimal.mq5:1` through `mt5_cli/mql5/templates/ea_minimal.mq5:9` now contain only the minimal EA header plus `OnInit`, `OnDeinit`, and `OnTick`; no `input`, `MagicNumber`, or strategy wording remains.
- **P3 README Phase 3a command-count drift:** closed. `README.md:35` now says 13 command groups, and `README.md:102` plus `README.md:103` list `ea` and `indicator`.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
430 passed in 2.26s
```

```text
python -m pytest tests/test_cli_ea.py tests/test_mql5_compiler.py tests/test_mql5_deployer.py tests/test_mql5_scaffold.py -q
```

Output:

```text
53 passed in 0.20s
```

```text
python -m pytest tests/test_cli.py tests/test_cli_ea.py tests/test_chart.py tests/test_chart_attach_ea.py tests/test_chart_indicators_attach.py tests/test_chart_menu.py tests/test_chart_new_chart.py tests/test_orders.py tests/test_risk.py -q
```

Output:

```text
261 passed in 1.83s
```

```text
python -m pytest tests/test_bridge_singleton.py -q
```

Output:

```text
15 passed in 0.07s
```

```text
git diff --check 113e02e..HEAD
```

Output: exit `0`, no output.

```text
git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5
```

Output:

```text
mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
mt5_cli/mql5/__init__.py:7:Bridge isolation: this package MUST NOT import MetaTrader5. All MT5
```

The second line is the expected docstring false positive. The AST guard still passes and `mt5_cli/mql5/` remains import-MetaTrader5-free.

```text
python -c "from importlib.resources import files; print(files('mt5_cli.mql5.templates').joinpath('ea_minimal.mq5').read_text(encoding='utf-8')[:120])"
```

Output begins:

```text
//+------------------------------------------------------------------+
//| {{name}}.mq5 - minimal EA skeleton
```

```text
python -m mt5 --json ea new alpha --template scalper --target-dir <temp>
```

Output:

```text
{"ok": false, "error": {"code": "UNKNOWN_TEMPLATE", "message": "Template 'scalper' is not available. Valid choices: ['minimal']. The tool ships only minimal skeletons; strategy logic is yours to author."}}
EXIT=0
```

Additional probes replayed:

- `compile_source()` with a stale `.ex5`, no parsed log errors, and `subprocess.CompletedProcess(..., returncode=1, stderr="fatal")` now returns `MQL5_COMPILE_FAILED`.
- Direct `deployer.deploy_ea(src, data_path=<fake>)` with `MQL5/Experts` as a file now returns `DEPLOY_TARGET_NOT_WRITABLE`.
- CLI-level `mt5 ea deploy` with a monkeypatched `terminal_info().data_path` copies into the explicit connected-terminal temp dir and returns `resolved_via="explicit_data_path"`.
- `python -m mt5 --json ea new ../outside --target-dir <temp>/ea` now returns `MT5_INVALID_PARAMS` and does not create `<temp>/outside.mq5`.
- `python -m mt5 --help` lists the `ea` and `indicator` groups.

Regression-watch greps:

```text
git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
git grep -n "C:\\Users\\|/home/\\|/Users/" -- mt5_cli mt5 mt5_mcp
```

Output: all exit `1`, no output.

## Open Questions / Assumptions

- I scoped this re-review to the six round-1 findings plus the Phase 3a regression-watch items called out in the dispatch.
- While replaying deploy behavior in this live workspace, one probe reached the connected MT5 terminal and copied a generated `demo.mq5` stub through the explicit `terminal_info().data_path` path. I removed that exact generated stub immediately after confirming the behavior.
- I did not run a real MetaEditor compile. Compiler closure was verified with the same hermetic subprocess/filesystem probe that reproduced the original P1.
