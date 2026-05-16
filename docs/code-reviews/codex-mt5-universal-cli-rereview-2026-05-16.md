# Codex Re-review - Phase 3a CLI Fixes

Review target: `mt5-universal` at `3269f7b` (`3269f7be3677ec9817f7bff410684fd27a6755e8`)
Compared against: `384bd17` (prior Codex CLI review checkpoint)

Decision: **NO-GO**. The two P1 findings are closed, but one P2 from the prior review remains partially open.

## Findings

### P2 - `attach_ea(chart_id=...)` still posts the EA menu command for a stale/non-child hwnd

`attach_ea()` now checks the boolean result of `activate_chart()` before it posts the Expert Advisor menu command, which closes the narrow case where `activate_chart()` explicitly returns `False`. It still does not prove that the requested `chart_id` is an enumerated MDI child before trusting the activation attempt.

Citations:

- `mt5_cli/chart/attach_ea.py:109` gates explicit `chart_id` only on `activate_chart(...)`.
- `mt5_cli/chart/attach_ea.py:158` posts the `WM_COMMAND` EA attach after that boolean gate.
- `mt5_cli/chart/chart.py:403` sends `WM_MDIACTIVATE` to the MDI client.
- `mt5_cli/chart/chart.py:407` returns `True` after `SendMessage` succeeds, without verifying that `hwnd` exists under the MT5 window or became active.
- `tests/test_chart_attach_ea.py:260` covers the monkeypatched `activate_chart() -> False` path, but not the stale-hwnd case where Win32 accepts `WM_MDIACTIVATE` and the requested chart is not actually an MT5 child.

Observed behavior:

I replayed the prior wrong-chart scenario with fake Win32 modules: main MT5 window found, MDIClient found, `chart_id=9999` not enumerated as a child, `SendMessage(WM_MDIACTIVATE, 9999)` returns normally. The function still reports success and posts the EA attach command to the main window:

```text
{'ok': True, 'data': {'expert_name': 'MyEA', 'command_id': 8001, 'chart_id': 9999, 'parent_hwnd': 1000, 'menu_path': 'Insert > Experts > MyEA', 'auto_confirmed': True}}
mdi_activate_calls= [(7777, 546, 9999, 0)]
wm_command_calls= [(1000, 273, 8001, 0)]
```

Why it matters:

The chart-control design uses GUI menu pokes as MT5 "hands"; the menu action applies to whichever chart is active. The explicit `chart_id` argument exists to prevent an EA from landing on the wrong chart. If a stale or wrong-parent hwnd can still pass through as success, the CLI can mutate the wrong chart while returning an OK envelope, which violates the fail-closed contract for agent-native chart control.

Expected behavior:

When `chart_id` is supplied, the function should fail closed with `CHART_ID_NOT_FOUND` or equivalent before posting `WM_COMMAND` unless the requested hwnd is verified as an MT5 chart child for the matched parent window.

## Verified Closures

- **P1 #1 `order poll-fill` timeout kwarg:** closed. `mt5/cli.py:574` keeps CLI `--timeout` in seconds and calls `poll_fill(ticket, timeout_ms=int(timeout * 1000))` at `mt5/cli.py:587`. Targeted CLI probe returned `{"ok": true, "data": {"filled": false, "ticket": 12345}}` with exit `0`; `tests/test_cli.py:349` also asserts the `timeout_ms` threading.
- **P1 #2 Click parser errors bypass envelope:** closed. `EnvelopeGroup` at `mt5/cli.py:106` catches `click.UsageError`, emits `MT5_INVALID_PARAMS` via `emit()`, and exits `0`. I verified both invalid `Choice` and bad integer cases return JSON fail envelopes with exit `0`; coverage is at `tests/test_cli.py:313`, `tests/test_cli.py:328`, and `tests/test_cli.py:339`.
- **P2 #4 `ensure_chart()` timeframe lie after `new_chart()` partial success:** closed. `mt5_cli/chart/chart.py:846` now propagates the actual `new_chart()` data, including `timeframe=None` and `tf_switch_warning`; coverage is at `tests/test_chart.py:341`.
- **P2 #5 `close_chart()` success on post-close verification exception:** closed. `mt5_cli/chart/chart.py:1072` now returns `CHART_CLOSE_VERIFY_FAILED` when the after-enumeration raises; coverage is at `tests/test_chart.py:746`.
- **P2 #6 `connect` overrides ignored when already connected:** closed. `mt5/cli.py:187` now calls `_bridge_reconnect_once(cfg)` when overrides are supplied and the bridge is already connected; coverage is at `tests/test_cli.py:506`, `tests/test_cli.py:566`, and `tests/test_cli.py:583`.
- **P2 #7 invalid history dates connect before validation:** closed. `history orders`, `deals`, and `stats` parse dates before `_autoconnect` at `mt5/cli.py:696`, `mt5/cli.py:722`, and `mt5/cli.py:746`; coverage is at `tests/test_cli.py:421`, `tests/test_cli.py:453`, and `tests/test_cli.py:477`.
- **P3 #8 mutating CLI safety coverage:** non-blocking coverage was added for limit/stop/dryrun and position move/breakeven live threading at `tests/test_cli.py:608`, `tests/test_cli.py:622`, `tests/test_cli.py:636`, `tests/test_cli.py:649`, and `tests/test_cli.py:662`.
- **P3 #9 `emit.py` payload edges:** non-blocking coverage was added for `ok(None)`, list-of-dicts, nested dicts, datetimes, bytes, and scalars at `tests/test_cli.py:680` through `tests/test_cli.py:740`.
- **P3 #10 `config show --no-mask-secrets` login exposure test:** non-blocking coverage was added at `tests/test_cli.py:748`.
- **P3 #11 `cycle_chart` no-active/wrap coverage:** non-blocking coverage exists at `tests/test_chart.py:542`, `tests/test_chart.py:580`, and `tests/test_chart.py:616`.

