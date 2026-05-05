# MetaTrader 5 CLI — Feature Specification

**Version:** 0.5 (spec corrections + design decisions resolved)
**Date:** 2026-04-28
**Status:** Ready for implementation

---

## 1. Purpose

`mt5` is a command-line interface for MetaTrader 5 that exposes the platform's data and trading surfaces as composable shell commands and structured JSON output. It is designed to be the primitive layer that an AI agent (or a human operator) calls to perform autonomous top-down market analysis and order execution without touching the MT5 GUI.

---

## 2. Goals / Non-Goals

### Goals
- Fetch multi-timeframe OHLCV rate data from a connected MT5 terminal
- Compute technical indicators in Python and return them as JSON
- Capture screenshots of the MT5 window via OS-level screen capture
- Place, modify, and close market and pending orders on a **demo account by default**
- Inspect positions, account state, and trade history
- Provide a REPL for interactive exploration
- Be composable: every command supports `--json` for machine-readable output and pipes

### Non-Goals
- **Strategy logic** — entry/exit rules and backtesting live in a separate layer; this CLI exposes primitives only. Simple derived analytics (bias summaries, confluence scores from `analyze`) are in scope as convenient compositions of rate + indicator data — not strategy signals.
- **Economic calendar** — `MetaTrader5` Python package v5.0.5260 has no `calendar_events()` API (verified: `dir(mt5)` returns no calendar symbol). News blackout logic is the strategy layer's responsibility; use an operator-maintained `news_calendar.json` file. Not a v2 candidate unless a future MT5 package version exposes it.
- **Full chart GUI automation** — v1 includes focused Win32 chart primitives where they are reliable (symbol/timeframe switching and screenshots) and data-layer access to Depth of Market. Applying indicators to the chart window and native EA-driven chart operations remain deferred (see §10).
- **Multi-broker abstraction** — targets a single locally running MT5 terminal (Windows)
- **Live trading by default** — hard-blocked unless `--live` is explicitly set (see §7)
- **Web or remote execution** — Windows-only; the official `MetaTrader5` Python package requires a locally installed MT5 terminal

---

## 3. Architecture

```
┌─────────────────────────────────────────────┐
│                  CLI layer                  │
│  mt5_cli.py  (Click groups + REPL)          │
│  ReplSkin    (prompt-toolkit, unified UX)   │
└───────────────┬─────────────────────────────┘
                │ calls
┌───────────────▼─────────────────────────────┐
│                 Core layer                  │
│  core/account.py    core/market.py          │
│  core/rates.py      core/indicator.py       │
│  core/analyze.py    core/order.py           │
│  core/position.py   core/history.py         │
│  core/screenshot.py core/risk.py            │
│  core/project.py    (config + config IO)    │
└───────────────┬─────────────────────────────┘
                │ calls
┌───────────────▼─────────────────────────────┐
│               Bridge layer (v1)             │
│  utils/mt5_backend.py                       │
│    — wraps MetaTrader5 Python package        │
│    — wraps mss for OS screen capture         │
│    — wraps pandas-ta for indicator compute   │
└─────────────────────────────────────────────┘
                │ IPC (COM / named pipe)
┌───────────────▼─────────────────────────────┐
│         MetaTrader 5 Terminal (local)        │
│         Running on Windows                  │
└─────────────────────────────────────────────┘
```

### Layer responsibilities

| Layer | What it owns | What it never touches |
|-------|-------------|----------------------|
| CLI | Click groups, context passing, `--json` flag, REPL loop | Business logic, MT5 API |
| Core | Domain logic (pure functions: dict in → dict out) | Click, any UI |
| Bridge | MT5 package init/shutdown, mss captures, pandas-ta wrappers | Click, domain logic |

### Bridge layer contracts

**`symbol_select()` prerequisite** — Before any `copy_rates_*`, `symbol_info_tick()`, or `order_send()` call the bridge must call `mt5.symbol_select(symbol, True)`. Without it, symbols not already in the terminal's Market Watch return `None` silently. This call is idempotent for already-selected symbols.

**Connection lifecycle** — `mt5.initialize()` is called once per session (not per command). The bridge holds a singleton connection and registers `mt5.shutdown()` via `atexit`. In REPL mode the connection is kept open across all commands; re-initializing per command adds ~500 ms latency and exhausts terminal connection slots. If `mt5.last_error()` indicates a disconnection, the bridge auto-reconnects once before raising.

**Thread safety** — The MT5 Python package is not thread-safe. The bridge acquires a module-level `threading.Lock` around every `mt5.*` call. Multi-strategy orchestrators running strategies in parallel threads are safe; order calls from different threads are serialized at the bridge layer with no additional work required by callers.

**Position close mechanism** — MT5 has no dedicated `close_position()` function. All close operations (`position close`, `position close-all`, `position breakeven`, `position move-sl`) are implemented as `mt5.order_send()` with `action=TRADE_ACTION_DEAL`, the opposite direction type (SELL to close a BUY, BUY to close a SELL), and `position=<ticket>` binding to the specific open trade. The bridge reads the current position via `positions_get(ticket=ticket)` to extract symbol, volume, and type before constructing the request.

### Library Usage (Python API)

The `core/` layer is explicitly designed to be importable by strategy-layer consumers. Core modules are pure functions — no Click dependency, no REPL, no argv parsing. The same JSON envelope that the CLI's `--json` flag emits is returned as a Python dict.

```python
from metatrader5_cli.mt5.core import account, market, rates, order, position, history

# Every core call returns the same envelope the CLI's --json flag does:
acct = account.info()
# {"ok": True, "data": {"login": ..., "balance": ..., "leverage": ..., ...}}

tick_value = market.info("USDJPY")["data"]["trade_tick_value"]

# Orders go through the SAME risk envelope as CLI-invoked orders:
result = order.place_market(
    symbol="USDJPY",
    side="sell",
    volume=0.10,
    sl=156.420,
    tp=155.800,
    strategy_id="gopher-gate",
)
# result = {"ok": True, "data": {"ticket": ..., "retcode": 10009, ...}}
# or {"ok": False, "error": {"code": "RISK_MAX_POSITIONS", ...}}

pos = position.list(symbol="USDJPY")
bars = rates.fetch("USDJPY", "M5", bars=100)
```

