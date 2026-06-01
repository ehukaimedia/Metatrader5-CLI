# metatrader5-cli

`metatrader5-cli` is a Python library and command-line tool for controlling
MetaTrader 5 from scripts, terminals, and agent workflows.

It gives automation "hands" for MT5: account and market data, order and
position management, chart control, screenshots, MQL5 compile/deploy helpers,
and the native MT5 Strategy Tester.

The project is intentionally tool-only. It does not ship trading strategies,
indicator calculations, signal logic, or market opinions.

## Features

- Connect to a running MetaTrader 5 terminal.
- Read account, market, rates, history, and risk state.
- Place, modify, cancel, and dry-run orders with safety gates.
- Manage positions, stop losses, and break-even moves.
- Control MT5 charts and capture screenshots.
- Scaffold, compile, deploy, and discover user-authored MQL5 EAs and
  indicators.
- Run MT5's native Strategy Tester from a CLI envelope and parse results into
  JSON.

Every command supports `--json`. CLI invocations exit with status code `0`; the
result envelope's `ok` field carries success or failure.

## Requirements

- Windows with MetaTrader 5 installed.
- Python 3.10+.
- A configured MT5 terminal, usually already logged in to the broker account
  you want to inspect or control.

The current broker profile is Trading.com. Multi-broker abstractions are not
part of the current public surface.

## Install

```bash
git clone https://github.com/ehukaimedia/Metatrader5-CLI.git
cd Metatrader5-CLI
pip install -e .
```

The install registers the `mt5` console command.

## Quickstart

Run these from a normal shell while MetaTrader 5 is open and logged in:

```bash
mt5 --help
mt5 --json status
mt5 --json market info EURUSD
mt5 --json rates fetch USDJPY H1 --bars 10
mt5 --json order dryrun EURUSD buy --volume 0.01 --sl 1.1600
mt5 --json position list
mt5 --json chart list
mt5 --json screenshot take
```

Example JSON shape:

```json
{
  "ok": true,
  "data": {}
}
```

Failures use the same envelope style:

```json
{
  "ok": false,
  "error": {
    "code": "MT5_CONNECTION_ERROR",
    "message": "Could not connect to MT5"
  }
}
```

## Agents & MCP

`metatrader5-cli` is built for agentic workflows. Every command emits a JSON
envelope on stdout and always exits `0` — agents parse `ok`, never the exit code
— and `--json` works in any position.

Two integration paths:

1. **Shell out to the CLI:** run `mt5 --json <command>` and parse the envelope.
2. **MCP server (recommended for LLM agents):** install the extra and point any
   MCP client at the `mt5-mcp` server.

   ```bash
   pip install metatrader5-cli[mcp]
   mt5-mcp        # stdio MCP server
   ```

   It exposes typed read and dry-run tools (`status`, `account_*`, `market_*`,
   `rates_*`, `history_*`, `position_list`, `order_list_pending`,
   `order_dryrun`). For safety, **live-money mutations are not exposed over
   MCP** — those stay behind the CLI's explicit triple-lock below.

See [AGENTS.md](AGENTS.md) for the full contract, error-code table, and
copy-paste examples.

## Safety

Demo accounts are still live broker execution environments, even when the funds
are not real. Treat every mutating command with live-trading discipline.

Real-account trading requires all three gates:

- `cfg["live"]` is `true`
- `MT5_LIVE=1` is set
- the CLI command includes `--live`

Demo and contest accounts bypass the real-account triple lock by design, but
mutation smoke tests should still use tiny volume, explicit intent, and final
checks for open positions and pending orders.

Useful safety commands:

```bash
mt5 --json position list
mt5 --json order list-pending
mt5 --json order dryrun AUDUSD buy --volume 0.01 --sl 0.7000
```

## Configuration

The default config file is:

```text
~/.config/metatrader5-cli.json
```

Set `MT5_CONFIG` to point at a different config file.

The Trading.com defaults include broker-specific behavior such as FOK filling,
no hedging, 22:00 UTC rollover handling, and retcode help text.

## User Workspace

Install the tool once, then run `mt5` from your own trading project. User EAs,
indicators, presets, and tester results live outside this repository.

```text
my-trading-project/
  ea/
    my_strategy.mq5
    my_strategy.ex5
  indicators/
    my_signal.mq5
  presets/
    my_strategy.set
  results/
  .metatrader5-cli.json
```

Discovery order for EAs and indicators:

1. `./ea` or `./indicators` in the current working directory.
2. `~/.local/share/metatrader5-cli/ea` or `~/.local/share/metatrader5-cli/indicators`.

First match wins.

## MQL5 Helpers

Create, compile, list, and deploy user-owned MQL5 files:

```bash
mt5 --json ea new my_strategy
mt5 --json ea compile my_strategy
mt5 --json ea deploy my_strategy
mt5 --json ea list

mt5 --json indicator new my_signal
mt5 --json indicator compile my_signal
mt5 --json indicator deploy my_signal
mt5 --json indicator list
```

The included templates are minimal skeletons only. Trading logic belongs to the
user's MQL5 source files.

## Strategy Tester

The tester commands wrap MT5's native Strategy Tester. This is not a separate
Python backtester and not a fully headless server API.

EA tester runs use MT5's `/config` startup contract. The terminal must be
available for a fresh batch-mode launch; if `terminal64.exe` is already running,
the CLI returns `TERMINAL_ALREADY_RUNNING` rather than running against stale UI
state.

```bash
mt5 --json tester ea single \
  --expert my_strategy \
  --symbol AUDUSD \
  --tf M5 \
  --from 2024-01-01 \
  --to 2024-06-30 \
  --modelling ohlc-1m

mt5 --json tester ea optimize \
  --expert my_strategy \
  --symbol AUDUSD \
  --tf M5 \
  --from 2024-01-01 \
  --to 2024-06-30 \
  --mode genetic \
  --param Risk=1.0 \
  --param FastPeriod=9,5,1,21

mt5 --json tester list
mt5 --json tester show <run-id>
```

Tester reports are copied into the user's `results/<run-id>/` snapshot when MT5
produces them.

## Command Groups

| Group | Purpose |
|-------|---------|
| `connect`, `status` | Connect and inspect terminal/account state |
| `account` | Account info, balance, and risk snapshot |
| `market` | Symbol info, ticks, depth, search, sessions |
| `rates` | OHLCV and tick history |
| `order` | Market, limit, stop, dry-run, modify, cancel, poll fills |
| `position` | List, close, move stop loss, break-even |
| `history` | Orders, deals, stats |
| `alert` | List MT5 terminal alerts |
| `chart` | MT5 chart/window control |
| `screenshot` | Capture and annotate MT5 screenshots |
| `config` | Show effective config and retcode help |
| `ea` | MQL5 Expert Advisor scaffold, compile, deploy, discovery |
| `indicator` | MQL5 custom indicator scaffold, compile, deploy, discovery |
| `tester` | MT5 Strategy Tester runs, listing, and result parsing |

Run `mt5 <group> --help` or `mt5 <group> <command> --help` for exact options.