## Validation

Commands run:

```text
python -m pytest -q
```

Output:

```text
366 passed in 2.07s
```

```text
git diff --check 384bd17..HEAD
```

Output: exit `0`, no output.

```text
git grep -n -e "import MetaTrader5" -e "from MetaTrader5" -- mt5_cli mt5
```

Output:

```text
mt5_cli/bridge/mt5_backend.py:10:import MetaTrader5 as mt5
```

```text
git grep -n "mt5_universal" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
git grep -ni "cli-anything\|cli_anything" -- ':!archive' ':!.git' ':!.claude' ':!docs/code-reviews/*'
```

Output: both exit `1`, no output. The broader grep that includes prior review artifacts still finds historical mentions inside old review files only.

```text
Get-Command mt5 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
```

Output:

```text
C:\Users\arsen\AppData\Roaming\Python\Python313\Scripts\mt5.exe
```

```text
mt5 --help
```

Output begins:

```text
Usage: mt5 [OPTIONS] COMMAND [ARGS]...
Commands:
  account
  chart
  config
  connect
  history
  market
  order
  position
  rates
  screenshot
  status
```

```text
$env:MT5_CONFIG='/nonexistent.json'; mt5 --json config show; Remove-Item Env:MT5_CONFIG
```

Output:

```text
{"ok": true, "data": {"server": "Trading.comMarkets-MT5", "login": null, "password": null, "live": false, "magic": 88888, "deviation": 20, "max_positions": 5, "max_daily_loss": 2000.0, "max_lot_per_order": 2.5, "min_sl_distance_points": 50, "max_spread_points": 80, "min_free_margin_pct": 20, "max_orders_per_minute": 10, "symbol_allowlist": [], "allow_hedging": false, "strategy_ids": {}, "filling": "FOK", "rollover_utc_hour": 22}}
```

```text
$env:MT5_CONFIG='/nonexistent.json'; mt5 --json config retcode 10030; Remove-Item Env:MT5_CONFIG
```

Output:

```text
{"ok": true, "data": {"retcode": 10030, "help": "Wrong filling mode. Trading.com is FOK-only; pin filling=FOK in your config."}}
```

Targeted probes:

- `python -m mt5 --json order poll-fill 12345 --timeout 0.01` -> `{"ok": true, "data": {"filled": false, "ticket": 12345}}`, exit `0`.
- `python -m mt5 --json order market EURUSD junk --volume 0.01 --sl 1.09` -> `MT5_INVALID_PARAMS`, exit `0`.
- `python -m mt5 --json order cancel not-an-int` -> `MT5_INVALID_PARAMS`, exit `0`.
- Inline `CliRunner` probe for invalid history dates confirmed `MT5_INVALID_PARAMS` with `_bridge_connect` call count `0`.
- Inline `CliRunner` probe for `connect --login/--password/--server` while already connected confirmed `_bridge_reconnect_once(cfg)` was called and `_bridge_connect` was not.
- Inline chart probe confirmed `ensure_chart()` preserves `timeframe=None` and `tf_switch_warning` from `new_chart()`.
- Inline chart probe confirmed `close_chart()` returns `CHART_CLOSE_VERIFY_FAILED` when post-close enumeration raises.
- Inline chart probe confirmed `attach_ea()` fails closed when `activate_chart()` is monkeypatched to return `False`.
- Inline chart probe above shows the remaining stale/non-child `chart_id` bypass.

## Open Questions / Assumptions

- I treated the prior review's P3s as optional. The added coverage looks reasonable and does not affect the GO/NO-GO decision.
- I did not run `mt5 --json status` in this re-review to avoid opening a bridge session against any live terminal/account. The reviewed fixes are covered by unit tests and targeted isolated probes.
- I treated prior code-review artifacts as archival, so historical `mt5_universal` and `cli-anything` strings inside `docs/code-reviews/` are not live-tree naming drift.
