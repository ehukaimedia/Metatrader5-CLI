# Codex Review: mt5-universal Phase 2 complete

Review target: `mt5-universal` at `8c95b46`
Compared against: `140fabb` (Phase 2.3 checkpoint)

Required reading completed first:
- `docs/specs/2026-05-15-mt5-universal-review-context.md`
- `docs/specs/2026-05-15-mt5-universal-agent-native-design.md`

## Findings

1. **P1 [Critical]** - Phase 2.8 chart-indicator primitives call MT5 SDK functions that are not exposed by the installed Python package

   `mt5_cli/chart/indicators_attach.py:94`, `mt5_cli/chart/indicators_attach.py:103`, `mt5_cli/bridge/mt5_backend.py:123` - `attach()` dispatches `mt5_call("iCustom", ...)` and `mt5_call("ChartIndicatorAdd", ...)`, while `detach()` / `list_attached()` use the same pattern for `ChartIndicatorDelete`, `ChartIndicatorsTotal`, and `ChartIndicatorName`. The bridge's `mt5_call()` does a raw `getattr(mt5, fn_name)`, so any missing SDK attribute raises `AttributeError` before an envelope can be returned. On this environment's installed `MetaTrader5 5.0.5260`, all five attributes are absent:

   ```text
   {'iCustom': False, 'ChartIndicatorAdd': False, 'ChartIndicatorDelete': False, 'ChartIndicatorsTotal': False, 'ChartIndicatorName': False}
   5.0.5260
   ```

   Why it matters: Phase 2 acceptance explicitly includes `from mt5_cli.chart import ... attach, detach, list_attached`, and the chosen "hands, not strategies" design depends on attaching user-authored MQL5 indicators rather than computing indicator math in Python. The current implementation imports and unit-tests against mocks, but the real SDK surface cannot execute these hands.

2. **P1 [Critical]** - Pending order risk validation checks stop distance from the current ask, not the pending trigger price

   `mt5_cli/orders/orders.py:473`, `mt5_cli/orders/orders.py:497`, `mt5_cli/orders/orders.py:781`, `mt5_cli/orders/orders.py:803`, `mt5_cli/risk/risk.py:335`, `mt5_cli/risk/risk.py:337` - `place_limit()` and `place_stop()` pass the order through `check_order()` before building the pending request with the caller's `price`. Inside `check_order()`, Guard 5b always computes `sl_distance_points` from `tick.ask`, not from the pending order's requested trigger price. A far-away pending order can therefore pass the min-SL-distance gate even when its SL is too close to its eventual execution price.

   Why it matters: the preserved risk contract says library callers cannot bypass `mt5_cli/risk/` for order calls. For pending orders, using the live ask as the entry proxy creates a gate bypass in the exact place the Phase 2.3.H deferred ordering primitives were meant to extend.

3. **P1 [Critical]** - Direct order placement enforces only the explicit intent flag, not the preserved live-trading triple lock

   `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:268`, `mt5_cli/risk/risk.py:283`, `mt5_cli/risk/risk.py:289`, `mt5_cli/orders/orders.py:389`, `mt5_cli/orders/orders.py:421` - the spec preserves the legacy live-trading requirement as three gates: `cfg["live"]: true` + `MT5_LIVE=1` + `--live` CLI flag. `place_market()` reaches `order_send()` after `check_order()`, but `check_order()` only checks the account mode and `is_live_intent`; it does not require `cfg["live"]` and does not inspect `MT5_LIVE`. Because the library is a first-class surface for CLI, MCP, and direct import, a direct caller can submit a live-account order with only `is_live_intent=True` even when config/env are not armed.

   Why it matters: this is not a request for a different architecture; it is the existing spec's non-negotiable safety rule. The `positions.close()` exception was treated as out-of-scope per the review prompt, but new order placement still needs the preserved triple lock.

4. **P2 [Important]** - Config fallback handles syntactically invalid JSON, but valid non-object JSON crashes `load()`

   `mt5_cli/config/config.py:75`, `mt5_cli/config/config.py:76` - corrupt JSON is caught through `ValueError`, but `json.loads()` can successfully return a scalar or list. `dict.update()` then raises `TypeError` for values such as `42`, and that exception is not caught. Observed command:

   ```text
   Traceback (most recent call last):
     File "<string>", line 1, in <module>
       from mt5_cli.config import load; print(load()['max_positions'])
                                              ~~~~^^
     File "C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\mt5_cli\config\config.py", line 75, in load
       cfg.update(json.loads(path.read_text()))
       ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   TypeError: 'int' object is not iterable
   ```

   Why it matters: Phase 2.4 and Phase 2.12 explicitly call out corrupt-JSON fallback so agents do not crash on a bad config edit. A config file containing valid JSON of the wrong shape is the same operator-facing failure mode.

