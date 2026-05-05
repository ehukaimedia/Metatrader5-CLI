# MetaTrader 5 CLI

Command-line and Python API for operating a running MetaTrader 5 terminal through a guarded, JSON-friendly interface.

This project is designed for human operators and coding agents that need to inspect markets, run analysis, dry-run orders, place demo/live-gated trades, manage positions, and query history from any working directory.

## Current Status

- Demo e2e tested against `Trading.comMarkets-MT5`.
- Live trading is blocked unless all three live gates are enabled.
- The global command is `mt5` after installation.

## Install Globally

From this repository:

```powershell
cd "C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI"
python -m pip install -e . --no-deps
```

This installs an editable package and creates the console script:

```powershell
mt5 --help
```

On this machine the script is installed at:

```text
C:\Users\arsen\AppData\Roaming\Python\Python313\Scripts\mt5.exe
```

If a new shell cannot find `mt5`, ensure the user Scripts directory is on `PATH`:

```powershell
$env:Path -split ';' | Select-String 'Python313\\Scripts'
```

Agents in other repos can use the CLI directly once this command resolves:

```powershell
mt5 --json account info
mt5 market search --pattern USDJPY
mt5 --json market info USDJPY
```

## Configuration

Config file:

```text
%USERPROFILE%\.config\cli-anything-mt5.json
```

Example:

```json
{
  "server": "Trading.comMarkets-MT5",
  "login": 105112007,
  "live": false,
  "magic": 88888,
  "deviation": 20,
  "filling": "auto",
  "max_positions": 5,
  "max_daily_loss": 50.0,
  "max_lot_per_order": 0.10,
  "min_sl_distance_points": 50,
  "max_spread_points": 30,
  "min_free_margin_pct": 20,
  "max_orders_per_minute": 10,
  "symbol_allowlist": [],
  "allow_hedging": false,
  "strategy_ids": {},
  "screenshot": {
    "output_dir": null,
    "window_substring": "MT5"
  }
}
```

If MetaTrader 5 is already open and logged in, the password can be omitted. The bridge will call bare `mt5.initialize()` in that case.

## Safety Model

Every mutating path is guarded. For real-money accounts, live trading requires all three gates:

1. `"live": true` in `%USERPROFILE%\.config\cli-anything-mt5.json`
2. `MT5_LIVE=1` in the environment
3. `--live` on the CLI invocation

Example live invocation shape:

```powershell
$env:MT5_LIVE = "1"
mt5 --live --json order market USDJPY buy --volume 0.01 --sl 159.500
```

For demo or test operation, do not pass `--live`.

## Agent Workflow From Any Repo

Use this sequence before any trade:

```powershell
mt5 market search --pattern USDJPY
mt5 --json market info USDJPY
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json market depth USDJPY --levels 5
mt5 --json analyze topdown USDJPY --timeframes D1,H4,H1
mt5 --json screenshot tda USDJPY --timeframes D1,H4,H1,M15,M5,M1 --output-dir "$env:TEMP\mt5-cli\screenshots" --final-timeframe M15
mt5 --json analyze sniper-poc USDJPY --direction auto --max-spread-points 30
mt5 --json order dryrun USDJPY buy --order-type limit --price 157.800 --volume 0.001 --sl 157.750 --tp 157.900 --strategy-id ehukai-m1-sniper-poc
mt5 --json order list --symbol USDJPY
mt5 --json order limit USDJPY buy --price 157.800 --volume 0.001 --sl 157.750 --tp 157.900 --strategy-id ehukai-m1-sniper-poc
mt5 --json position list --symbol USDJPY
```

Rules for agents:

- Always run `market search --pattern SYMBOL` first.
- Use `chart ensure SYMBOL --timeframe M15` before GUI/screenshot work so MT5 is on the intended active chart.
- Try `market depth SYMBOL --levels N` when structured book data is available.
- Use `chart depth-of-market SYMBOL` and `screenshot dom SYMBOL` for the actual MT5 GUI panel opened from Charts > Depth Of Market.
- Always run `order dryrun` before `order market`, `order limit`, or `order stop`; a sniper POC `candidate` is a plan, not broker validation.
- Use `order list --symbol SYMBOL` to inspect current pending orders; do not rely only on the MT5 chart trade panel.
- Always branch on JSON `ok` before reading `data`.
- Never place a live-account order unless the user explicitly requests live trading and all three live gates are intentionally set.
- Use `mt5 --json ...` for machine-readable output.