**Guarantees for library callers:**
- `core/risk.py` runs for **every** order call — CLI or library. The risk envelope is not a CLI concern; it is a core concern. Library callers cannot bypass it by importing `core.order` directly — the risk check is the first thing every order function does.
- The bridge's singleton MT5 connection (`utils/mt5_backend.py`) is shared across all library callers in the same process. The `atexit` shutdown still fires.
- All `time` fields are ISO-8601 UTC strings. No raw Unix epoch integers leak through the library API.
- `symbol_select()` is called automatically by `market.*` and `rates.*` calls; callers never need to pre-select symbols.

**Known consumer patterns:**

| Consumer type | Purpose | Typical entry point |
|---|---|---|
| `mt5` CLI | Interactive and scripted shell invocation | `metatrader5_cli.mt5.mt5_cli:main` |
| Autonomous trading runtime | Strategy-layer daemon: orchestrator, session-level gates, position manager. Imports `metatrader5_cli.mt5.core.*` directly. CLI risk envelope is the per-order floor; the runtime adds stateful session-level gates (consecutive losses, equity floor, daily loss cap, news blackout) on top — **never relaxes the floor**. Any agentic team can build such a runtime against this library. | runtime-specific |
| Backtest harness | Replay historical bars through strategy code via `rates.range()` and `rates.ticks_range()` | runtime-specific |
| Multi-strategy orchestrator | Runs multiple `--strategy-id`-tagged strategies in one process; filters performance via `history.stats(strategy_id=...)` | runtime-specific |

**When to shell out to the CLI vs import the library:**
- **Import** for all in-process hot paths: analysis loop, position monitor, order placement, rate/tick fetches. Subprocess overhead (~500 ms per `mt5.initialize()`) is unacceptable for a 5-second monitor loop.
- **Subprocess** only for operator-facing stdout output where human-readable formatting matters (e.g. `@sonnet` shelling out to post a formatted `STATUS` message to the ehukai bus). In practice, even that should prefer the library + local formatting.

### Patterns cherry-picked from CLI-Anything

| Pattern | Source reference |
|---------|-----------------|
| `@click.group(invoke_without_command=True)` → REPL fallback | adguardhome_cli.py:120–143 |
| Three-tier config (flags > env > `~/.config/cli-anything-mt5.json`) | adguardhome/core/project.py |
| `output(data, as_json)` dual-mode output function | adguardhome_cli.py:36–49 |
| `ReplSkin` (prompt-toolkit, colors, banner, error/success) | adguardhome/utils/repl_skin.py |
| Core modules: pure functions, no Click imports | adguardhome/core/server.py |
| `setup.py` namespace packages + `console_scripts` entry point | adguardhome/setup.py |
| Stateful session pattern (snapshot/undo) | audacity/core/session.py |

---

## 4. Package Layout

```
Metatrader5-CLI/
├── setup.py
├── MT5.md                          # Agent-facing SOP
├── metatrader5_cli/
│   └── mt5/
│       ├── __main__.py
│       ├── mt5_cli.py              # Root CLI + REPL (~500 LOC)
│       ├── core/
│       │   ├── account.py          # Balance, equity, margin
│       │   ├── market.py           # Symbol info, tick, spread
│       │   ├── rates.py            # OHLCV fetch, multi-TF
│       │   ├── indicator.py        # pandas-ta wrapper
│       │   ├── analyze.py          # Multi-TF analysis pipeline
│       │   ├── order.py            # Place/modify/cancel orders
│       │   ├── position.py         # Open positions CRUD
│       │   ├── history.py          # Closed trades, deals
│       │   ├── screenshot.py       # mss OS screen capture
│       │   ├── risk.py             # Safety guardrails
│       │   └── project.py          # Config load/save
│       ├── utils/
│       │   ├── mt5_backend.py      # MetaTrader5 init/shutdown
│       │   ├── repl_skin.py        # Shared from CLI-Anything
│       │   └── __init__.py
│       ├── skills/
│       │   └── SKILL.md            # Agent-facing capability doc
│       └── tests/
│           ├── TEST.md
│           ├── test_core.py        # Unit (mocked MT5 package)
│           └── test_e2e.py         # Integration (live demo account)
└── docs/
    └── specs/
        └── mt5-cli-spec.md         # This file
```

---

## 5. Configuration

### Config file
`~/.config/cli-anything-mt5.json`

```json
{
  "login": 12345678,
  "password": "demo-password",
  "server": "Trading.com-Demo",
  "timeout": 10000,
  "live": false,
  "magic": 88888,
  "deviation": 20,
  "filling": "auto",
  "max_positions": 5,
  "max_daily_loss": 50.0,
  "max_lot_per_order": 1.0,
  "min_sl_distance_points": 50,
  "max_orders_per_minute": 10,
  "max_spread_points": 30,
  "symbol_allowlist": [],
  "min_free_margin_pct": 20,
  "screenshot_path": "~/mt5-screenshots",
  "screenshot_monitor": 0,
  "allow_hedging": false,
  "strategy_ids": {
    "gopher-gate": 12001,
    "fvg-sniper": 12002
  }
}
```

**Config key notes:**
- `magic` — integer tag applied to every agent-placed order; allows filtering agent orders from manually-placed trades in history queries. Default `88888`.
- `deviation` — max price slippage tolerance in points for market orders; 20 is a safe broker-agnostic default.
- `filling` — for market orders, `"auto"` reads `symbol_info().filling_mode` at order time and maps to `ORDER_FILLING_FOK/IOC/RETURN`; for pending limit/stop orders, `"auto"` uses `ORDER_FILLING_RETURN` because MT5 pending-order placement can reject broker market-order filling modes. Set explicitly only if broker requires a fixed mode.
- `max_daily_loss` — denominated in **account currency** (read from `account_info().currency`), not USD.
- `screenshot_monitor` — integer monitor index passed to `mss`. `0` = primary monitor. Set to `2` if MT5 is on a secondary display.
- `strategy_ids` — map of human-readable strategy name → magic integer. Entries here take priority over auto-derivation. Magic integers must be `< 100000` to avoid colliding with the auto-derived range `[100000, 180000)`.
- `allow_hedging` — `false` by default (Trading.com US enforces FIFO; no opposing positions on the same symbol). Set `true` only for non-US brokers that permit hedging.

