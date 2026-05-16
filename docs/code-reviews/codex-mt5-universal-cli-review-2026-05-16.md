# Codex Review: mt5-universal Phase 3a CLI + chart-control bundle

Review target: `mt5-universal` at `69cfc1a`
Compared against: `9caf433` (post-fix P2 closure)
Decision: **NO-GO** until the P1 envelope-contract regressions are fixed.

Required reading completed first:
- `shared/codex-cli-review-prompt-2026-05-16.md`
- `docs/code-reviews/codex-mt5-universal-post-fix-closure-review-2026-05-16.md`
- `docs/specs/2026-05-15-mt5-universal-review-context.md`
- `docs/specs/2026-05-15-mt5-universal-agent-native-design.md`

## Findings

1. **P1 [Critical]** - `mt5 order poll-fill` crashes instead of returning an envelope

   `mt5/cli.py:502`, `mt5/cli.py:504`, `mt5/cli.py:512`, `mt5_cli/orders/orders.py:747` - the CLI defines `--timeout` as a float seconds-like option, but calls `orders.poll_fill(ticket, timeout=timeout)`. The library signature is `poll_fill(ticket, timeout_ms=5000)`, so the command raises `TypeError` before `emit()` runs.

   Observed behavior:

   ```text
   python -m mt5 --json order poll-fill 12345 --timeout 1
   ...
   TypeError: poll_fill() got an unexpected keyword argument 'timeout'. Did you mean 'timeout_ms'?
   EXIT=1
   ```

   Why it matters: Phase 3a's CLI contract says commands always exit 0 and report success/failure in the standard envelope. This command is a shipped order command that currently cannot be used through the CLI at all, and the exception bypasses the agent-parseable failure channel.

2. **P1 [Critical]** - Click parser errors bypass the JSON envelope and nonzero-exit contract

   `mt5/emit.py:8`, `mt5/cli.py:342`, `mt5/cli.py:344`, `tests/test_cli.py:313` - invalid CLI invocations are still handled by Click's default parser path. For example, `order market` uses a Click `Choice` for side, and the test suite currently asserts `result.exit_code != 0` for an invalid side instead of expecting a fail envelope.

   Observed behavior:

   ```text
   python -m mt5 --json order market EURUSD junk --volume 0.01 --sl 1.09
   Usage: python -m mt5 order market [OPTIONS] SYMBOL {buy|sell}
   Try 'python -m mt5 order market --help' for help.

   Error: Invalid value for '{buy|sell}': 'junk' is not one of 'buy', 'sell'.
   EXIT=2
   ```

   Why it matters: the locked CLI surface is explicitly agent-native: scripts parse envelopes and do not infer semantics from process exit status or Click usage text. Invalid params are exactly where agents need structured `MT5_INVALID_PARAMS`-style output, not an unparseable stderr usage block.

3. **P2 [Important]** - `attach_ea(chart_id=...)` ignores activation failure and can attach to the wrong chart

   `mt5_cli/chart/attach_ea.py:109`, `mt5_cli/chart/attach_ea.py:147`, `mt5_cli/chart/attach_ea.py:167`, `tests/test_chart_attach_ea.py:237` - when a caller supplies `chart_id`, `attach_ea()` calls `activate_chart(...)` but ignores its boolean result. It then posts the Expert Advisor menu command to the terminal and returns success. If the `chart_id` is stale, wrong-parent, or cannot be activated, MT5 may attach the EA to whichever chart is already active.

   Observed targeted probe:

   ```text
   activate_chart -> False
   attach_ea("MyEA", chart_id=9999, settle_seconds=0)
   {'ok': True, 'data': {'expert_name': 'MyEA', 'command_id': 8001, 'chart_id': 9999, ...}}
   ```

   Why it matters: this is a routing error on an EA attachment primitive. EAs can trade, and an agent passing an explicit chart id is doing so to avoid exactly this wrong-chart behavior. The chart-control bundle's "hands" need to fail closed when the named hand target cannot be selected.

4. **P2 [Important]** - `ensure_chart()` reports the requested timeframe even when `new_chart()` failed to switch timeframe

   `mt5_cli/chart/new_chart.py:178`, `mt5_cli/chart/new_chart.py:181`, `mt5_cli/chart/chart.py:844`, `mt5_cli/chart/chart.py:848`, `tests/test_chart.py:307` - `new_chart()` deliberately returns partial success with `tf_switch_warning` when the chart opens but timeframe switching fails. `ensure_chart()` treats any `ok` from `new_chart()` as fully verified and returns `timeframe=normalized_timeframe`, dropping the warning entirely.

   Observed targeted probe:

   ```text
   new_chart(...) -> ok({"timeframe": None, "tf_switch_warning": {"code": "CHART_TIMEFRAME_VERIFY_FAILED"}})
   ensure_chart("USDJPY", timeframe="H1") -> ok({"timeframe": "H1", "opened_new": True, ...})
   ```

   Why it matters: `ensure_chart()` is the prepare/verify primitive agents will call before screenshots, indicators, or EAs. Returning `ok=True` with the requested timeframe when the chart is actually on another timeframe recreates the label-vs-reality problem the chart layer has been steadily closing.

