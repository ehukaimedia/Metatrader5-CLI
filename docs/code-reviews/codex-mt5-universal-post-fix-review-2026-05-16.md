# Codex Review: mt5-universal post-fix pass

Review target: `mt5-universal` at `7b9a560`
Compared against: `8c95b46` (Phase 2 complete + naming sweep)

Required reading completed first:
- `docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md`
- `docs/specs/2026-05-15-mt5-universal-review-context.md`
- `docs/specs/2026-05-15-mt5-universal-agent-native-design.md`

## Findings

1. **P1 [Critical]** - Live triple-lock fix is incomplete for order mutation paths

   `mt5_cli/orders/orders.py:183`, `mt5_cli/orders/orders.py:195`, `mt5_cli/orders/orders.py:680`, `mt5_cli/orders/orders.py:694`, `mt5_cli/orders/orders.py:863`, `mt5_cli/orders/orders.py:881`, `mt5_cli/orders/orders.py:910`, `mt5_cli/orders/orders.py:952` - P1 #3 is fixed for placement paths that call `risk.check_order()`, but `orders._live_gate_check()` still checks only `is_live_intent` on REAL accounts. `cancel()` uses that helper before sending `TRADE_ACTION_REMOVE`, `modify()` uses it before sending either position `TRADE_ACTION_SLTP` or pending-order `TRADE_ACTION_MODIFY`, and `cancel_all_pending()` uses it before cascading into `cancel()`. These functions do not accept `cfg`, so they cannot enforce `cfg["live"]`, and they never check `MT5_LIVE=1`.

   Observed behavior: a direct library caller can still mutate live pending orders or SL/TP with `is_live_intent=True` while config live is false and `MT5_LIVE` is unset. Tests cover `is_live_intent=False` for `cancel()` / `modify()`, but not the full triple-lock matrix for these mutation paths.

   Why it matters: the preserved spec says live trading requires all three gates, and the library is a first-class surface for CLI, MCP, and direct imports. `positions.close()` remains out-of-scope per the prompt, but these `orders` mutation paths still send live trade requests through the bridge.

2. **P2 [Important]** - Shared menu normalization fails on Win32 shortcut suffixes

   `mt5_cli/chart/_menu.py:22`, `mt5_cli/chart/_menu.py:26`, `mt5_cli/chart/_menu.py:49`, `mt5_cli/chart/_menu.py:62`, `mt5_cli/chart/new_chart.py:87`, `mt5_cli/chart/new_chart.py:94`, `mt5_cli/chart/indicators_attach.py:113`, `mt5_cli/chart/indicators_attach.py:125` - `normalize_menu_text()` says it drops the keyboard-shortcut suffix after a tab, but it calls `.split()` before `.split("\t", 1)`, so tabs are converted to spaces first. A real menu label such as `&New Chart\tCtrl+N` normalizes to `new chart ctrl+n`, not `new chart`, and exact-match walks then fail to find `File > New Chart`. The same helper is used by indicator attach leaf matching, so shortcut-decorated leaves have the same failure mode.

   Observed probe:

   ```text
   new chart ctrl+n
   myema alt+1
   ```

   The current tests miss this because the fake menu labels use `&New Chart` and `MyEMA` without tab suffixes.

   Why it matters: `new_chart()` and `attach()` are GUI hands. If the real MT5 menu exposes shortcut suffixes, agents get false `CHART_MENU_PATH_NOT_FOUND` / `CHART_INDICATOR_NOT_FOUND` failures even though the menu item is present.

3. **P2 [Important]** - `new_chart()` can report success without proving a new chart was opened

   `mt5_cli/chart/new_chart.py:103`, `mt5_cli/chart/new_chart.py:106`, `mt5_cli/chart/new_chart.py:120`, `mt5_cli/chart/new_chart.py:125`, `mt5_cli/chart/new_chart.py:132`, `mt5_cli/chart/new_chart.py:134`, `mt5_cli/chart/new_chart.py:137`, `mt5_cli/chart/new_chart.py:141`, `mt5_cli/chart/new_chart.py:151`, `mt5_cli/chart/new_chart.py:155` - the function snapshots existing chart hwnds, posts the menu command, then diffs the after snapshot. If the before snapshot throws, it is silently replaced with `set()`. If no new hwnd is found, the code falls back to whichever chart is active and then returns an `ok` envelope with the requested symbol. With `timeframe` supplied, it can also call `switch_tf(..., chart_id=new_chart_hwnd)` against that existing/unknown chart.

   Observed behavior from code trace: if `PostMessage` does not open a chart, MT5 focuses an existing chart, or the before snapshot failed, `new_chart()` can return success for the requested symbol even though no new chart was identified. Tests cover the happy hwnd-diff path, but not unchanged-after, before-snapshot exception, or no-hwnd branches.

   Why it matters: the primitive is meant to give agents reliable chart-control hands. Returning `ok` with a requested symbol that was not actually opened repeats the same label-vs-reality class of bug fixed for `dom()`.