## Common Commands

```powershell
mt5 config test
mt5 --json account info
mt5 --json account risk

mt5 market search --pattern EUR
mt5 --json market tick USDJPY
mt5 --json market depth USDJPY --levels 5

mt5 --json rates fetch USDJPY H1 --bars 100
mt5 --json indicator ema USDJPY H1 --period 20 --bars 100
mt5 --json indicator fvg USDJPY M15 --bars 300 --min-points 5 --state open --limit 20
mt5 --json analyze bias USDJPY
mt5 --json analyze sniper-poc USDJPY --direction auto
mt5 --json chart current
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json chart switch-tf H1
mt5 --json chart symbol USDJPY
mt5 --json chart depth-of-market USDJPY
mt5 --json chart dom USDJPY
mt5 --json screenshot tda USDJPY --timeframes D1,H4,H1,M15,M5,M1 --output-dir "$env:TEMP\mt5-cli\screenshots"
mt5 --json screenshot dom USDJPY --output-dir "$env:TEMP\mt5-cli\screenshots"

mt5 --json order dryrun USDJPY buy --volume 0.01 --sl 159.500
mt5 --json order list --symbol USDJPY
mt5 --json order market USDJPY buy --volume 0.01 --sl 159.500
mt5 --json order poll-fill TICKET

mt5 --json position list --symbol USDJPY
mt5 --json position close TICKET
mt5 --json position breakeven TICKET --buffer-points 5

mt5 --json history deals --from 2026-01-01 --to 2026-01-31 --symbol USDJPY
mt5 --json history stats --from 2026-01-01 --to 2026-01-31

mt5 kill-switch
mt5 kill-switch --yes
```

## Visual Top-Down Analysis

The screenshot TDA command drives the active MT5 chart through Win32 toolbar messages and captures one PNG per timeframe:

```powershell
mt5 --json screenshot tda USDJPY --timeframes D1,H4,H1,M15,M5,M1 --output-dir "$env:TEMP\mt5-cli\screenshots"
```

Output shape:

```json
{
  "ok": true,
  "data": {
    "symbol": "USDJPY",
    "captured_at": "2026-04-29T00:00:00+00:00",
    "frames": [
      {
        "tf": "D1",
        "path": "C:\\...\\USDJPY_D1_....png",
        "w": 1280,
        "h": 720,
        "structured_context": {
          "market_structure": {"support": 157.1, "resistance": 158.2},
          "fvg": {"zones": [{"visual_label": "BULL FVG OPEN 4.2p"}]},
          "liquidity": {"pools": [{"visual_label": "BSL LIQ OPEN C2 V100"}]}
        }
      }
    ],
    "visual_manifest": {"indicator_assets": {"EhukaiFVG": "C:\\...\\EhukaiFVG.mq5"}},
    "manifest_path": "C:\\...\\USDJPY_TDA_manifest_....json"
  }
}
```

The implementation is broker-agnostic. It defaults to matching the standard MT5 window class or a title containing `MT5`, uses the standard MT5 period toolbar, and writes only to `--output-dir`, `screenshot.output_dir`, legacy `screenshot_path`, or the OS temp directory (`%TEMP%\mt5-cli\screenshots` on Windows, `$TMPDIR/mt5-cli/screenshots` on POSIX). No broker-specific paths or project-specific paths are required.

Visual TDA returns the best of both worlds for agents. The PNGs show the MT5 chart exactly as the operator sees it, while the JSON manifest explains the vendored Ehukai indicator contract and attaches recomputed structure/FVG/liquidity data. The canonical MQ5 sources live in `metatrader5_cli/mt5/mql5/Indicators/`:

- `EhukaiFVG.mq5`: stable `EFVG_` objects, `BULL/BEAR FVG OPEN/PARTIAL/FILLED <pips>p` labels, rectangle boundaries, and dashed midlines.
- `EhukaiMarketStructure.mq5`: stable `EMS_` objects, `HH/HL/LH/LL` swing labels, `MS <TF>: ...` bias panel, BOS labels, and support/resistance levels.
- `EhukaiLiquiditySwings.mq5`: stable `ELS_` objects, `BSL/SSL LIQ OPEN/SWEPT C<count> V<volume>` labels, swing-high/swing-low liquidity rectangles, and dashed levels after sweep.
- `EhukaiTDAOverlay.mq5`: stable `ETDA_` objects and the recommended single chart overlay for screenshots. It composes structure, nearest FVGs, and nearest liquidity pools with low-noise defaults. In agent screenshot mode it filters oversized FVGs and distant liquidity pools so historic zones do not visually overpower actionable near-price context.

