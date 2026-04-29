# MT5 CLI — Operator SOP

Quick reference for humans operating the CLI.  For agent-facing capability
docs see `cli_anything/mt5/skills/SKILL.md`.

---

## 1. Connect and verify

```bash
mt5 config test          # ping terminal; shows server + balance
mt5 account info --json  # full account snapshot
mt5 account risk --json  # risk envelope status (positions used, daily loss, etc.)
```

If `config test` fails, check that MetaTrader 5 is running and **Tools →
Options → Expert Advisors → "Allow algorithmic trading"** is enabled.

---

## 2. Top-down analysis before a trade

```bash
mt5 market search USDJPY            # confirm broker symbol name
mt5 market info  USDJPY --json      # tick, spread, volume limits
mt5 analyze topdown USDJPY \
    --timeframes MN1,W1,D1,H4,H1,M15 --json
mt5 analyze structure USDJPY H4 --bars 200 --json
mt5 screenshot take --output ~/charts/usdjpy-h4.png
```

---

## 3. Place an order — dry-run first

```bash
# Broker-validates margin and fill mode; no order sent
mt5 order dryrun USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00 --json

# Place only if dry-run ok:true
mt5 order market USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00 --json

# Confirm fill
mt5 position list --symbol USDJPY --json

# Move to breakeven once in profit
mt5 position breakeven TICKET_ID --json
```

For a live (real-money) account every mutating command additionally requires:
- `--live` flag on the command
- `MT5_LIVE=1` environment variable
- `"live": true` in `~/.config/cli-anything-mt5.json`

All three must be true simultaneously; any one missing blocks the trade.

---

## 4. Emergency flatten (kill-switch)

```bash
# Interactive confirmation prompt
mt5 kill-switch

# Scope to one symbol
mt5 kill-switch --symbol USDJPY

# Skip confirmation (use in scripts)
mt5 kill-switch --yes
```

Returns a per-ticket result list — inspect `ok` on each entry to see which
positions or orders failed to close.

---

## 5. History and performance

```bash
mt5 history orders --from 2026-01-01 --to 2026-01-31 --json
mt5 history deals  --from 2026-01-01 --symbol USDJPY --json
mt5 history stats  --from 2026-01-01 --json
mt5 history stats  --from 2026-01-01 --strategy-id gopher-gate --json
```

---

## 6. Interactive REPL

```bash
mt5 repl
```

Features: arrow-key history, tab completion on command names, prompt shows
last-used symbol (`mt5 (USDJPY)>`), auto-reconnects once on disconnect.

---

## 7. Common MT5 retcodes

| Code | Meaning | Fix |
|------|---------|-----|
| 10009 | `TRADE_RETCODE_DONE` | Order fully executed — success |
| 10008 | `TRADE_RETCODE_PLACED` | Placed but not yet filled — run `order poll-fill TICKET` |
| 10006 | `TRADE_RETCODE_REJECT` | Rejected by broker — check symbol, volume, margin |
| 10030 | `TRADE_RETCODE_INVALID_FILL` | Wrong filling mode — add `filling = "FOK"` to config |
| 10027 | `TRADE_RETCODE_NOT_ALLOWED` | Algo trading disabled — enable in MT5 → Options → Expert Advisors |
| 10013 | `TRADE_RETCODE_INVALID_STOPS` | SL/TP too close to price — increase buffer |
| 10016 | `TRADE_RETCODE_INVALID_VOLUME` | Volume outside broker min/max or not a valid step |

All retcodes surface in `error.mt5_retcode` in the JSON error envelope.

---

## 8. Config file (`~/.config/cli-anything-mt5.json`)

```json
{
  "server":   "Trading.com-Demo01",
  "login":    123456,
  "password": "secret",
  "magic":    88888,
  "live":     false,

  "max_positions":          5,
  "max_daily_loss":         50.0,
  "max_lot_per_order":      1.0,
  "min_sl_distance_points": 50,
  "max_spread_points":      30,
  "min_free_margin_pct":    20,
  "max_orders_per_minute":  10,
  "symbol_allowlist":       [],
  "allow_hedging":          false,
  "filling":                "auto",

  "strategy_ids": {
    "gopher-gate": 77001,
    "fvg-sniper":  77002
  }
}
```
