# Codex Review - Phase 3b MQL5 Plugin Host

Review target: `mt5-universal` at `6493512` (`6493512a1e150c48e4490c1a31f73a458e15aac4`)
Compared against: `4f586aa` (Phase 3a complete baseline)

Decision: **NO-GO**. I found one P1 and four P2 findings in the new Phase 3b surface.

## Findings

### P1 - `compile_source()` can report success for a failed MetaEditor run and return a stale `.ex5`

`mt5_cli/mql5/compiler.py:100` captures the `subprocess.run()` result, but `mt5_cli/mql5/compiler.py:107` through `mt5_cli/mql5/compiler.py:115` only fail when parsed log errors are nonzero or the `.ex5` file is absent. `proc.returncode` is placed in the error data only after the code has already decided to fail. If MetaEditor returns nonzero while an old `.ex5` from a previous compile still exists, the function returns `ok`.

Repro probe:

```text
src=demo.mq5, stale demo.ex5 exists, demo.log says "0 errors, 0 warnings",
subprocess.run returns CompletedProcess(..., returncode=1, stderr="fatal")

compile_source(src) ->
{'ok': True, 'data': {'source': '...demo.mq5', 'ex5': '...demo.ex5', 'errors': 0, 'warnings': 0, 'log_path': '...demo.log'}}
```

Why it matters: Phase 3b makes MQL5 the canonical author format and the compiler/deployer are the hands that move user code into MT5. Returning success for a failed compile can cause an agent to deploy an older binary while believing it compiled the current source. That is the wrong code path for a trading tool, even if the repo itself ships no strategies.

Coverage gap: `tests/test_mql5_compiler.py:84` covers "errors in log and no `.ex5`", but there is no test for nonzero process exit with a pre-existing `.ex5`.

### P2 - `mt5 ea deploy` can leak a Python traceback and exit 1 instead of returning an envelope

`mt5_cli/mql5/deployer.py:75` through `mt5_cli/mql5/deployer.py:82` performs `mkdir()` and `shutil.copy2()` without catching filesystem failures. The CLI wrappers at `mt5/cli.py:1073` and `mt5/cli.py:1138` pass the deployer result to `emit()`, but an exception from the deployer prevents `emit()` from running at all. This violates the Phase 3a CLI envelope contract that every CLI invocation exits 0 and reports failure in the envelope.

Repro probe:

```text
temp workspace:
  ea/demo.mq5 exists
  MT5_TERMINAL_DATA_DIR=data
  data/MQL5/Experts is a file, not a directory

python -m mt5 --json ea deploy demo
EXIT=1
Traceback ... FileExistsError: [WinError 183] Cannot create a file when that file already exists: '...\\data\\MQL5\\Experts'
```

Why it matters: the review prompt explicitly called out deployer failure modes as fail-closed envelopes such as `DEPLOY_TARGET_NOT_WRITABLE`, not silent or uncaught filesystem errors. Agents need structured `ok=false` output here; they should not have to parse tracebacks or exit codes.

Coverage gap: `tests/test_mql5_deployer.py:51` and `tests/test_mql5_deployer.py:69` cover successful copies, and `tests/test_mql5_deployer.py:90` covers an unresolved data dir, but no test covers unwritable/malformed target directories or copy failures.

### P2 - deploy target resolution can copy to the wrong MT5 terminal

`mt5_cli/mql5/deployer.py:24` through `mt5_cli/mql5/deployer.py:54` resolves the terminal data directory by `MT5_TERMINAL_DATA_DIR` or by choosing the newest hash directory under the MetaQuotes Terminal root. `deploy_ea()` and `deploy_indicator()` at `mt5_cli/mql5/deployer.py:92` and `mt5_cli/mql5/deployer.py:97` do not accept a `data_path` parameter, and the module does not ask the bridge for the connected terminal's `terminal_info().data_path`.

Observed behavior from code trace: when multiple MT5 terminals or broker installs exist, the deployer picks "newest hash dir", not "the terminal this CLI session is controlling". A user can compile and deploy successfully, but the file can land in another terminal's `MQL5/Experts/` or `MQL5/Indicators/`.

Why it matters: Phase 3b acceptance is `mt5 ea compile demo && mt5 ea deploy demo` producing a copy in the terminal's Experts folder. The selected terminal must be the intended one. The review prompt allowed two safe shapes: use the bridge's `terminal_info().data_path`, or keep the module bridge-free by accepting a caller-provided `data_path`. This implementation does neither.

### P2 - scaffold names can escape the requested target directory

`mt5_cli/mql5/scaffold.py:39` creates the target directory, then `mt5_cli/mql5/scaffold.py:41` builds `dest = target_dir / f"{name}.mq5"` from the raw user-supplied name. The CLI passes that raw name from `mt5/cli.py:1030` and `mt5/cli.py:1095`. A name containing `..` or separators writes outside `./ea` or `./indicators` while still returning `ok=true`.