### Resolution order (highest wins)
1. CLI flags (`--login`, `--server`, `--live`)
2. Environment variables for connection credentials: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`
3. Config file (`~/.config/cli-anything-mt5.json`)
4. Hardcoded defaults (live=false, max_positions=5, timeout=10000)

> **`MT5_LIVE` is not a config-resolution layer.** It is live-gate #3 (§7.1)
> and is checked directly by `_compose_live_intent` in the CLI layer, never
> merged into `cfg["live"]`.  Setting `MT5_LIVE=1` without `"live": true` in
> the config file does not enable live trading.

### Config commands
```
mt5 config show          # Print current effective config (mask password)
mt5 config save          # Write current flags to config file
mt5 config test          # Attempt MT5 connection and print result
```

---

## 6. Command Catalog

All commands emit either human-readable text (default) or JSON (`--json` flag).
Exit code 0 = success, 1 = user/input error, 2 = MT5 connection error.

### JSON envelope

Every `--json` response wraps in a standard envelope so agents can branch on success/failure without parsing exit codes alone:

**Success:**
```json
{"ok": true, "data": { ... }}
```

**Failure:**
```json
{"ok": false, "error": {"code": "RISK_MAX_POSITIONS", "message": "Max open positions (5) reached", "mt5_retcode": null}}
{"ok": false, "error": {"code": "MT5_ORDER_REJECTED", "message": "Order rejected by broker", "mt5_retcode": 10006}}
{"ok": false, "error": {"code": "MT5_CONNECTION_ERROR", "message": "Cannot connect to terminal", "mt5_retcode": null}}
```

Standard error codes: `MT5_CONNECTION_ERROR`, `MT5_ORDER_REJECTED`, `MT5_INVALID_SYMBOL`, `MT5_INVALID_VOLUME`, `RISK_MAX_POSITIONS`, `RISK_MAX_DAILY_LOSS`, `RISK_SYMBOL_NOT_ALLOWED`, `RISK_INSUFFICIENT_MARGIN`, `RISK_LIVE_GATE_BLOCKED`, `RISK_MAX_LOT_EXCEEDED`, `RISK_NO_STOP_LOSS`, `RISK_SPREAD_TOO_WIDE`, `RISK_RATE_LIMIT`, `RISK_HEDGE_BLOCKED`, `RISK_STRATEGY_ID_TOO_LONG`.

All `data` keys shown in the command tables below are nested inside `"data": { ... }` in the actual JSON output.

### 6.1 `mt5 account`

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `account info` | — | `login`, `name`, `server`, `currency`, `balance`, `equity`, `margin`, `free_margin`, `margin_level`, `leverage`, `profit`, `trade_mode` (`"demo"/"real"/"contest"`), `trade_allowed` | Full account snapshot |
| `account balance` | — | `balance`, `equity`, `currency` | Quick balance check |
| `account risk` | — | `max_positions`, `max_daily_loss`, `daily_loss_used`, `positions_used`, `safe_to_trade`, `currency` | Risk envelope status |

### 6.2 `mt5 market`

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `market info` | `SYMBOL` | `symbol`, `bid`, `ask`, `spread`, `digits`, `pip_size`, `trade_tick_value`, `volume_min`, `volume_step`, `volume_max`, `swap_long`, `swap_short`, `filling_mode`, `trade_mode` | Symbol spec. `pip_size` = one pip in price units (USDJPY: `0.01`, EURUSD: `0.0001`). `trade_tick_value` = account-currency value of one tick per 1.0 lot — use this for position sizing, not a hardcoded constant. `filling_mode` = raw broker bitmask (1=FOK, 2=IOC, 4=RETURN). |
| `market tick` | `SYMBOL` | `symbol`, `time`, `bid`, `ask`, `last`, `volume` | Latest tick |
| `market depth` | `SYMBOL --levels INT` | `symbol`, `captured_at`, `levels`, `raw_count`, `bids`, `asks`, `best_bid`, `best_ask`, `spread`, `spread_points`, `mid`, `bid_volume`, `ask_volume`, `volume_imbalance`, `raw` | One-shot Depth of Market snapshot using `market_book_add()` -> `market_book_get()` -> `market_book_release()`. Bids are sorted high-to-low, asks low-to-high. `--levels 0` returns all available levels; positive values limit each side. DOM is broker/symbol dependent and may return `MT5_MARKET_BOOK_SUBSCRIBE_FAILED` or `MT5_MARKET_BOOK_UNAVAILABLE`. |
| `market search` | `--pattern TEXT` | `[{symbol, description, currency_base, currency_profit}]` | Symbol search. `--pattern EUR` is auto-wrapped as `*EUR*` glob passed to `mt5.symbols_get(group=...)`. Users may supply explicit MT5 glob syntax (e.g. `EUR*,GBP*`). |
| `market sessions` | `SYMBOL` | `{tokyo: {start_utc, end_utc}, london: {start_utc, end_utc}, ny: {start_utc, end_utc}, sydney: {start_utc, end_utc}}` | Named FX session boundaries in UTC. Static lookup table keyed by symbol class (FX majors, metals, indices). Eliminates per-strategy hardcoded session times. |

### 6.3 `mt5 rates` — Timeframe Data Fetch

"Timeframe toggle" in v1 is data-layer: fetch OHLCV at any timeframe without touching the chart window.

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `rates fetch` | `SYMBOL TIMEFRAME` `--bars INT` | `symbol`, `timeframe`, `bars: [{time, open, high, low, close, tick_volume}]` | Fetch N bars |
| `rates latest` | `SYMBOL TIMEFRAME` | `{time, open, high, low, close, tick_volume, spread}` | Most recent **closed** bar. Uses `copy_rates_from_pos(..., start_pos=1, count=1)` — `start_pos=0` is the live forming bar and must not be used here. |
| `rates range` | `SYMBOL TIMEFRAME --from DATE --to DATE` | same bars array | Date-range fetch |
| `rates ticks` | `SYMBOL --bars INT` | `symbol`, `ticks: [{time, bid, ask, last, volume, flags}]` | Fetch last N ticks via `copy_ticks_from(symbol, date_from, count, flags)`. `date_from` is computed as `datetime.utcnow() - timedelta(hours=24)`; the bridge fetches up to 24 hours of ticks and slices to `--bars`. If fewer ticks exist in the window the full available set is returned. Required for tick-precision SL-hit reconstruction and microstructure analysis. |
| `rates ticks-range` | `SYMBOL --from DATE --to DATE` | same ticks array | Date-range tick fetch via `copy_ticks_range()` |

**Timeframe values:** `M1 M5 M15 M30 H1 H4 D1 W1 MN1`

**Tick flags:** raw MT5 `TICK_FLAG_*` bitmask surfaced as-is; bridge converts to ISO-8601 timestamps.

### 6.3.1 `mt5 chart` — GUI-facing chart aliases

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `chart switch-tf` | `TIMEFRAME` `--window TEXT` `--settle-seconds FLOAT` | `timeframe`, `title`, `hwnd` | Switch the active MT5 chart timeframe through the period toolbar and verify the title. |
| `chart current` | `--window TEXT` | `title`, `hwnd` | Read the currently matched MT5 chart window title. Use this before GUI workflows to confirm the active chart. |
| `chart symbol` | `SYMBOL` `--window TEXT` `--settle-seconds FLOAT` | `symbol`, `title`, `hwnd` | Switch the active MT5 chart symbol and verify the title. |
| `chart ensure` | `SYMBOL --timeframe TF --window TEXT --settle-seconds FLOAT` | `symbol`, `timeframe`, `title`, `hwnd` | Ensure the active MT5 chart is on the broker-exact SYMBOL and optional timeframe, then verify the title. Defaults to `M15`; use `--timeframe none` to only ensure the symbol. This is the preferred chart-selection primitive for agents. |
| `chart depth-of-market` / `chart dom` | `SYMBOL --window TEXT --settle-seconds FLOAT` | `symbol`, `menu`, `command_id`, `title`, `hwnd` | Open the actual MT5 Charts > Depth Of Market GUI panel for SYMBOL via the terminal menu. This is the visual/menu path; use `market depth` for structured Python API book data. |

### 6.4 `mt5 indicator` — Python-Computed Indicators

Indicators are computed from fetched rate data using `pandas-ta`. No chart-window interaction.

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `indicator ema` | `SYMBOL TIMEFRAME --period INT --bars INT` | `symbol`, `timeframe`, `period`, `values: [{time, ema}]` | EMA series |
| `indicator atr` | `SYMBOL TIMEFRAME --period INT --bars INT` | `values: [{time, atr}]` | ATR series |
| `indicator fvg` | `SYMBOL TIMEFRAME --bars INT --min-points FLOAT --state STATE` | `zones`, `values` | Fair Value Gap zones. Each zone includes exact `lower`, `upper`, `mid`, `state`, `size_points`, `size_pips`, `distance_points`, `distance_pips`, `visual_label`, `object_prefix`, and `visual_contract` fields so agents can pair CLI data with the vendored `EhukaiFVG.mq5` overlay. |
| `indicator list` | — | `[{name, description, params}]` | Available indicators |

### 6.4.1 `mt5 ehukai` — Visual-TDA Indicator Mirrors

These commands are the preferred structured data companions for screenshots
that use the vendored Ehukai MT5 overlays. They intentionally mirror
`EhukaiFVG.mq5`, `EhukaiMarketStructure.mq5`, and
`EhukaiLiquiditySwings.mq5` so visual agents do not choose
between duplicate generic interpretations.

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `ehukai fvg` | `SYMBOL TIMEFRAME --bars INT --min-gap-pips FLOAT --max-zones INT --max-distance-pips FLOAT` | `source`, `object_prefix`, `zones`, `visual_contract` | Visible open/partial FVG zones matching `EhukaiFVG.mq5` defaults: `EFVG_` prefix, pips-based labels, max four zones, distance filter, exact lower/upper/mid levels. |
| `ehukai structure` | `SYMBOL TIMEFRAME --bars INT --pivot-bars INT --max-swings INT` | `source`, `bias`, `panel_label`, `support`, `resistance`, `visible_swings`, `visual_contract` | Bias, support/resistance, and swing labels matching `EhukaiMarketStructure.mq5`: adaptive pivot bars, `EMS_` prefix, `HH/HL/LH/LL`, BOS labels, and the `MS <TF>: ...` panel text. |
| `ehukai liquidity` | `SYMBOL TIMEFRAME --bars INT --length INT --area wick\|full-range --filter-by count\|volume --filter-value FLOAT --max-pools INT` | `source`, `object_prefix`, `pools`, `open_pools`, `swept_pools`, `nearest_buy_side`, `nearest_sell_side`, `visual_contract` | Buy-side/sell-side liquidity pools matching `EhukaiLiquiditySwings.mq5`: `ELS_` prefix, `BSL/SSL LIQ OPEN/SWEPT C<count> V<volume>` labels, exact zone top/bottom/level, interaction count, tick volume, and sweep status. Use as a target/trap map rather than a standalone entry signal. |

### 6.5 `mt5 analyze` — Top-Down Market Structure Analysis

The high-value workflow: fetch rates across multiple TFs, read swing structure, and return a structured JSON summary suitable for AI decision-making. This workflow does not use technical indicators.

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `analyze topdown` | `SYMBOL` `--timeframes TF[,TF...]` `--bars INT` | See schema below | Multi-TF market-structure summary. `--timeframes` accepts comma-separated TFs in one value (`--timeframes D1,H4,H1`) or repeated flags (`--timeframes D1 --timeframes H4`). Space-separated in a single flag is not supported by Click. |
| `analyze structure` | `SYMBOL TIMEFRAME --bars INT` `--pivot-n INT` | `support`, `resistance`, `swing_highs`, `swing_lows`, `swing_points`, `visual_contract` | Key S/R levels via N-bar pivot detection. A bar at index `i` is a swing high if its `high` is the highest of the `N` bars before and after it; swing low symmetrically. Default `--pivot-n 5`. `support` = highest swing low below current price; `resistance` = lowest swing high above current price. `swing_points` adds `SH/SL/HH/HL/LH/LL` visual labels matching `EhukaiMarketStructure.mq5`. |
| `analyze bias` | `SYMBOL` | `bias: bullish/bearish/neutral`, `confidence: float`, `reasoning: str` | One-line directional bias |

**`analyze topdown` JSON schema:**
```json
{
  "symbol": "USDJPY",
  "generated_at": "2026-04-24T09:02:00Z",
  "timeframes": {
    "MN1": {
      "trend": "bullish",
      "structure": "HH_HL",
      "current_price": 155.41,
      "support": 154.80,
      "resistance": 156.20,
      "swing_highs": [{ "time": "2026-04-20T00:00:00Z", "price": 156.20 }],
      "swing_lows": [{ "time": "2026-04-15T00:00:00Z", "price": 154.80 }]
    },
    "W1": { "..." : "..." },
    "D1": { "..." : "..." },
    "H4": { "..." : "..." },
    "H1": { "..." : "..." },
    "M15": { "..." : "..." }
  },
  "bias": "bullish",
  "confluence_score": 0.83,
  "notes": ["D1: bullish structure (HH_HL); support=154.8, resistance=156.2"]
}
```

### 6.6 `mt5 screenshot`

OS-level screen capture using `mss`. Captures the MT5 window or full desktop. Does not interact with MT5 internals.

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `screenshot take` | `--output PATH` `--window TEXT` `--monitor INT` | `path`, `width`, `height`, `timestamp` | Capture MT5 window. `--monitor` overrides `screenshot_monitor` config (default `0` = primary). |
| `screenshot tda` | `SYMBOL --timeframes TEXT --output-dir PATH --final-timeframe TF --visual-manifest/--no-visual-manifest --context/--no-context --manifest/--no-manifest --context-bars INT --fvg-limit INT` | `symbol`, `captured_at`, `frames`, `visual_manifest`, `ehukai_analysis`, `manifest_path`, `final_timeframe`, `final_title` | Capture visual top-down-analysis frames. After capture, restores the active chart to `--final-timeframe` (default `M15`). Use `--final-timeframe none` to leave the last captured timeframe active. By default writes a sibling JSON manifest and attaches per-frame Ehukai structure/FVG/liquidity context so agents can combine screenshots with exact data from the same visual indicator semantics. |
| `screenshot dom` | `SYMBOL` `--output PATH` `--output-dir PATH` `--window TEXT` `--open/--no-open` `--close/--no-close` `--settle-seconds FLOAT` | `path`, `symbol`, `w`, `h`, `window_title`, `panel_opened`, `panel_closed`, `open_result`, `close_result` | Open Charts > Depth Of Market for SYMBOL, capture the MT5 window, and close/toggle the DOM panel by default so it does not block the chart. Use `--no-close` only for manual inspection. |
| `screenshot annotate` | `--input PATH` `--output PATH` `--text TEXT` `--xy INT INT` | `path` | Add text overlay to image |
| `screenshot list` | `--dir PATH` | `[{path, timestamp, size_kb}]` | List saved screenshots |

**Window targeting:** `--window` matches on window title substring (default: `"MetaTrader 5"`).

### 6.7 `mt5 order` — Place / Manage Orders

**All order commands require an active MT5 connection. Live trading requires `--live` flag (see §7).**

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `order market` | `SYMBOL buy/sell` `--volume FLOAT` `--risk-pct FLOAT` `--sl FLOAT` `--tp FLOAT` `--comment TEXT` `--strategy-id TEXT` `--magic INT` `--deviation INT` `--filling {FOK,IOC,RETURN,auto}` | `ticket`, `symbol`, `type`, `volume`, `price`, `sl`, `tp`, `time`, `magic`, `strategy_id`, `retcode` | Market order. `--risk-pct` auto-sizes volume from account equity and SL distance using `trade_tick_value` (mutually exclusive with `--volume`). `--strategy-id` tags the order for per-strategy history filtering; defaults to config `magic` expressed as string. |
| `order list` | `--symbol TEXT` `--strategy-id TEXT` | `[{ticket, symbol, type, volume_initial, volume_current, price_open, price_current, sl, tp, state, type_filling, type_filling_name, magic, strategy_id, comment}]` | Current pending orders from `orders_get`. Use this before relying on chart-only trade-panel reads. |
| `order limit` | `SYMBOL buy/sell` `--price FLOAT` `--volume FLOAT` `--risk-pct FLOAT` `--sl FLOAT` `--tp FLOAT` `--expiry DATETIME` `--strategy-id TEXT` `--magic INT` `--filling {FOK,IOC,RETURN,auto}` | same + `expiry`, `strategy_id` | Limit pending order. `--filling auto` uses `ORDER_FILLING_RETURN` for pending placement. |
| `order stop` | `SYMBOL buy/sell` `--price FLOAT` `--volume FLOAT` `--risk-pct FLOAT` `--sl FLOAT` `--tp FLOAT` `--strategy-id TEXT` `--magic INT` `--filling {FOK,IOC,RETURN,auto}` | same + `strategy_id` | Stop pending order. `--filling auto` uses `ORDER_FILLING_RETURN` for pending placement. |
| `order modify` | `TICKET` `--sl FLOAT` `--tp FLOAT` `--price FLOAT` | `ticket`, `result`, `retcode` | Modify pending/position |
| `order cancel` | `TICKET` | `ticket`, `result`, `retcode` | Cancel pending order |
| `order poll-fill` | `TICKET` `--timeout-ms INT` | `ticket`, `filled: bool`, `retcode`, `time_filled` | Poll `orders_get()` + `positions_get()` up to `timeout-ms` (default 5000) to confirm a fill after retcode 10008 (`TRADE_RETCODE_PLACED`). Library entry: `order.poll_fill(ticket, timeout_ms=5000)`. Returns `{"filled": False}` on timeout; caller chooses to cancel. |
| `order dryrun` | (same as `order market`) | `margin`, `margin_free`, `margin_level`, `profit`, `retcode`, `dry_run: true` | Pre-flight check via `mt5.order_check()` — broker-validated, no order sent |

**Order field notes:**
- `--strategy-id` is the human-readable tag (e.g. `"gopher-gate"`, `"fvg-sniper"`). Stored in the `comment` field (MT5 `ORDER_COMMENT` max 31 chars) and mapped to an `int` magic for `history` filtering. Resolution order:
  1. If `strategy_ids` map in config has an entry for the id, use that magic int (must be `< 100000`)
  2. Else auto-derive: `magic = int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000` (deterministic, collision-resistant in the `[100000, 180000)` range, reserves `< 100000` for manual/config magics and the default)
  3. Else (no `--strategy-id` supplied): use config `magic` (default `88888`, which is safely `< 100000`)
  The auto-derived magic is logged on first use so operators can pin it in `strategy_ids` if preferred. `history stats --strategy-id <id>` applies the same resolution — auto-derivation works end-to-end without configuration, so two runtime instances using different `--strategy-id` values always isolate.
- `--strategy-id` is validated at the risk gate: if `len(strategy_id) > 31`, the order is rejected with `RISK_STRATEGY_ID_TOO_LONG` before any MT5 call is made. MT5's `ORDER_COMMENT` field is capped at 31 characters; truncation is not used because two distinct IDs could silently collide.
- `--risk-pct FLOAT` auto-computes volume as `equity × risk_pct / (sl_distance_points × trade_tick_value)`. `sl_distance_points = abs(entry_price - sl) / symbol_info.point`. Requires `--sl`. Mutually exclusive with `--volume`. Uses `market info` `trade_tick_value` — never hardcoded. Note: `trade_tick_value` is per 1.0 lot per point; `sl_distance_points` must therefore be in points (not pips) to keep units consistent.
- `--magic` defaults to config `magic` (88888); override per-order if needed. Prefer `--strategy-id` for new strategies.
- `--deviation` defaults to config `deviation` (20 points); applies to market orders only.
- `--filling auto` (default) reads `mt5.symbol_info(symbol).filling_mode` bitmask for market orders and uses `ORDER_FILLING_RETURN` for pending orders. Set explicitly only when the broker requires a fixed mode. Without the correct filling mode, `order_send()` returns `TRADE_RETCODE_INVALID_FILL` (10030). If `filling=auto` still returns 10030, the error envelope includes the raw `filling_mode` bitmask so the caller can pin an explicit mode.
- `--sl` is **required** for `order market`. The risk gate enforces `min_sl_distance_points` and rejects orders with no stop-loss.
- `order dryrun` calls `mt5.order_check(request)` — full broker-side pre-flight that validates margin, stops, and symbol rules before any real order is sent.

### 6.8 `mt5 position`

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `position list` | `--symbol TEXT` | `[{ticket, symbol, type, volume, open_price, sl, tp, profit, swap}]` | All open positions |
| `position show` | `TICKET` | Single position dict | One position detail |
| `position close` | `TICKET` `--volume FLOAT` | `ticket`, `result`, `profit` | Full or partial close |
| `position close-all` | `--symbol TEXT` | `[{ticket, result, profit}]` | Close all (or by symbol) |
| `position move-sl` | `TICKET --sl FLOAT` | `ticket`, `result` | Adjust stop-loss |
| `position breakeven` | `TICKET` `--buffer-points INT` | `ticket`, `result`, `sl_set_to` | Move SL to open price. `--buffer-points` (default `0`) adds the specified number of points beyond open price in the trade's favor (e.g. `--buffer-points 5` on a BUY sets SL to `open_price + 5 * symbol_info.point`). Use a positive buffer to clear spread/commission costs. |

### 6.9 `mt5 history`

| Command | Args | JSON output keys | Description |
|---------|------|-----------------|-------------|
| `history orders` | `--from DATE --to DATE --symbol TEXT --strategy-id TEXT` | `[{ticket, symbol, type, volume, price, sl, tp, time_setup, time_done, state, magic, strategy_id}]` | Order history. `--strategy-id` filters to orders placed with that tag (matched on `magic` value). |
| `history deals` | `--from DATE --to DATE --symbol TEXT --strategy-id TEXT` | `[{ticket, order, symbol, type, volume, price, profit, commission, swap, time, magic}]` | Deal history with optional per-strategy filter. |
| `history stats` | `--from DATE --to DATE --strategy-id TEXT` | `{trades, win_rate, total_profit, avg_profit, avg_loss, profit_factor, max_drawdown}` | Performance summary, optionally scoped to one strategy. Without `--strategy-id`, aggregates all magic numbers. |

---

## 7. Safety & Risk System

Autonomous trading commands carry significant financial risk. The following guardrails are enforced in `core/risk.py` and checked before any order is sent.

### 7.1 Demo / Live gate

- **Default:** `live = false` in config. All order commands execute on the **demo account**.
- **Live trading:** Requires ALL of:
  1. `"live": true` in config file, **AND**
  2. `--live` CLI flag at invocation, **AND**
  3. `MT5_LIVE=1` environment variable set
- If any of the three is missing, the command prints a clear error and exits code 1. No live order is ever sent silently.
- **Runtime `trade_mode` assertion (critical):** Even when all three gates pass, `core/risk.py` calls `mt5.account_info().trade_mode` at execution time and asserts it equals `ACCOUNT_TRADE_MODE_DEMO` (value `0`) unless `--live` is active. This check runs at order time, not connection time, because accounts can be swapped in the terminal without restarting the CLI. A `trade_mode == ACCOUNT_TRADE_MODE_REAL` on a "demo" config is a hard reject with error code `RISK_LIVE_GATE_BLOCKED`.

### 7.2 Risk envelope (checked pre-order)

**Portfolio-level guards** (state of existing positions):

| Guard | Config key | Default | Behavior on breach |
|-------|-----------|---------|-------------------|
| Max open positions | `max_positions` | 5 | Reject, `RISK_MAX_POSITIONS` |
| Max daily loss | `max_daily_loss` | 50.0 (account currency) | Reject, `RISK_MAX_DAILY_LOSS`. **Daily loss = realized P&L from deals closed today + floating P&L of all open positions at check time.** Both components are included so a large open loser cannot evade the cap. Realized component: sum of `deal.profit + deal.commission + deal.swap` for all deals since `00:00 UTC` today. Floating component: sum of `position.profit` across all open positions. |
| Symbol allowlist | `symbol_allowlist` | `[]` (= allow all) | Reject, `RISK_SYMBOL_NOT_ALLOWED` |
| Min free margin | `min_free_margin_pct` | 20 (%) | Reject, `RISK_INSUFFICIENT_MARGIN` |

**Per-order guards** (properties of the incoming order request):

| Guard | Config key | Default | Behavior on breach |
|-------|-----------|---------|-------------------|
| Max lot per order | `max_lot_per_order` | 1.0 | Reject, `RISK_MAX_LOT_EXCEEDED` |
| Min SL distance | `min_sl_distance_points` | 50 | Reject orders with no SL or SL too close, `RISK_NO_STOP_LOSS` |
| Max spread at order time | `max_spread_points` | 30 | Reject, `RISK_SPREAD_TOO_WIDE` |
| Max orders per minute | `max_orders_per_minute` | 10 | Reject (`core/risk.py` maintains a sliding 60-second window counter), `RISK_RATE_LIMIT` |

All guards are checked in sequence in `core/risk.py` before the `order_send()` call.

### 7.3 Dry-run mode

- `order dryrun` validates the full request (symbol, volume, SL/TP distances, risk checks) and returns what the order *would* send — without placing it.
- `--dry-run` flag accepted by all order commands as an alias.

### 7.4 Kill-switch

```
mt5 kill-switch               # Close ALL open positions, cancel ALL pending orders
mt5 kill-switch --symbol SYM  # Same but scoped to one symbol
```

Requires confirmation prompt (or `--yes` flag to skip in scripts).

**Partial failure behavior:** if one position close or order cancel fails mid-sequence, the kill-switch continues to the remaining tickets and does not abort. The return value is a list of per-ticket results: `{ticket, ok, error}`. The caller is responsible for re-running or alerting on any `ok: false` entries. This ensures the account is maximally flattened even when individual operations fail.

---

## 8. Broker-Specific Notes (Trading.com)

This CLI is designed for use with a locally running MT5 terminal. The primary validated broker is **Trading.com (US)**. Constraints below are enforced in `core/risk.py` and `utils/mt5_backend.py` as defaults; they can be overridden via config for other brokers.

### Filling mode

Trading.com advertises `ORDER_FILLING_FOK` (Fill or Kill) for market orders through `symbol_info().filling_mode` bitmask value `1`; `filling=auto` will select FOK for market orders. Pending limit/stop placement uses `ORDER_FILLING_RETURN` by default because MT5 accepts it for pending orders on this terminal while FOK pending placement can fail before returning a normal trade retcode. If a market `order_send()` returns retcode `10030` (`TRADE_RETCODE_INVALID_FILL`), force `filling=FOK` explicitly in config:
```json
{ "filling": "FOK" }
```
The error envelope on 10030 always includes the raw `filling_mode` bitmask for diagnosis.

### No hedging / FIFO

Trading.com US operates under **FIFO (First In First Out)** rules with **no hedging**:
- You cannot hold simultaneous long and short on the same symbol
- If multiple positions exist on the same symbol, MT5 will close the oldest first when you send a close request
- **TICKET argument vs. FIFO:** `position close TICKET --volume FLOAT` passes the specified ticket in `order_send(position=ticket)`. Under strict FIFO, the broker may redirect a partial close to the oldest ticket for that symbol, ignoring the passed ticket. Do not assume the explicitly passed ticket is the one closed; always inspect the returned `ticket` in the response. For full closes on the exact ticket, this is not an issue.

`core/risk.py` adds a guard: if a new order would create an opposing position on a symbol already open, it rejects with error `RISK_HEDGE_BLOCKED` (unless `allow_hedging=true` is set in config for non-US brokers).

### Symbol naming

Trading.com symbols use standard names: `USDJPY`, `EURUSD`, etc. (no `.m` or `raw` suffixes on FX majors). If `symbol_select()` fails, run `market search --pattern USD` to find the broker-specific exact name. The `SKILL.md` documents this as step 0 for any new symbol workflow.

### Rollover (daily close)

The forex daily close is **22:00 UTC (5 PM EST)**. At this time:
- Spreads widen 10–15× normal on FX majors for 2–5 minutes
- The `market info` `spread` field will reflect the widened value
- The risk gate's `max_spread_points` check will block new orders during the spike if configured correctly
- `market sessions` provides the static FX session table; position managers should monitor `market info` spread around this time

### Leverage

Default leverage for USDJPY at Trading.com US: **1:50** (regulatory cap for US retail). `account info` now returns `leverage`. Strategies must respect `AURUM_EQUITY_HARD_FLOOR_PCT` / margin requirements accordingly.

### Retcode reference (Trading.com–specific behavior)

| Retcode | Name | Behavior |
|---|---|---|
| 10009 | `TRADE_RETCODE_DONE` | Order fully executed — fill confirmed |
| 10008 | `TRADE_RETCODE_PLACED` | Order placed but fill not yet confirmed — poll `orders_get()` |
| 10006 | `TRADE_RETCODE_REJECT` | Rejected by broker — check symbol, volume, margin |
| 10030 | `TRADE_RETCODE_INVALID_FILL` | Wrong filling mode — pin `FOK` in config |
| 10027 | `TRADE_RETCODE_NOT_ALLOWED` | Algo trading disabled in MT5 terminal — enable via Tools → Options → Expert Advisors |
| 10013 | `TRADE_RETCODE_INVALID_STOPS` | SL/TP too close to price or exactly at entry — add buffer |
| 10016 | `TRADE_RETCODE_INVALID_VOLUME` | Volume outside `volume_min`/`volume_max` or not a multiple of `volume_step` |

All retcodes surfaced in `error.mt5_retcode` in the JSON envelope.

---

## 9. REPL

Invoked when no subcommand is given: `mt5` → REPL.

```
$ mt5
  ₿ MT5 CLI v0.1  |  Trading.com-Demo  |  Balance: 10,119.50 USD
  Type 'help' for commands, 'exit' to quit.