4. **P2 [Important]** - Phase 3 plan smoke tests still require strategy-flavored templates

   `docs/plans/2026-05-15-mt5-universal-agent-native.md:2057`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:2077`, `docs/specs/2026-05-15-mt5-universal-agent-native-design.md:239` - the spec acceptance now says `mt5 ea new demo` uses only the minimal MQL5 skeleton, but the Phase 3 CLI smoke-test plan still invokes `mt5 ea new ... --template scalper` and `mt5 indicator new ... --template overlay`.

   Why it matters: this is the same P2 #6 drift in a later plan section. A future agent following the plan either has to reintroduce rejected strategy-flavored templates or ship tests that fail.

5. **P2 [Important]** - Phase 6 path tests still assert the old `mt5-universal` app directory

   `docs/plans/2026-05-15-mt5-universal-agent-native.md:4271`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:4278`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:4303` - the Phase 6 implementation snippet sets `APP_NAME = "metatrader5-cli"`, but the immediately preceding tests still expect cache paths under `mt5-universal`.

   Why it matters: the locked path split says config is `~/.config/metatrader5-cli.json` and user data/cache dirs use the `metatrader5-cli` app name. These TDD instructions would either pull implementation back to the old app name or leave Phase 6 red.

6. **P2 [Important]** - Playground still describes Trading.com as the current default `BrokerProfile`

   `docs/playgrounds/mt5-universal-refactor-playground.html:575` - Phase 2 playground capability text says Trading.com is now the "default BrokerProfile", while the current spec says single-broker only, no current `BrokerProfile` ABC, and no `generic_mt5.py`.

   Why it matters: the playground is explicitly part of the architecture workflow. This wording can steer future agents back toward the rejected abstraction, even though the surrounding plan/spec text now mostly reflects the single-broker scope.

## Validation

- `python -m pytest -q` ->

  ```text
  253 passed in 1.17s
  ```

- `git diff --check 8c95b46..HEAD` -> exit 0, no output

- `git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli` ->

  ```text
  mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
  ```

- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` ->

  ```text
  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:90:- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  ```

- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` ->

  ```text
  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:91:- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  ```

  I treated those two grep hits as prior-review validation text, not active architecture guidance.

- `$env:MT5_CONFIG='/nonexistent.json'; python -c "from mt5_cli.config import load, retcode_help; cfg = load(); print(cfg['filling'], cfg.get('rollover_utc_hour'), '/', retcode_help(10030)[:30])"` ->

  ```text
  FOK 22 / Wrong filling mode. Trading.co
  ```

- `python -c "from mt5_cli.chart import switch_tf, symbol, ensure_chart, find_window, current_title, attach, new_chart; from mt5_cli.screenshot import take, dom, annotate; print('chart+screenshot imports OK')"` ->

  ```text
  chart+screenshot imports OK
  ```

- Optional SDK gap probe:

  ```text
  {'iCustom': False, 'ChartIndicatorAdd': False, 'ChartIndicatorDelete': False, 'ChartIndicatorsTotal': False, 'ChartIndicatorName': False}
  5.0.5260
  ```

- Valid non-object config smoke:

  ```text
  5
  ```

- Menu normalization probe:

  ```text
  new chart ctrl+n
  myema alt+1
  ```

## Open Questions / Assumptions

- Verified closed: P1 #1 no longer calls SDK indicator functions; `attach()` is Win32-only and the bridge grep is clean.
- Verified closed for placement and dry-run paths: P1 #2 now passes `entry_price` for `place_limit()`, `place_stop()`, and pending `dryrun()`.
- Partially closed: P1 #3 is fixed for `check_order()` placement paths but not for `orders.cancel()`, `orders.modify()`, or `orders.cancel_all_pending()`.
- Verified closed: P2 #4 valid non-object JSON no longer crashes `load()`.
- Partially closed: P2 #5 / #6 docs sweeps removed the original main locations, but later plan/playground sections still contain the drift listed above.
- Verified closed: P2 #7 `dom()` activates the requested symbol's chart before opening the DOM panel.
- Verified closed: P3 #8 dynamic-import regex catches alias and bare `import_module("MetaTrader5")` forms.
- I treated deferred "Adding a new broker" guidance as out-of-scope when it is explicitly scoped to a future second-broker event.
- I did not propose patches inline; this is an audit only.