Repro probe:

```text
python -m mt5 --json ea new ../outside --target-dir <tmp>/ea
{"ok": true, "data": {"source": "<tmp>\\ea\\..\\outside.mq5", "template": "minimal"}}
outside=True
```

Why it matters: Phase 3b's user-workspace convention says scaffolding creates `./ea/<name>.mq5` or `./indicators/<name>.mq5`. Agents should not be able to write outside the requested user asset directory by passing a malformed MQL5 name. This is a file-safety issue, and it is easy to hit accidentally if an agent confuses a name with a path.

Coverage gap: `tests/test_mql5_scaffold.py:1` through `tests/test_mql5_scaffold.py:71` cover happy paths, overwrite refusal, and unknown templates, but not path traversal or invalid MQL5 asset names.

### P2 - the EA template is not the "stubs only, no inputs" skeleton requested for Phase 3b

`mt5_cli/mql5/templates/ea_minimal.mq5:7` ships an `input long MagicNumber = 88888;` parameter. The same file also includes strategy/entry-management wording at `mt5_cli/mql5/templates/ea_minimal.mq5:2` and `mt5_cli/mql5/templates/ea_minimal.mq5:11`.

Why it matters: review-context decision #10 and this checkpoint's priority list lock templates to minimal skeletons only: `OnInit` / `OnDeinit` / `OnTick` for EAs, no inputs, no strategy logic, no opinionated parameters. `MagicNumber` is useful in real EAs, but it is still a shipped input parameter in the tool's template. The user should author any parameters in their own workspace copy.

### P3 - README command list still describes the Phase 3a CLI shape

`README.md:35` says `mt5 --help` lists "all 11 command groups", and the command table at `README.md:90` through `README.md:101` omits the new `ea` and `indicator` groups. `python -m mt5 --help` now lists 13 groups, including both new Phase 3b groups.

Why it matters: this is not a runtime blocker, but it is artifact drift in a changed README and will mislead users checking whether Phase 3b CLI wiring landed.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
414 passed in 2.22s
```

```text
git diff --check 4f586aa..HEAD
```

Output: exit `0`, no output.

```text
python -m pytest tests/test_bridge_singleton.py -q
```

Output:

```text
15 passed in 0.07s
```

```text
python -m pytest tests/test_cli_ea.py tests/test_mql5_compiler.py tests/test_mql5_deployer.py tests/test_mql5_discovery.py tests/test_mql5_scaffold.py -q
```

Output:

```text
47 passed in 0.19s
```

```text
python -m pytest tests/test_cli.py tests/test_cli_ea.py tests/test_chart.py tests/test_chart_attach_ea.py tests/test_chart_indicators_attach.py tests/test_chart_menu.py tests/test_chart_new_chart.py tests/test_orders.py tests/test_risk.py -q
```

Output:

```text
259 passed in 1.81s
```

```text
git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5
```

Output:

```text
mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
mt5_cli/mql5/__init__.py:7:Bridge isolation: this package MUST NOT import MetaTrader5. All MT5
```

The second line is the expected docstring false positive; the AST guard above passes and ignores it.

```text
python -m mt5 --json ea new alpha --template scalper --target-dir <temp>
```

Output:

```text
{"ok": false, "error": {"code": "UNKNOWN_TEMPLATE", "message": "Template 'scalper' is not available. Valid choices: ['minimal']. The tool ships only minimal skeletons; strategy logic is yours to author."}}
```

```text
python -c "from importlib.resources import files; print(files('mt5_cli.mql5.templates').joinpath('ea_minimal.mq5').read_text(encoding='utf-8')[:80])"
```

Output:

```text
//+------------------------------------------------------------------+
//| {{nam
```

```text
python -m mt5 --help
```

Output includes `ea` and `indicator` alongside the Phase 3a groups.

Additional targeted probes:

- `compile_source()` with stale `.ex5`, no parsed log errors, and `subprocess.CompletedProcess(..., returncode=1)` returned `ok=true`.
- `python -m mt5 --json ea deploy demo` with `MQL5/Experts` as a file exited `1` with a `FileExistsError` traceback.
- `python -m mt5 --json ea new ../outside --target-dir <tmp>/ea` returned `ok=true` and created `<tmp>/outside.mq5`.

## Open Questions / Assumptions

- I treated `mt5_cli/mql5/__init__.py`'s `MetaTrader5` docstring mention as intentional and non-blocking because `tests/test_bridge_singleton.py` is AST-based and passes.
- The prompt included both the exact `UNKNOWN_TEMPLATE` envelope and the phrase "should fail with `MT5_INVALID_PARAMS`" for `--template scalper`. I treated the shown library envelope as acceptable because the new commands are supposed to return library envelopes; I did not make that contradiction a finding.
- I did not run a real MetaEditor or MT5 terminal deploy. The compiler/deployer issues above were reproduced with hermetic filesystem/subprocess probes.
