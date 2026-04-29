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
mt5 --json analyze topdown USDJPY --timeframes D1,H4,H1
mt5 --json screenshot tda USDJPY --timeframes D1,H4,H1,M15,M5,M1 --output-dir "$env:TEMP\mt5-cli\screenshots"
mt5 --json order dryrun USDJPY buy --volume 0.01 --sl 159.500
mt5 --json order market USDJPY buy --volume 0.01 --sl 159.500
mt5 --json position list --symbol USDJPY
```

Rules for agents:

- Always run `market search --pattern SYMBOL` first.
- Always run `order dryrun` before `order market`, `order limit`, or `order stop`.
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

mt5 --json rates fetch USDJPY H1 --bars 100
mt5 --json indicator ema USDJPY H1 --period 20 --bars 100
mt5 --json indicator fvg USDJPY M15 --bars 300 --min-points 5 --state open --limit 20
mt5 --json analyze bias USDJPY
mt5 --json chart switch-tf H1
mt5 --json chart symbol USDJPY
mt5 --json screenshot tda USDJPY --timeframes D1,H4,H1,M15,M5,M1 --output-dir "$env:TEMP\mt5-cli\screenshots"

mt5 --json order dryrun USDJPY buy --volume 0.01 --sl 159.500
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
      {"tf": "D1", "path": "C:\\...\\USDJPY_D1_....png", "w": 1280, "h": 720}
    ]
  }
}
```

The implementation is broker-agnostic. It defaults to matching the standard MT5 window class or a title containing `MT5`, uses the standard MT5 period toolbar, and writes only to `--output-dir`, `screenshot.output_dir`, legacy `screenshot_path`, or the OS temp directory (`%TEMP%\mt5-cli\screenshots` on Windows, `$TMPDIR/mt5-cli/screenshots` on POSIX). No broker-specific paths or project-specific paths are required.

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