mt5 (USDJPY)> rates fetch USDJPY H4 --bars 3 --json
mt5 (USDJPY)> analyze topdown USDJPY --timeframes D1,H4,H1
mt5 (USDJPY)> order market USDJPY buy --volume 0.01 --sl 158.50 --tp 155.00 --dry-run
```

- Built with `prompt-toolkit` (`ReplSkin` from CLI-Anything)
- Context tracks last-used symbol (auto-filled as prompt prefix)
- `help` prints command table grouped by category
- Arrow-key history, tab-completion on command names
- `standalone_mode=False` — errors print and REPL continues

---

## 10. CLI Patterns & Dependencies

### Dependencies

```python
install_requires=[
    "MetaTrader5>=5.0.45",     # Windows-only MT5 Python binding
    "click>=8.0.0",             # CLI framework
    "prompt-toolkit>=3.0.0",    # REPL + autocomplete
    "pandas>=2.0.0",            # Rate data manipulation
    "pandas-ta>=0.3.14b",       # Technical indicators
    "mss>=9.0.0",               # Cross-monitor screen capture
    "Pillow>=10.0.0",           # Screenshot annotation
    "python-dateutil>=2.9.0",   # Date parsing for --from/--to
]
```

### Entry point

```
console_scripts:
  mt5 = metatrader5_cli.mt5.mt5_cli:main
