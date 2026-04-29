# MT5 CLI — Agent Capability Reference

Use this document before placing any trade or calling any MT5 command in an
agentic context.  It defines the mandatory pre-trade workflow, the risk gates
you will encounter, and the JSON envelope contract.

---

## Step 0 — Always verify the symbol first (`market search`)

Before any analysis or order, confirm the broker-exact symbol name:

```bash
mt5 market search USD          # returns all symbols containing "USD"
mt5 market search EURUSD       # exact match check
```

Broker symbol names differ: `EURUSD`, `EURUSD.`, `EURUSDm`, `FX:EURUSD`.
**Never assume** a symbol name from training data.  Use the name returned by
`market search` verbatim in all subsequent commands.

---

## Top-Down Workflow (spec §14)

Execute this sequence in order for every trading decision:

```bash
# 1. Verify symbol (Step 0 — mandatory)
mt5 market search USDJPY

# 2. Inspect tick and spread
mt5 market info USDJPY --json

# 3. Multi-timeframe bias
mt5 analyze topdown USDJPY --timeframes MN1,W1,D1,H4,H1,M15 --json

# 4. Key structure levels
mt5 analyze structure USDJPY H4 --bars 200 --json

# 5. Dry-run before committing
mt5 order dryrun USDJPY buy --volume 0.01 --sl 158.50 --json

# 6. Place the order only if dry-run returns ok:true
mt5 order market USDJPY buy --volume 0.01 --sl 158.50 --json

# 7. Confirm the position opened
mt5 position list --symbol USDJPY --json
```

**Never skip step 5 (dry-run).**  A dry-run runs the local risk envelope
first (position limits, daily loss cap, spread check, margin check), then
calls the broker's `order_check()` for a broker-side pre-flight — no order
is sent.  Local risk gates and broker validation are both applied; neither
substitutes for the other.

---

## Risk Envelope (what gates exist)

Every mutating command (`order market`, `order limit`, `order stop`,
`position close`, `position move-sl`, `position breakeven`,
`order cancel`) passes through these checks in order:

| Gate | Config key | Default | Error code |
|---|---|---|---|
| Live-account gate | `--live` flag + `MT5_LIVE=1` env + `cfg.live` | blocked on real accounts | `RISK_LIVE_GATE_BLOCKED` |
| Max open positions | `max_positions` | 5 | `RISK_MAX_POSITIONS` |
| Max daily loss | `max_daily_loss` | 50.0 (account currency) | `RISK_MAX_DAILY_LOSS` |
| Symbol allowlist | `symbol_allowlist` | `[]` (allow all) | `RISK_SYMBOL_NOT_ALLOWED` |
| Min free margin | `min_free_margin_pct` | 20 % | `RISK_INSUFFICIENT_MARGIN` |
| No-stop-loss | `min_sl_distance_points` | 50 pts | `RISK_NO_STOP_LOSS` |
| Max lot per order | `max_lot_per_order` | 1.0 | `RISK_MAX_LOT_EXCEEDED` |
| Max spread | `max_spread_points` | 30 pts | `RISK_SPREAD_TOO_WIDE` |
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

## Strategy Isolation (`--strategy-id`)

Tag each strategy's orders for isolated history filtering:

```bash
mt5 order market EURUSD buy --volume 0.01 --sl 1.0800 \
    --strategy-id gopher-gate --json

mt5 history stats --from 2026-01-01 --strategy-id gopher-gate --json
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
from cli_anything.mt5.core import account, analyze, market, order, position, rates

info = account.info()            # {"ok": True, "data": {...}}
tick = market.tick("EURUSD")
r    = rates.get("EURUSD", "H1", bars=200)
result = order.place_market(
    "EURUSD", "buy",
    volume=0.01, sl=1.0800,
    cfg=cfg, is_live_intent=False,
)
```
