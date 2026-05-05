# MT5 CLI — Operator SOP

Quick reference for humans operating the CLI.  For agent-facing capability
docs see `metatrader5_cli/mt5/skills/SKILL.md`.

> **`--json` and `--live` are top-level flags** and must come before the
> subcommand: `mt5 --json account info`, not `mt5 account info --json`.

---

## 1. Connect and verify

```bash
mt5 config test               # ping terminal; shows server + balance
mt5 --json account info       # full account snapshot
mt5 --json account risk       # risk envelope status (positions used, daily loss, etc.)
```

If `config test` fails, check that MetaTrader 5 is running and **Tools →
Options → Expert Advisors → "Allow algorithmic trading"** is enabled.

---

## 2. Top-down analysis before a trade

```bash
mt5 market search --pattern USDJPY                 # confirm broker symbol name
mt5 --json market info USDJPY                      # tick, spread, volume limits
mt5 --json chart ensure USDJPY --timeframe M15     # make active chart explicit
mt5 --json market depth USDJPY --levels 5          # optional structured DOM snapshot
mt5 --json screenshot dom USDJPY                   # GUI DOM panel from Charts > Depth Of Market
mt5 --json analyze topdown USDJPY \
    --timeframes MN1,W1,D1,H4,H1,M15
mt5 --json analyze structure USDJPY H4 --bars 200
mt5 --json screenshot tda USDJPY --timeframes H1,M15,M5 --final-timeframe M15
mt5 --json analyze sniper-poc USDJPY --direction auto --max-spread-points 30 --min-stop-points 50
```

Use `chart current` to read the active MT5 chart title and `chart ensure
SYMBOL --timeframe M15` before GUI or screenshot work. This is symbol/broker
agnostic: the command targets whatever broker-exact symbol MT5 accepts in the
active chart, then uses the standard timeframe toolbar. It is preferred over
automating File > New Chart because broker menus and recent-symbol lists vary.

TDA leaves the active chart on `M15` after capture by default. This is
symbol/broker agnostic and only depends on MT5 timeframe toolbar support. Use
`--final-timeframe none` when an agent should leave the chart on the last
captured timeframe instead.

Visual TDA also returns a JSON manifest. The PNGs show the chart overlays, and
the manifest explains the vendored Ehukai indicators plus recomputed structure
and FVG data for each frame. The canonical indicator sources are kept in the
repo under `metatrader5_cli/mt5/mql5/Indicators/`; the MT5 terminal copy is the
deployed runtime copy. Agents should compare screenshot labels such as `BULL
FVG OPEN`, `HH`, `HL`, `BULLISH BOS`, and `MS M15: ...` with the returned
`structured_context` levels before forming a trade thesis.

Use `mt5 --json ehukai structure SYMBOL TF`, `mt5 --json ehukai fvg SYMBOL TF`,
and `mt5 --json ehukai liquidity SYMBOL TF` when an agent needs the data
representation of the exact visual overlay logic. Generic `analyze` and
`indicator` commands remain available for research, but visual TDA uses the
Ehukai layer to avoid duplicate market-structure or FVG interpretations. Apply
only `EhukaiTDAOverlay` for normal screenshots; its screenshot mode hides
oversized FVGs and distant liquidity pools so historic zones do not visually
overpower actionable context.

`analyze sniper-poc` is read-only. It combines Ehukai structure/FVG/liquidity,
DOM when available, and current bid/ask rules to return either a candidate M1
POC limit plan or `no_trade`. A buy limit must be safely below bid because it
fills on ask; a sell limit must be safely above ask because it fills on bid.
The suggested SL is widened to at least `--min-stop-points` so the plan is
closer to what `order dryrun` and broker stop-distance rules will accept.

Depth of Market has two paths. Use `market depth` for structured bid/ask
ladder data when the broker exposes MT5 Python `market_book_*` data. Use
`chart depth-of-market` or `screenshot dom` for the actual MT5 GUI panel opened
from Charts > Depth Of Market. Treat DOM as an execution-quality input: spread,
top-of-book liquidity, nearby liquidity pockets, and imbalance.

Practical validation on this Trading.com demo terminal: `screenshot tda`
captures H1/M15/M5 chart context, `chart depth-of-market USDJPY` opens the GUI
DOM panel, and `screenshot dom USDJPY` captures it. By default the command
closes/toggles the DOM panel after capture so it does not block the chart; use
`--no-close` only when intentionally inspecting it manually. `market depth USDJPY` currently fails because the
broker/terminal does not expose DOM through `market_book_add()` in the Python
API, so use the GUI screenshot path for Trading.com DOM evidence.

---

## 3. Place an order — dry-run first

```bash
# Local risk gates + broker order_check(); no order sent
mt5 --json order dryrun USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00

# Inspect pending orders before/after placement
mt5 --json order list --symbol USDJPY

# Place only if dry-run ok:true
mt5 --json order market USDJPY buy --volume 0.10 --sl 158.50 --tp 154.00

# Confirm fill
mt5 --json position list --symbol USDJPY

# Move to breakeven once in profit
mt5 --json position breakeven TICKET_ID
```

For a live (real-money) account every mutating command additionally requires
all three live-gate conditions simultaneously:
- `mt5 --live ...` flag on the invocation
- `MT5_LIVE=1` environment variable
- `"live": true` in `~/.config/cli-anything-mt5.json`

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
mt5 --json history orders --from 2026-01-01 --to 2026-01-31
mt5 --json history deals  --from 2026-01-01 --to 2026-01-31 --symbol USDJPY
mt5 --json history stats  --from 2026-01-01 --to 2026-01-31
mt5 --json history stats  --from 2026-01-01 --to 2026-01-31 --strategy-id gopher-gate
```

---

## 6. Interactive REPL

```bash
mt5          # launch REPL (no subcommand = REPL mode)
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
| 10030 | `TRADE_RETCODE_INVALID_FILL` | Wrong filling mode. Market orders usually need the broker-advertised mode; pending orders default to RETURN. |
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