```

### Platform constraint

`MetaTrader5` package is **Windows-only**. The CLI will raise a clear `ImportError` with a human-readable message on macOS/Linux.

---

## 11. Testing Strategy

### Unit tests (`test_core.py`)
- Mock the `MetaTrader5` package using `unittest.mock`
- Test each core module independently (account, rates, order, risk)
- Test config load/save/merge
- Test risk guardrail logic (positions, daily loss, allowlist)
- No real MT5 terminal required; fast (<1 s)

### Integration tests (`test_e2e.py`)
- Require a running MT5 terminal connected to a **demo account**
- Marked `@pytest.mark.integration` — skipped in CI unless `MT5_DEMO_INTEGRATION=1`
- Cover: connect, fetch rates, compute indicator, place order on demo, close position
- **Never run against a live account** (asserted by checking `account.trade_mode != ACCOUNT_TRADE_MODE_REAL`)

### No live-money tests. Ever.

---

## 12. Deferred / v2

| Feature | Why deferred | Likely approach |
|---------|-------------|-----------------|
| Apply indicator to chart window | Same | EA bridge + `ChartIndicatorAdd()` |
| Native `ChartScreenShot()` | Requires running EA; higher fidelity than mss | EA bridge |
| Multi-terminal routing | Out of scope for v1 | Config profiles + `--profile` flag |
| Remote / API server mode | Requires a REST wrapper | FastAPI server wrapping core layer |
| Backtest integration | Strategy layer, not primitive layer | Separate tool |

---

## 13. Key Workflows (End-to-End)

### Workflow A — Top-down analysis before a trade

```bash
# 1. Confirm connection
mt5 config test