5. **P2 [Important]** - `close_chart()` treats post-close verification failure as success

   `mt5_cli/chart/chart.py:1061`, `mt5_cli/chart/chart.py:1063`, `mt5_cli/chart/chart.py:1074`, `tests/test_chart.py:581` - after posting `WM_CLOSE`, `close_chart()` catches any exception from the verification enumeration and substitutes `after_charts = []`. That makes `chart_id not in after_hwnds` true and returns `closed=True` even though verification could not run.

   Observed targeted probe:

   ```text
   before enumerate -> [chart 2000]
   post WM_CLOSE
   after enumerate -> RuntimeError("post-close enum failed")
   close_chart(2000) -> {'ok': True, 'data': {'closed': True, ...}}
   ```

   Why it matters: the function's contract is "WM_CLOSE on chart child + verify-gone". If verification fails, the caller needs a fail envelope so it can screenshot/check for dialogs instead of assuming a chart was closed.

6. **P2 [Important]** - `connect --login/--password/--server` can report a reconnect that did not happen

   `mt5/cli.py:66`, `mt5/cli.py:69`, `mt5/cli.py:127`, `mt5/cli.py:134`, `mt5/cli.py:138` - the `connect` command merges override options into `cfg`, then calls `_autoconnect(cfg)`. `_autoconnect()` immediately returns when `_bridge_is_connected()` is true, so an already-connected process ignores the provided overrides but still emits `{"connected": true, "server": "<requested server>"}`.

   Observed targeted probe:

   ```text
   _bridge_is_connected -> True
   mt5 --json connect --server NewServer --login 123 --password secret
   {"ok": true, "data": {"connected": true, "server": "NewServer"}}
   connect_calls []
   ```

   Why it matters: the command is documented as "Explicitly (re)connect" and its options say they override config. A user or agent can believe it has switched account/server while the bridge remains connected to the previous session.

7. **P2 [Important]** - Invalid history dates attempt MT5 connection before local validation

   `mt5/cli.py:620`, `mt5/cli.py:624`, `mt5/cli.py:626`, `mt5/cli.py:644`, `mt5/cli.py:648`, `mt5/cli.py:650`, `mt5/cli.py:668`, `mt5/cli.py:672`, `mt5/cli.py:674`, `tests/test_cli.py:366` - `history orders`, `history deals`, and `history stats` call `_autoconnect()` before parsing/rejecting `--from` / `--to`. With MT5 unavailable, a malformed date can return `MT5_CONNECTION_ERROR` instead of the local `MT5_INVALID_PARAMS` envelope.

   Observed targeted probe:

   ```text
   _bridge_is_connected -> False
   _bridge_connect -> RuntimeError("connect attempted")
   mt5 --json history orders --from garbage
   {"ok": false, "error": {"code": "MT5_CONNECTION_ERROR", "message": "Could not connect to MT5: connect attempted"}}
   calls 1
   ```

   Why it matters: argument validation should be side-effect-free. This also weakens the test boundary: the current test passes because the fixture marks the bridge initialized, masking the unwanted connection attempt.

8. **P3 [Minor]** - Several mutating CLI safety paths are not covered by `--live` / `cfg` assertions

   `tests/test_cli.py:238`, `tests/test_cli.py:250`, `tests/test_cli.py:262`, `tests/test_cli.py:336` - implementation currently threads `cfg` and `is_live_intent` correctly for order `limit`, `stop`, `dryrun`, and position `close-all`, `move-sl`, and `breakeven`; however the CLI tests only assert price/type/symbol for several of those paths, and there are no CLI plumbing tests for `move-sl` or `breakeven`.

   Why it matters: this is the live-trading safety boundary the prior P1 cycle just hardened. A future regression could drop `cfg` or `is_live_intent` on one of these mutators and leave the smoke suite green.

