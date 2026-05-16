# MT5 CLI — Agent Capability Reference

Use this document before placing any trade or calling any MT5 command in an
agentic context.  It defines the mandatory pre-trade workflow, the risk gates
you will encounter, and the JSON envelope contract.

---

## Step 0 — Always verify the symbol first (`market search`)

Before any analysis or order, confirm the broker-exact symbol name:

```bash
mt5 market search --pattern USD          # returns all symbols containing "USD"
mt5 market search --pattern EURUSD      # exact match check
```

Broker symbol names differ: `EURUSD`, `EURUSD.`, `EURUSDm`, `FX:EURUSD`.
**Never assume** a symbol name from training data.  Use the name returned by
`market search` verbatim in all subsequent commands.

---

## Top-Down Workflow (spec §14)

Execute this sequence in order for every trading decision:

```bash
# 1. Verify symbol (Step 0 — mandatory)
mt5 market search --pattern USDJPY

# 2. Inspect tick and spread
mt5 --json market info USDJPY

# Keep the active GUI chart deterministic for visual analysis
mt5 --json chart ensure USDJPY --timeframe M15

# Optional: inspect current Depth of Market liquidity as JSON
mt5 --json market depth USDJPY --levels 5
mt5 --json screenshot dom USDJPY                     # GUI DOM panel from Charts > Depth Of Market

# 3. Multi-timeframe bias
mt5 --json analyze topdown USDJPY --timeframes MN1,W1,D1,H4,H1,M15

# 4. Key structure levels
mt5 --json analyze structure USDJPY H4 --bars 200

# Optional visual pass; returns chart to M15 after capture by default
mt5 --json screenshot tda USDJPY --timeframes H1,M15,M5 --final-timeframe M15

# Optional direct data for the same visual overlay logic
mt5 --json ehukai structure USDJPY M15
mt5 --json ehukai fvg USDJPY M15 --max-zones 4
mt5 --json ehukai liquidity USDJPY M15

# 5. For sniper entries, ask for a non-mutating candidate first
mt5 --json analyze sniper-poc USDJPY --direction auto --summary

# 6. Dry-run the exact pending request before committing
mt5 --json order dryrun USDJPY buy --order-type limit --price 157.800 --volume 0.001 --sl 157.750 --tp 157.900 --strategy-id ehukai-m1-sniper-poc

# 6b. Inspect existing pending orders
mt5 --json order list --symbol USDJPY

# 7. Place the order only if dry-run returns ok:true and the quote/setup is still fresh
mt5 --json order limit USDJPY buy --price 157.800 --volume 0.001 --sl 157.750 --tp 157.900 --strategy-id ehukai-m1-sniper-poc

# 8. Confirm the position opened
mt5 --json position list --symbol USDJPY
```

**Never skip dry-run.**  A dry-run runs the local risk envelope
first (position limits, daily loss cap, spread check, margin check), then
calls the broker's `order_check()` for a broker-side pre-flight — no order
is sent.  Local risk gates and broker validation are both applied; neither
substitutes for the other.

`analyze sniper-poc` is still only analysis. A returned `candidate` is not a
passing broker pre-flight. Use `setup.order_commands[0]` first, then
`setup.order_commands[1]` only if dry-run returns `ok:true`, the quote has not
run through target, and `order list` shows no conflicting pending order.

Use `order list --symbol SYMBOL` for currently pending orders. Market-order
`--filling auto` follows the broker `filling_mode` bitmask; pending
limit/stop-order `--filling auto` uses `ORDER_FILLING_RETURN`, which this MT5
terminal accepts for pending placement even when market orders advertise FOK.
`order list` only reverse-resolves `strategy_id` for IDs pinned in
`cfg.strategy_ids` or when the caller filters with `--strategy-id`. Treat
`is_agent_magic:true` as "agent-derived magic, name unknown" and do not parse
the broker `comment`; Trading.com can truncate comments before the local
31-character strategy-id limit.

For sniper POC workflows, liquidity freshness is based on `sweep_age_bars`, not
pivot age. `ehukai liquidity` exposes `swept_at` plus `sweep_age_bars`, and
`analyze sniper-poc` uses tighter liquidity pivots on M1/M5 (`length=5`) while
keeping M15+ at the broader context default (`length=14`).

