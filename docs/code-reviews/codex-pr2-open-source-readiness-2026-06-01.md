# Code Review: PR #2 Open Source Readiness

Reviewer: Codex
Branch: prep/open-source-blockers
Base: master
Date: 2026-06-01

## Scope

Reviewed the 11 per-phase commits in `master..prep/open-source-blockers`, with priority on:

- `8e6f60b` positions live-trade triple-lock and CLI envelope contract
- `36bbd10` MCP server surface
- `23f5ce4` de-internalization AST safety
- `06d1354` PEP 621 packaging and dependency pruning
- `0d02206` error registry and `mt5 describe`
- `a67e4ea` `config.save()` hardening and envelope tests

## Findings

### Blocker

None.

### High

1. `mt5/cli.py:184` - Ctrl+C is converted by Click into `click.Abort`, then caught by the broad `except Exception` handler and reported as `MT5_INTERNAL_ERROR` with exit 0.

   Why it matters: the handler does not catch raw `SystemExit` or raw `KeyboardInterrupt`, but Click's `Command.main(..., standalone_mode=False)` converts `KeyboardInterrupt`/EOF into `click.Abort`, and `click.Abort` inherits from `RuntimeError -> Exception`. I verified this with `CliRunner`: a command callback raising `KeyboardInterrupt` produced `{"ok": false, "error": {"code": "MT5_INTERNAL_ERROR", ... "type": "Abort"}}` and exit code 0. In a real-money CLI, an operator interrupt should not be mislabeled as an internal library failure or silently normalized by the broad handler.

   Concrete fix: add an explicit `except click.Abort: raise` before `except Exception`, or handle it with a dedicated abort envelope/code if the project intentionally wants interrupts to preserve the envelope contract. Add a regression test for `KeyboardInterrupt`/`click.Abort` behavior. Raw `SystemExit` already propagates; I verified a callback raising `SystemExit(7)` exits 7 with no envelope.

### Medium

1. `mt5/cli.py:307` - `mt5 describe` omits Click secondary flag spellings.

   Why it matters: `_describe_param()` records only `p.opts`, so dual boolean flags expose only the positive spelling. The machine catalog currently reports `config show` as having `flags: ["--mask-secrets"]` but omits `--no-mask-secrets`; it also omits `--no-open-panel`, `--no-close-panel`, and `--no-visual`. Agents using `mt5 describe --json` as the source of truth cannot discover the disable forms for default-on controls.

   Concrete fix: include `p.secondary_opts` in the exported flag list, for example `info["flags"] = list(p.opts) + list(p.secondary_opts)`, and add a test asserting the catalog includes `--no-mask-secrets` and one screenshot/tester negative flag.

### Low

1. `tests/test_errors.py:17` - the error-code drift test excludes the shipped `mt5_mcp` package.

   Why it matters: after `36bbd10`, `mt5_mcp` is part of the wheel and emits envelope errors through `fail(...)`, but `_codes_used_in_fail_calls()` only scans `mt5_cli` and `mt5`. The current MCP codes are already registered, so this is not a runtime mismatch today, but a future MCP-only error code could ship undocumented while the drift test still passes.

   Concrete fix: import `mt5_mcp` in the test and add `Path(mt5_mcp.__file__).parent` to the scanned roots. Keep the exact-set assertion.

### Nit

None.

## Verified Good

- Positions live-gate: `mt5_cli.positions.positions._live_gate_check()` bypasses non-REAL accounts before checking gates, and REAL accounts require `is_live_intent`, `cfg["live"]`, and `MT5_LIVE == "1"`. The CLI passes `ctx.obj["cfg"]` to `close`, `close_all`, `move_sl`, and `breakeven`; `close_all -> close` and `breakeven -> move_sl` thread the same `cfg`.
- MCP server: registered tools are read plus `order_dryrun` only. No live mutation tools are in `TOOLS`; `order_dryrun` passes `is_live_intent=False`; `mcp` is imported lazily inside `build_server()`.
- De-internalization: docstring-stripped AST comparison across the 20 changed Python files in `23f5ce4` found only the expected non-docstring deltas in `mt5_cli/chart/attach_ea.py` and `mt5_cli/chart/indicators_attach.py`.
- Packaging: wheel contents include `mt5/`, `mt5_cli/`, `mt5_mcp/`, `mt5` and `mt5-mcp` console scripts, MQL5 templates, and `USER_WORKSPACE.md`. Removed dependencies `pandas`, `pandas-ta`, `prompt-toolkit`, and `python-dateutil` have no remaining imports.
- `config.save()` strips `password` by default and preserves it only with `include_password=True`.

## Empirical Verification

- `python -m pytest -m "not integration" -q`: `563 passed, 2 deselected in 3.77s`
- `python -m ruff check .`: `All checks passed!`
- `python -m pip wheel . --no-deps -w .\_whl`: built `metatrader5_cli-0.4.0-py3-none-any.whl` successfully

## Verdict

request-changes
