# Codex Review - Phase 3 Polish

Review target: `mt5-universal` at `580ea3b` (`580ea3bb8fc91e9477772845860fc28946cefb89`)
Compared against: `e52f527` (Phase 3b GO re-review checkpoint)

Decision: **NO-GO**. The warnings-only compile path and template semver changes work, but the stale `.ex5` guard still has a boundary hole.

## Findings

### P1 - Stale `.ex5` with equal source mtime still returns `ok=true`

The dispatch defined the new failure condition as: errors > 0, `.ex5` missing, or `.ex5` stale where stale means `mtime <= source mtime`. The implementation accepts equal mtimes as fresh: `mt5_cli/mql5/compiler.py:120` through `mt5_cli/mql5/compiler.py:123` sets `ex5_fresh` when `ex5.stat().st_mtime >= src.stat().st_mtime`, and `mt5_cli/mql5/compiler.py:124` only fails when that is false. The error text at `mt5_cli/mql5/compiler.py:129` also documents only `mtime < source`. The new regression test at `tests/test_mql5_compiler.py:125` sets the `.ex5` mtime to `src_mtime - 60`, so it does not cover the equality boundary.

Repro probe:

```text
src_mtime 1778975268.6429453
ex5_mtime 1778975268.6429453
{'ok': True, 'data': {'source': '...demo.mq5', 'ex5': '...demo.ex5', 'errors': 0, 'warnings': 0, 'log_path': '...demo.log', 'exit_code': 1}}
```

Probe setup:

- `demo.mq5` exists.
- `demo.ex5` exists from a prior run and is forced to the exact same mtime as the source.
- log says `0 errors, 0 warnings`.
- `subprocess.run()` returns `CompletedProcess(..., returncode=1, stderr="fatal")`.

Why it matters: this is the same safety class as the original P1. A nonzero MetaEditor run with no fresh proof of output can still be reported as a successful compile, so an agent can deploy an old binary while believing the current compile succeeded. The warning nuance is real, but the replacement freshness gate needs to fail closed on the equality boundary the task explicitly called stale.

## Verified Closures

- **Warnings-only successful compile:** verified. With `returncode=1`, log containing `0 errors, 1 warnings`, and `.ex5` mtime after the source, `compile_source()` returns `ok=true` with `warnings=1` and `exit_code=1`.
- **Template semver version strings:** verified. `mt5_cli/mql5/templates/ea_minimal.mq5:5` and `mt5_cli/mql5/templates/indicator_minimal.mq5:5` both use `#property version "0.1.0"`.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
432 passed in 2.25s
```

```text
python -m pytest tests/test_mql5_compiler.py tests/test_mql5_scaffold.py -q
```

Output:

```text
26 passed in 0.06s
```

```text
git diff --check e52f527..HEAD
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

The second line is the expected docstring false positive; this polish did not add any real MQL5-side bridge import.

Targeted probes:

- Equal-mtime stale probe above returned `ok=true`, which is the blocking finding.
- Warnings-only fresh `.ex5` probe returned `ok=true` with `warnings=1`.
- Template file inspection confirmed both minimal templates use `0.1.0`.

## Open Questions / Assumptions

- I scoped this review to the single polish commit and the two behaviors requested in the dispatch.
- I did not run a real MetaEditor compile. The behavior was verified with hermetic subprocess/filesystem probes matching the earlier compiler review probes.
