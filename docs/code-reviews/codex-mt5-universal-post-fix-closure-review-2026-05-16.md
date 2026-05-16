# Codex Review: mt5-universal post-fix closure pass

Review target: `mt5-universal` at `9caf433`
Compared against: `7b9a560` (chart.new_chart + shared menu helper checkpoint)

Required reading completed first:
- `docs/code-reviews/codex-mt5-universal-post-fix-review-2026-05-16.md`
- `docs/specs/2026-05-15-mt5-universal-review-context.md`
- `docs/specs/2026-05-15-mt5-universal-agent-native-design.md`

## Findings

1. **P2 [Important]** - Phase 2.3.H plan still documents the pre-fix mutation API without `cfg`

   `docs/plans/2026-05-15-mt5-universal-agent-native.md:436`, `docs/plans/2026-05-15-mt5-universal-agent-native.md:437` - the live plan's deferred-ordering table still lists `modify(ticket, *, sl=None, tp=None, price=None, expiry=None, is_live_intent)` and `cancel_all_pending(symbol=None, *, is_live_intent)`, and the latter still says to call `cancel(ticket)` per-ticket. Current code correctly requires `cfg` for both APIs and threads `cfg` into each recursive `cancel()` call.

   Observed behavior: the implementation at `mt5_cli/orders/orders.py:866` and `mt5_cli/orders/orders.py:973` is safe, but the architecture plan still teaches the exact shape that caused the previous P1: mutation paths with no way to enforce `cfg["live"]` as part of the REAL-account triple lock.

   Why it matters: `docs/playgrounds/` and `docs/plans/` are part of this repo's spec-driven workflow. A future agent following Task 2.3.H from the plan could reintroduce the single-gate mutation surface that `62c7081` just closed, fighting the locked live-trading safety contract instead of the design itself.

## Verified Closures

- Previous P1 triple-lock finding: closed for `cancel()`, `modify()`, and `cancel_all_pending()`. `_live_gate_check()` now requires `cfg`, enforces `is_live_intent`, `cfg["live"]`, and `MT5_LIVE=1` on REAL accounts, and `cancel_all_pending()` threads `cfg` into each per-ticket `cancel()`.
- Previous P2 menu-normalization finding: closed. `normalize_menu_text("&New Chart\tCtrl+N")` now returns `new chart`.
- Previous P2 `new_chart()` fail-closed finding: closed for before-snapshot failure, after-verify failure, and no-new-hwnd detection. The active-chart fallback is gone.
- Previous P2 docs findings on `--template scalper` / `overlay`, Phase 6 `mt5-universal` app-dir tests, and playground "default BrokerProfile": closed at the cited locations.

## Validation

- `python -m pytest -q` ->

  ```text
  278 passed in 1.20s
  ```

- `git diff --check 7b9a560..HEAD` -> exit 0, no output

- `git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli` ->

  ```text
  mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
  ```

- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` ->

  ```text
  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:90:- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  docs/code-reviews/codex-mt5-universal-post-fix-review-2026-05-16.md:78:- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` ->
  docs/code-reviews/codex-mt5-universal-post-fix-review-2026-05-16.md:81:  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:90:- `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  ```

  Supplemental active-tree check excluding prior review artifacts: `git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'` -> exit 1, no output.

- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` ->

  ```text
  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:91:- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  docs/code-reviews/codex-mt5-universal-post-fix-review-2026-05-16.md:84:- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` ->
  docs/code-reviews/codex-mt5-universal-post-fix-review-2026-05-16.md:87:  docs/code-reviews/codex-mt5-universal-phase-2-complete-review-2026-05-16.md:91:- `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude'` -> exit 1, no output (zero matches)
  ```

  Supplemental active-tree check excluding prior review artifacts: `git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'` -> exit 1, no output.

- `$env:MT5_CONFIG='/nonexistent.json'; python -c "from mt5_cli.config import load, retcode_help; cfg = load(); print(cfg['filling'], cfg.get('rollover_utc_hour'), '/', retcode_help(10030)[:30])"` ->

  ```text
  FOK 22 / Wrong filling mode. Trading.co
  ```

- `python -c "from mt5_cli.chart import switch_tf, symbol, ensure_chart, find_window, current_title, attach, new_chart; from mt5_cli.screenshot import take, dom, annotate; print('chart+screenshot imports OK')"` ->

  ```text
  chart+screenshot imports OK
  ```

- `python -c "from mt5_cli.chart._menu import normalize_menu_text; print(normalize_menu_text('&New Chart\tCtrl+N')); print(normalize_menu_text('MyEMA\tAlt+1'))"` ->

  ```text
  new chart
  myema
  ```

- Optional SDK gap probe:

  ```text
  {'iCustom': False, 'ChartIndicatorAdd': False, 'ChartIndicatorDelete': False, 'ChartIndicatorsTotal': False, 'ChartIndicatorName': False}
  5.0.5260
  ```

- Subagent spot checks:

  ```text
  tests/test_orders.py -q -> 58 passed
  tests/test_chart_menu.py tests/test_chart_new_chart.py -q -> 29 passed
  ```

## Open Questions / Assumptions

- I treated the intentional breaking API change for direct library callers as accepted: out-of-repo scripts calling `cancel()`, `modify()`, or `cancel_all_pending()` must now pass `cfg`.
- `positions.close()` remains out-of-scope per the prior review prompt and preserved live-gate design.
- The chart/menu validation is mocked Win32 behavior only; I did not run a live MT5 GUI timing test.
- The remaining `mt5-universal` strings found in specs/plans are branch, document, tag, or filename references rather than package/config-path drift.