# 2. Multi-TF analysis
mt5 analyze topdown USDJPY --timeframes MN1,W1,D1,H4,H1,M15 --json

# 3. Key levels
mt5 analyze structure USDJPY H4 --bars 200 --json

# 4. Screenshot current chart for visual reference
mt5 screenshot take --output ~/analysis/usdjpy-h4.png

# 5. Check account risk envelope before trading
mt5 account risk --json
```

### Workflow B — Place an order with full safety checks

```bash
# Dry-run first
mt5 order market USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00 --dry-run --json

# If dry-run passes, place for real (demo by default)
mt5 order market USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00 --json

# Watch the position
mt5 position list --symbol USDJPY --json

# Move to breakeven once in profit
mt5 position breakeven TICKET_ID --json
```

### Workflow C — Autonomous agent loop (AI caller)

```bash
# Agent invokes this sequence in a loop:
mt5 analyze topdown USDJPY --timeframes D1,H4,H1 --json   # → bias
mt5 account risk --json                                     # → safe to trade?
mt5 order market USDJPY buy --volume 0.01 --sl X --tp Y --json  # → ticket
mt5 position list --json                                    # → confirm open
# ... time passes ...
mt5 position close TICKET --json                            # → realized P&L
mt5 history stats --from TODAY --json                       # → session summary
```

---

## 14. Open Questions (Resolved)

| Question | Resolution |
|---|---|
| **Volume calculation via `--risk-pct`** | **Yes** — added to all order commands. Computes volume from `equity × risk_pct / (sl_distance_points × trade_tick_value)`. Mutually exclusive with `--volume`. |
| **Tick subscription / streaming** | **Deferred to v2.** FX strategies poll; streaming requires a persistent process loop outside the CLI's command model. |
| **SKILL.md agent doc** | Written alongside implementation. First documented workflow: `market search` → `market info` → `analyze topdown` → `order dryrun` → `order market`. |
| **Screenshot multi-monitor targeting** | **`--monitor INT` flag added** to `screenshot take`. Default `0` (primary). MT5 is on monitor 2 in production config — set `screenshot_path` and `screenshot_monitor: 2` in config. |
| **Time format in JSON** | **ISO-8601 UTC** throughout (`"2026-04-24T09:02:00Z"`). Bridge converts all MT5 Unix epoch integers before surfacing. No raw epoch integers in any JSON output. |
| **Magic number / strategy-id convention** | **Resolved** — `--strategy-id TEXT` on all order commands. Config `strategy_ids` map stores human-id → magic int. `history` commands support `--strategy-id` filter. Default magic `88888` when unset. |
| **Broker symbol name variants** | **Yes** — `SKILL.md` documents `market search` as step 0 for any new symbol. `market info` call validates symbol is tradable before any workflow proceeds. |
| **Filling mode fallback on 10030** | **Resolved** — error envelope includes raw `filling_mode` bitmask on retcode 10030. Trading.com always FOK; pin `"filling": "FOK"` in config if `auto` still fails. |
| **REPL reconnect on MT5 restart** | **Auto-reconnect once transparently.** If second attempt also fails, surface as `MT5_CONNECTION_ERROR` and drop to error prompt without exiting REPL. |