5. **P2 [Important]** - Post-sweep artifacts still advertise rejected broker abstractions and old user-data paths

   `docs/playgrounds/mt5-universal-refactor-playground.html:277`, `docs/playgrounds/mt5-universal-refactor-playground.html:279`, `docs/playgrounds/mt5-universal-refactor-playground.html:295`, `docs/playgrounds/mt5-universal-refactor-playground.html:296`, `docs/playgrounds/mt5-universal-refactor-playground.html:578`, `docs/playgrounds/mt5-universal-refactor-playground.html:579`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:1501`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:4210` - the playground still renders `broker.base` / `broker.generic_mt5` and tells agents to discover user EAs/indicators under `~/.config/mt5-universal/...`. The plan still has an implementation snippet pointing `_search_paths()` at `.config/mt5-universal`, and the Phase 6 resolver snippet sets `APP_NAME = "mt5-universal"`.

   Why it matters: review-context section 2 and the current spec lock single-broker Trading.com scope, no `BrokerProfile` ABC, no `generic_mt5`, package name `mt5_cli`, config file `~/.config/metatrader5-cli.json`, and user-authored data under `~/.local/share/metatrader5-cli/` / XDG data. The code tree grep is clean, but the artifacts that future agents are told to work from still point at the old architecture and old data location.

6. **P2 [Important]** - Phase 3 scaffolding artifacts still use strategy-flavored templates

   `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:239`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:1828`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:1870` - the spec's Phase 3 acceptance still uses `mt5 ea new demo --template scalper`, and the plan still wires `--template` choices such as `scalper | swing` and `overlay | oscillator`.

   Why it matters: the locked "hands, not strategies" decision rejects strategy-connoting EAs/indicators and says templates are minimal MQL5 skeletons only. If Phase 3 follows these artifacts, it will reintroduce the strategy flavor the Phase 2 cleanup removed.

7. **P2 [Important]** - `dom(symbol=...)` can return the requested symbol while opening/capturing whatever chart is active

   `mt5_cli/screenshot/screenshot.py:292`, `mt5_cli/screenshot/screenshot.py:316`, `mt5_cli/screenshot/screenshot.py:401`, `mt5_cli/screenshot/screenshot.py:412`, `mt5_cli/screenshot/screenshot.py:418`, `mt5_cli/screenshot/screenshot.py:420` - `_open_dom_panel()` posts the Depth of Market menu command to the MT5 window and returns `symbol_name.upper()`, but it never activates or verifies a chart for that symbol first. `dom()` then captures `target_window`, which defaults to the top-level `"MT5"` match. If the active chart is EURUSD and the caller requests `dom("USDJPY")`, the function can open/capture the active chart's DOM or full terminal while reporting `symbol: "USDJPY"`.

   Why it matters: Phase 2.7 adds screenshot primitives so agents can inspect the user's MT5 state. Returning a mislabeled visual capture is worse than failing closed because downstream agent reasoning can treat the wrong market state as evidence.

8. **P3 [Minor]** - Dynamic import guard misses common `importlib` alias forms

   `tests/test_bridge_singleton.py:75`, `tests/test_bridge_singleton.py:86`, `tests/test_bridge_singleton.py:101` - the regex backstop catches `importlib.import_module("MetaTrader5")` and `__import__("MetaTrader5")`, but it does not catch `from importlib import import_module; import_module("MetaTrader5")` or `import importlib as il; il.import_module("MetaTrader5")`. Observed helper result:

   ```text
   [True, False, False]
   ```

   Why it matters: the bridge singleton is a locked design convention. The AST import scan is solid for static imports, but the dynamic backstop still has bypasses a future contributor could use without failing `tests/test_bridge_singleton.py`.

## Validation

- `python -m pytest -q` -> `216 passed in 0.75s`
- `git diff --check 140fabb..HEAD` -> exit 0, no output
- `git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli` ->

  ```text
  mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
  ```

- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
- `$env:MT5_CONFIG='/nonexistent.json'; python -c "from mt5_cli.config import load, retcode_help; cfg = load(); print(cfg['filling'], cfg.get('rollover_utc_hour'), '/', retcode_help(10030)[:30])"` ->

  ```text
  FOK 22 / Wrong filling mode. Trading.co
  ```

- `python -c "import MetaTrader5 as mt5; names=['iCustom','ChartIndicatorAdd','ChartIndicatorDelete','ChartIndicatorsTotal','ChartIndicatorName']; print({n: hasattr(mt5, n) for n in names}); print(getattr(mt5, '__version__', 'no-version'))"` ->

  ```text
  {'iCustom': False, 'ChartIndicatorAdd': False, 'ChartIndicatorDelete': False, 'ChartIndicatorsTotal': False, 'ChartIndicatorName': False}
  5.0.5260
  ```

- Valid non-object config smoke:

  ```text
  Traceback (most recent call last):
    File "<string>", line 1, in <module>
      from mt5_cli.config import load; print(load()['max_positions'])
                                             ~~~~^^
    File "C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\mt5_cli\config\config.py", line 75, in load
      cfg.update(json.loads(path.read_text()))
      ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  TypeError: 'int' object is not iterable
  ```

- Dynamic import regex sample ->

  ```text
  [True, False, False]
  ```

## Open Questions / Assumptions

- I treated the single-broker Trading.com scope, no `BrokerProfile` ABC, no `generic_mt5`, no Python indicator math, no strategy templates, no example workspaces, and XDG data/config split as locked decisions per the required specs and prompt.
- I did not flag `positions.close()` using only the live gate because the review prompt explicitly marks that behavior as by design.
- I treated Phase 3+ implementation deliverables as future work, but flagged committed spec/plan/playground drift where those artifacts still direct future agents toward rejected Phase 3 shapes.
- I did not propose patches inline; this file is an audit only.