9. **P3 [Minor]** - `emit()` edge cases are mostly untested

   `mt5/emit.py:27`, `mt5/emit.py:34`, `mt5/emit.py:55`, `tests/test_cli.py:169`, `tests/test_cli.py:179` - the formatter handles `ok(None)`, list-of-dicts separators, nested dicts, bytes, datetimes, and scalar payloads, but the current CLI tests cover only a flat dict success and one fail output.

   Observed probe:

   ```text
   ok(None) -> OK
   ok([{"a": 1}, {"b": {"nested": 2}}]) -> prints "---" separator
   ok({"blob": b"abc"}) -> blob: b'abc'
   ok({"dt": datetime(...)}) -> dt: 2026-01-01 00:00:00+00:00
   ```

   Why it matters: `emit()` is the last agent-facing formatting boundary. Direct tests would keep future cleanup from changing parseability or human summaries by accident.

10. **P3 [Minor]** - `config show --no-mask-secrets` test does not assert login exposure

   `tests/test_cli.py:98`, `tests/test_cli.py:105`, `mt5/cli.py:912`, `mt5_cli/config/config.py:101` - the default masking test asserts both password and login are redacted, but the no-mask test only asserts password. The implementation currently exposes both correctly with `--no-mask-secrets`, but the sensitive login behavior is not locked by the test.

   Why it matters: login is explicitly treated as sensitive in `mask_secrets()`. Tests should cover both sides of that boundary: masked by default, intentionally exposed only through `--no-mask-secrets`.

11. **P3 [Minor]** - `cycle_chart()` no-active/wrap-around boundaries are under-specified in tests

   `mt5_cli/chart/chart.py:972`, `mt5_cli/chart/chart.py:977`, `mt5_cli/chart/chart.py:993`, `tests/test_chart.py:438` - the implementation defaults `active_index` to 0 when no chart is marked active and then reports `cycled_from=charts[0].hwnd`. Wrap-around is modulo-based, but tests only check that a next-cycle result differs from `cycled_from`; they do not cover last-to-first, first-to-last, or no-active behavior.

   Why it matters: this is not a blocker, but callers/logs can misread `cycled_from` as an observed active chart when it is actually a fallback. The test suite should define whether that fallback label is intentional.

## Verified Closures / Good Paths

- Previous closure-review P2 is closed at `5ae1722`: the Phase 2.3.H plan now documents `cfg` on `modify()` and `cancel_all_pending()`.
- Triple-lock plumbing is correct in the CLI implementation for order mutators: `market`, `limit`, `stop`, `dryrun`, `cancel`, `modify`, and `cancel-all` pass `cfg=ctx.obj["cfg"]` and `is_live_intent` from `--live`.
- Position mutators match the current library contract: `close`, `close-all`, `move-sl`, and `breakeven` pass `is_live_intent` from `--live` and do not pass `cfg`.
- SDK-dependent account/market/rates/order/position/history commands call `_autoconnect()`; chart, screenshot, config, and retcode commands skip it as intended.
- `config show` masks both `login` and `password` by default, and `--no-mask-secrets` exposes both when dummy env values are supplied.
- `setup.py` registers only `mt5 = mt5.cli:main`; no `mt5-mcp` entry point is registered ahead of Phase 5.
- Bridge singleton grep remains clean: only `mt5_cli/bridge/mt5_backend.py` imports `MetaTrader5`.
- `attach_ea()` uses the recursive menu walk, and the CLI `--no-confirm` flag correctly inverts to `auto_confirm=False`.

## Validation

- `python -m pytest -q` ->

  ```text
  337 passed in 1.93s
  ```

- `git diff --check 9caf433..HEAD` -> exit 0, no output

- `git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5` ->

  ```text
  mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
  ```

- `mt5 --help` ->

  ```text
  Usage: mt5 [OPTIONS] COMMAND [ARGS]...

    mt5 - agent-native control of the MetaTrader 5 terminal.

  Options:
    --json  Emit JSON envelopes (for agents / scripts).
    --help  Show this message and exit.

  Commands:
    account     Account info / balance / risk.
    chart       Chart UI control (Win32 + GUI menu pokes).
    config      Show effective config / look up MT5 retcodes.
    connect     Explicitly (re)connect to the MT5 terminal.
    history     Closed orders / deals / equity stats.
    market      Symbol info / ticks / DOM / search.
    order       Order placement / cancel / modify.
    position    Open position list / close / move SL / breakeven.
    rates       OHLCV / tick history fetch.
    screenshot  Capture / annotate / list screenshots.
    status      Show connection + account summary.
  ```

- `mt5 --json config show` ->

  ```text
  {"ok": true, "data": {"server": "Trading.comMarkets-MT5", "login": null, "password": null, "live": false, "magic": 88888, "deviation": 20, "max_positions": 5, "max_daily_loss": 2000.0, "max_lot_per_order": 2.5, "min_sl_distance_points": 50, "max_spread_points": 80, "min_free_margin_pct": 20, "max_orders_per_minute": 10, "symbol_allowlist": [], "allow_hedging": false, "strategy_ids": {}, "filling": "FOK", "rollover_utc_hour": 22}}
  ```

