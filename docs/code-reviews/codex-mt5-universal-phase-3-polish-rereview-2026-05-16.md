# Codex Re-review - Phase 3 Polish Boundary

Review target: `mt5-universal` at `81dc04b` (`81dc04b562e6099fd3cbc3bcc470c741c0e1748a`)
Compared against: `35fc0f9` (`35fc0f9b68ab90ce4361595abb6a289b2a6ed0df`), the Phase 3 polish NO-GO review

Decision: **GO**. The remaining P1 equality-boundary finding is closed.

## Findings

No findings.

## Verified Closure

- **Equal-mtime stale `.ex5` boundary:** closed. `mt5_cli/mql5/compiler.py:125` through `mt5_cli/mql5/compiler.py:128` now requires `.ex5` mtime to be strictly greater than source mtime, and `mt5_cli/mql5/compiler.py:134` reports `.ex5 is stale (mtime <= source)`. The replayed probe with `src_mtime == ex5_mtime`, `returncode=1`, and `0 errors, 0 warnings` now returns `ok=false` with `MQL5_COMPILE_FAILED`.
- **Regression test coverage:** present. `tests/test_mql5_compiler.py:131` covers the exact equality boundary, and the happy-path test at `tests/test_mql5_compiler.py:57` through `tests/test_mql5_compiler.py:68` explicitly bumps `.ex5` mtime forward so it exercises the strict freshness gate correctly.
- **Warnings-only compile behavior:** still correct. A probe with `returncode=1`, `0 errors, 1 warnings`, and a fresh `.ex5` returns `ok=true` with `warnings=1`.
- **Template semver polish:** still correct. Both minimal templates use `#property version "0.1.0"`.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
433 passed in 2.24s
```

```text
python -m pytest tests/test_mql5_compiler.py -q
```

Output:

```text
13 passed in 0.04s
```

```text
git diff --check 35fc0f9..HEAD
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

The second line is the expected docstring false positive; this re-review commit did not add any real MQL5-side `MetaTrader5` import.

Targeted equal-mtime stale probe:

```text
src_mtime 1778975612.1077874
ex5_mtime 1778975612.1077874
{'ok': False, 'error': {'code': 'MQL5_COMPILE_FAILED', 'message': '0 errors, 0 warnings, .ex5 is stale (mtime <= source) (metaeditor exit=1)', 'data': {'log': '0 errors, 0 warnings\r\n', 'exit_code': 1, 'stderr': 'fatal'}}}
```

Targeted warnings-only fresh `.ex5` probe:

```text
{'ok': True, 'data': {'source': '...warn.mq5', 'ex5': '...warn.ex5', 'errors': 0, 'warnings': 1, 'log_path': '...warn.log', 'exit_code': 1}}
```

## Open Questions / Assumptions

- Scope was limited to the one-character strict freshness fix at `81dc04b` plus the two polish behaviors from the dispatch.
- I did not run a real MetaEditor compile; the compiler behavior was verified with hermetic subprocess and filesystem probes matching the prior review.