---

## Risk Envelope (what gates exist)

Every mutating command (`order market`, `order limit`, `order stop`,
`position close`, `position move-sl`, `position breakeven`,
`order cancel`) passes through these checks in order:

| Gate | Config key | Default | Error code |
|---|---|---|---|
| Live-account gate | `--live` flag + `MT5_LIVE=1` env + `cfg.live` | blocked on real accounts | `RISK_LIVE_GATE_BLOCKED` |
| Max open positions | `max_positions` | 5 | `RISK_MAX_POSITIONS` |
| Max daily loss | `max_daily_loss` | 2000.0 (account currency) | `RISK_MAX_DAILY_LOSS` |
| Symbol allowlist | `symbol_allowlist` | `[]` (allow all) | `RISK_SYMBOL_NOT_ALLOWED` |
| Min free margin | `min_free_margin_pct` | 20 % | `RISK_INSUFFICIENT_MARGIN` |
| No-stop-loss | `min_sl_distance_points` | 50 pts | `RISK_NO_STOP_LOSS` |
| Max lot per order | `max_lot_per_order` | 2.5 | `RISK_MAX_LOT_EXCEEDED` |
| Max spread | `max_spread_points` | 80 pts | `RISK_SPREAD_TOO_WIDE` |
| Rate limit | `max_orders_per_minute` | 10 | `RISK_RATE_LIMIT` |
| Hedge guard | `allow_hedging` | false | `RISK_HEDGE_BLOCKED` |
| Strategy-ID length | hardcoded | 31 chars | `RISK_STRATEGY_ID_TOO_LONG` |

**Daily loss** includes both realised P&L (deals closed today since 00:00 UTC)
and floating P&L of all open positions — a large open loser cannot evade the
cap.

---

## JSON Envelope Contract

Every command returns one of two shapes.

**Success:**
```json
{"ok": true, "data": {"ticket": 12345678, "symbol": "USDJPY", "type": "buy",
  "volume": 0.01, "price": 157.432, "sl": 158.50, "tp": null,
  "magic": 88888, "strategy_id": null, "retcode": 10009}}
```

**Failure:**
```json
{"ok": false, "error": {"code": "RISK_MAX_POSITIONS",
  "message": "Max open positions (5) reached", "mt5_retcode": null}}
```

```json
{"ok": false, "error": {"code": "MT5_ORDER_REJECTED",
  "message": "Order rejected by broker", "mt5_retcode": 10006}}
```

Always branch on `result["ok"]` before reading `result["data"]`.

---

## Active Chart Targeting

Before any GUI-facing task, use chart targeting instead of relying on the
currently active MT5 tab:

```bash
mt5 --json chart current
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json chart ensure USDJPY --timeframe none
```

`chart ensure` is symbol agnostic. It switches the active chart to the
broker-exact symbol and optional timeframe using MT5 chart controls, then
verifies the MT5 window title. Prefer it over File > New Chart automation
because broker symbol menus and recent-symbol lists vary by terminal.

---

## Visual TDA Indicator Contract

`screenshot tda` gives visual agents both screenshot pixels and data:

- PNG frames show the MT5 chart with the Ehukai overlays.
- `visual_manifest` explains how to interpret the overlays.
- `manifest_path` points to a sibling JSON file containing the same frame paths,
  legend, and structured context.
- Each frame can include `structured_context.structure` from `analyze structure`
  and `structured_context.fvg.zones` from `indicator fvg`.

The canonical indicator sources are vendored in
`metatrader5_cli/mt5/mql5/Indicators/`:

- `EhukaiFVG.mq5`: `EFVG_` objects, `BULL/BEAR FVG OPEN/PARTIAL/FILLED <pips>p`
  labels, rectangle bounds, upper/lower lines, and dashed midlines.
- `EhukaiMarketStructure.mq5`: `EMS_` objects, `HH/HL/LH/LL` labels, `MS <TF>:`
  bias panel, BOS labels, and support/resistance levels.