- `$env:MT5_LOGIN='12345'; $env:MT5_PASSWORD='secret123'; mt5 --json config show` ->

  ```text
  {"ok": true, "data": {"server": "Trading.comMarkets-MT5", "login": "***", "password": "***", "live": false, "magic": 88888, "deviation": 20, "max_positions": 5, "max_daily_loss": 2000.0, "max_lot_per_order": 2.5, "min_sl_distance_points": 50, "max_spread_points": 80, "min_free_margin_pct": 20, "max_orders_per_minute": 10, "symbol_allowlist": [], "allow_hedging": false, "strategy_ids": {}, "filling": "FOK", "rollover_utc_hour": 22}}
  ```

- `$env:MT5_LOGIN='12345'; $env:MT5_PASSWORD='secret123'; mt5 --json config show --no-mask-secrets` ->

  ```text
  {"ok": true, "data": {"server": "Trading.comMarkets-MT5", "login": 12345, "password": "secret123", "live": false, "magic": 88888, "deviation": 20, "max_positions": 5, "max_daily_loss": 2000.0, "max_lot_per_order": 2.5, "min_sl_distance_points": 50, "max_spread_points": 80, "min_free_margin_pct": 20, "max_orders_per_minute": 10, "symbol_allowlist": [], "allow_hedging": false, "strategy_ids": {}, "filling": "FOK", "rollover_utc_hour": 22}}
  ```

- `mt5 --json config retcode 10030` ->

  ```text
  {"ok": true, "data": {"retcode": 10030, "help": "Wrong filling mode. Trading.com is FOK-only; pin filling=FOK in your config."}}
  ```

- `mt5 --json status` -> exit 0; returned an `ok` demo-account envelope. Local account identifiers are intentionally redacted from this review artifact.

- `where.exe mt5` and `Get-Command mt5` ->

  ```text
  C:\Users\arsen\AppData\Roaming\Python\Python313\Scripts\mt5.exe
  Source      : C:\Users\arsen\AppData\Roaming\Python\Python313\Scripts\mt5.exe
  Definition  : C:\Users\arsen\AppData\Roaming\Python\Python313\Scripts\mt5.exe
  CommandType : Application
  ```

- `python -m mt5 --json order market EURUSD junk --volume 0.01 --sl 1.09; Write-Output "EXIT=$LASTEXITCODE"` ->

  ```text
  EXIT=2
  Usage: python -m mt5 order market [OPTIONS] SYMBOL {buy|sell}
  Try 'python -m mt5 order market --help' for help.

  Error: Invalid value for '{buy|sell}': 'junk' is not one of 'buy', 'sell'.
  ```

- `python -m mt5 --json order poll-fill 12345 --timeout 1; Write-Output "EXIT=$LASTEXITCODE"` ->

  ```text
  EXIT=1
  TypeError: poll_fill() got an unexpected keyword argument 'timeout'. Did you mean 'timeout_ms'?
  ```

- Targeted history invalid-date probe with `_bridge_connect` stubbed to raise ->

  ```text
  exit 0
  output {"ok": false, "error": {"code": "MT5_CONNECTION_ERROR", "message": "Could not connect to MT5: connect attempted"}}
  calls 1
  ```

- Targeted connect override probe with `_bridge_is_connected -> True` ->

  ```text
  exit 0
  output {"ok": true, "data": {"connected": true, "server": "NewServer"}}
  connect_calls []
  ```

- Targeted chart probes:

  ```text
  ensure_chart("USDJPY", timeframe="H1") with new_chart tf_switch_warning
  -> {'ok': True, 'data': {'timeframe': 'H1', 'opened_new': True, ...}}

  attach_ea("MyEA", chart_id=9999) with activate_chart -> False
  -> {'ok': True, 'data': {'chart_id': 9999, 'auto_confirmed': True, ...}}

  close_chart(2000) with post-close enumeration failure
  -> {'ok': True, 'data': {'closed': True, ...}}
  ```

- Subagent spot checks:

  ```text
  tests/test_cli.py -q -> 35 passed
  tests/test_cli.py tests/test_config.py -q -> 52 passed
  tests/test_chart.py tests/test_chart_attach_ea.py -q -> 44 passed
  ```

## Open Questions / Assumptions

- I treated Click `--help` output as allowed to remain Click-native; the P1 is about invalid command invocations under the promised JSON/envelope execution contract.
- I did not run live GUI actions for chart attach/close/cycle. Chart findings are from code trace plus mocked targeted probes.
- I did not re-litigate Phase 3b MQL5 plugin host scope; it remains TODO by design.
- I treated real local account fields from `mt5 --json status` as sensitive and redacted them from the committed review artifact.