For live charts and screenshot agents, apply only `EhukaiTDAOverlay.mq5` by
default. Keep the primitive overlays above for debugging a single concept, but
do not stack them on normal TDA charts because labels and rectangles will
overlap.

Use `--no-context` when only screenshots are needed, and `--no-manifest` when a sibling JSON file should not be written.

For visual-TDA decisions, prefer the Ehukai-specific CLI commands so the data
matches the chart overlays:

```powershell
mt5 --json ehukai structure USDJPY M15
mt5 --json ehukai fvg USDJPY M15 --max-zones 4
mt5 --json ehukai liquidity USDJPY M5 --length 14
```

The older generic `analyze structure` and `indicator fvg` commands remain
available for raw strategy research, but `screenshot tda` now uses the Ehukai
context layer so agents are not choosing between duplicate interpretations.
Use `ehukai liquidity` as a liquidity-map layer: buy-side pools above swing
highs and sell-side pools below swing lows are targets/trap zones, not standalone
entry signals. Swept pools include both `swept_at` and `sweep_age_bars`, so
agents can separate a fresh stop-run from an old pivot.

For M1 sniper planning, use the non-mutating POC command after TDA/DOM context:

```powershell
mt5 --json analyze sniper-poc USDJPY --direction auto --max-spread-points 30 --min-rr 1.5 --min-stop-points 50 --max-sweep-age-bars 12 --max-fvg-age-bars 20 --max-entry-distance-pips 15
```

`analyze sniper-poc` combines Ehukai structure, FVG, liquidity sweeps, market depth when available, and current bid/ask quote rules. It returns either `status: "candidate"` with a suggested limit-order command for review/dry-run, or `status: "no_trade"` with failed gates. It explicitly models the execution side: buy limits fill on ask, sell limits fill on bid, so spread traps are rejected before a pending order is proposed. It also expands the SL to at least `--min-stop-points` so the plan is closer to what `order dryrun` and broker stop-distance rules will accept.

For autonomous placement, use the two commands returned in `setup.order_commands`
in order. The first command is the broker-side `order dryrun` for the pending
limit; only place the second command if dryrun returns `ok:true` and the setup
is still current. By default, sniper POC only accepts OPEN FVGs within
`--max-entry-distance-pips`, requires the enabling sweep within
`--max-sweep-age-bars`, rejects FX rollover (`21:00-22:59 UTC`), and resolves
auto-direction ties to `no_trade`. It uses faster Ehukai liquidity pivots on
M1/M5 (`length=5`) for sniper sweeps and the broader context default
(`length=14`) on M15+. Use `--summary` for agent loops that do not need the
full per-timeframe `frames` payload.

Use `chart current` and `chart ensure` to make the active chart explicit before any visual task:

```powershell
mt5 --json chart current
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json chart ensure USDJPY --timeframe none
```

`chart ensure` is symbol agnostic: it works with any broker-exact symbol that MT5 accepts in the active chart and any supported timeframe (`M1 M5 M15 M30 H1 H4 D1 W1 MN`). It is preferred over automating File > New Chart because broker menus and recent-symbol lists vary by terminal.

After the capture loop, TDA leaves the active chart on `M15` by default so the operator workspace returns to the normal working timeframe. This is configurable and broker-agnostic:

```powershell
mt5 --json screenshot tda USDJPY --final-timeframe M15
mt5 --json screenshot tda USDJPY --final-timeframe H1
mt5 --json screenshot tda USDJPY --final-timeframe none
```

## Depth of Market

Depth of Market has two useful CLI paths:

```powershell
# Structured Python API path, when the broker exposes market_book_* data
mt5 --json market depth USDJPY --levels 5

# GUI path, matching MT5 Charts > Depth Of Market
mt5 --json chart depth-of-market USDJPY
mt5 --json screenshot dom USDJPY --output-dir "$env:TEMP\mt5-cli\screenshots"
```