Use screenshots for spatial confluence and JSON for exact levels. If visual
labels and structured context disagree, report the discrepancy instead of
forcing agreement.

For visual TDA, prefer `ehukai structure` and `ehukai fvg` over generic
`analyze structure` / `indicator fvg`. The generic commands remain available for
research, but the Ehukai commands intentionally mirror the chart overlays.

For chart screenshots, prefer the single `EhukaiTDAOverlay.mq5` overlay. Keep
`EhukaiFVG.mq5`, `EhukaiMarketStructure.mq5`, and `EhukaiLiquiditySwings.mq5`
as primitive/debug overlays only; stacking them on normal TDA charts creates
visual overlap that hurts agent vision.

---

## Depth of Market (DOM)

Use DOM when an agent needs execution context near the current price. There are
two paths:

```bash
# Structured MT5 Python API path
mt5 --json market depth USDJPY --levels 5

# GUI path matching MT5 Charts > Depth Of Market
mt5 --json chart depth-of-market USDJPY
mt5 --json screenshot dom USDJPY --output-dir "$TEMP/mt5-cli/dom"
```

`market depth` returns nearest-first `bids` and `asks`, `best_bid`,
`best_ask`, `spread_points`, `mid`, and `volume_imbalance` when the broker
exposes Python market-book data. `chart depth-of-market` opens the actual MT5
GUI panel. `screenshot dom` opens and captures that panel by default, then
closes/toggles it afterward so it does not block the chart. Use `--no-close`
only when intentionally inspecting the panel manually.

Use it to decide whether to wait, tighten/avoid execution, or ask for human
confirmation when the book is thin, spread is wide, or one side is unusually
heavy. Do not use DOM alone as directional strategy logic. If the broker or
symbol does not expose structured DOM, handle `MT5_MARKET_BOOK_SUBSCRIBE_FAILED`
or `MT5_MARKET_BOOK_UNAVAILABLE`, then use `screenshot dom` for GUI evidence and
continue with `market info`, `market tick`, analysis, and dry-run validation.

For TDA workflows, run DOM as an optional side check after screenshots:

```bash
mt5 --json screenshot tda USDJPY --timeframes H1,M15,M5 --output-dir "$TEMP/mt5-cli/tda"
mt5 --json market depth USDJPY --levels 5
mt5 --json screenshot dom USDJPY --output-dir "$TEMP/mt5-cli/dom"
```

If DOM fails on Trading.com or another retail broker, do not block the TDA
workflow. Use the GUI DOM capture when available, plus TDA frames, `market
tick`, spread from `market info`, and `order dryrun` for execution validation.

TDA should leave the workspace readable for the operator. `screenshot tda`
defaults to `--final-timeframe M15` after all frames are captured. Use
`--final-timeframe none` only when the caller intentionally wants to leave the
chart on the last captured timeframe.

---

## Strategy Isolation (`--strategy-id`)

Tag each strategy's orders for isolated history filtering:

```bash
mt5 --json order market EURUSD buy --volume 0.01 --sl 1.0800 \
    --strategy-id gopher-gate

mt5 --json history stats --from 2026-01-01 --to 2026-01-31 --strategy-id gopher-gate
```

Magic resolution order:
1. `strategy_ids` map in `~/.config/cli-anything-mt5.json` (pin here for repeatability)
2. Auto-derived: `sha256(strategy_id)[:8] % 80000 + 100000`
3. Default config `magic` (88888) when no `--strategy-id` given

Two strategies with different IDs always isolate, even without config.

---

## Useful Library API (for runtime callers)

Import the core layer directly — no subprocess required:

```python
from metatrader5_cli.mt5.core import account, indicator, market, order, position, rates

info = account.info()                    # {"ok": True, "data": {...}}
tick = market.tick("EURUSD")
depth = market.depth("EURUSD", levels=5)
r    = rates.fetch("EURUSD", "H1", bars=200)   # list of OHLCV dicts
ema  = indicator.ema("EURUSD", "H1", period=20)
result = order.place_market(
    "EURUSD", "buy",
    volume=0.01, sl=1.0800,
    cfg=cfg, is_live_intent=False,
)
```