`market depth` is the canonical structured data command. `chart depth-of-market` opens the actual MT5 GUI panel from Charts > Depth Of Market, and `screenshot dom` captures that panel for visual agent review. By default `screenshot dom` closes/toggles the DOM panel after capture so it does not block the chart; pass `--no-close` only when intentionally inspecting the panel manually. DOM data availability depends on broker and symbol support, but the GUI panel can still be useful when the Python API returns `MT5_MARKET_BOOK_*` errors.

Agents should use DOM as a pre-entry liquidity check, not as a trading signal by itself:

- `best_bid`, `best_ask`, `spread`, and `spread_points` show whether the current top of book is tradable.
- `bids` and `asks` are sorted nearest-first and limited per side by `--levels`.
- `bid_volume`, `ask_volume`, and `volume_imbalance` summarize near-price pressure across the returned levels.
- `MT5_MARKET_BOOK_SUBSCRIBE_FAILED` and `MT5_MARKET_BOOK_UNAVAILABLE` mean the broker or symbol may not expose DOM; fall back to `market info`, `market tick`, and normal dry-run checks.

Validated behavior on this Trading.com demo terminal: visual TDA screenshots work, and the GUI DOM panel opens through Charts > Depth Of Market. The Python `market_book_add()` path currently returns `False` for USDJPY/EURUSD/GBPUSD, so agents should use `screenshot dom` for Trading.com GUI DOM context and treat `market depth` as opportunistic structured data.

TDA + DOM workflow:

```powershell
# 1. Capture chart context
mt5 --json screenshot tda USDJPY --timeframes H1,M15,M5 --output-dir "$env:TEMP\mt5-cli\tda"

# 2. Try structured book context
mt5 --json market depth USDJPY --levels 5

# 3. If depth returns MT5_MARKET_BOOK_* errors, capture the GUI DOM panel
mt5 --json screenshot dom USDJPY --output-dir "$env:TEMP\mt5-cli\dom"

# 4. Use tick/spread/dryrun for execution validation
mt5 --json market tick USDJPY
mt5 --json analyze sniper-poc USDJPY --direction auto --max-spread-points 30 --min-stop-points 50
mt5 --json order dryrun USDJPY buy --volume 0.01 --sl 159.500
```

Output shape:

```json
{
  "ok": true,
  "data": {
    "symbol": "USDJPY",
    "levels": 5,
    "best_bid": 157.890,
    "best_ask": 157.891,
    "spread_points": 1.0,
    "mid": 157.8905,
    "volume_imbalance": 0.14,
    "bids": [{"side": "bid", "price": 157.890, "volume_dbl": 20.0}],
    "asks": [{"side": "ask", "price": 157.891, "volume_dbl": 10.0}]
  }
}
```

## Python API

Agents can also import the core API directly:

```python
from metatrader5_cli.mt5.core import account, indicator, market, order, project, rates
from metatrader5_cli.mt5.utils import mt5_backend as bridge

cfg = project.load()
bridge.connect(
    cfg.get("login"),
    cfg.get("password"),
    cfg.get("server", ""),
    cfg.get("timeout", 10000),
)

info = account.info()
tick = market.tick("USDJPY")
depth = market.depth("USDJPY", levels=5)
bars = rates.fetch("USDJPY", "H1", bars=100)
ema = indicator.ema("USDJPY", "H1", period=20, bars=100)
dryrun = order.dryrun(
    "USDJPY",
    "buy",
    volume=0.01,
    sl=159.500,
    cfg=cfg,
    is_live_intent=False,
)
```

FVG output is zone-based, not loose-line based. Each gap owns its boundaries:

```json
{
  "type": "fvg",
  "direction": "bullish",
  "lower": 160.244,
  "upper": 160.264,
  "mid": 160.254,
  "size_points": 20,
  "state": "open",
  "boundaries": {
    "lower": {"price": 160.244, "role": "lower"},
    "upper": {"price": 160.264, "role": "upper"},
    "mid": {"price": 160.254, "role": "mid"}
  },
  "render": {"kind": "zone"}
}
```

## Verification

Unit suite:

```powershell
python -m pytest metatrader5_cli/mt5/tests/test_core.py -v
```

Live demo integration suite:

```powershell
$env:MT5_DEMO_INTEGRATION = "1"
python -m pytest metatrader5_cli/mt5/tests/test_e2e.py -v
```

The integration suite asserts the account is not real, performs a dry-run, places a 0.01-lot demo USDJPY order, confirms fill, closes it, and verifies history.
