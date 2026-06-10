# metatrader5-cli

[![CI](https://github.com/ehukaimedia/Metatrader5-CLI/actions/workflows/ci.yml/badge.svg)](https://github.com/ehukaimedia/Metatrader5-CLI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

`metatrader5-cli` is a Python library and command-line tool for controlling
MetaTrader 5 from scripts, terminals, and agent workflows.

**Who it's for:** developers and AI agents that need reliable, safety-gated
"hands" on an MT5 terminal — without a strategy or opinion baked in.

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

The data, chart, screenshot, and Strategy Tester commands are broker-agnostic
and work against any MT5 terminal. Order placement ships with a Trading.com
profile (FOK filling, no hedging); for other brokers, set `filling` in your
config or pass `--filling` explicitly.

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
copy-paste examples, and [`examples/`](examples/) for a runnable agent loop.

## Use as a library

The same surface is importable — no subprocess needed:

```python
from mt5_cli.bridge import connect
from mt5_cli.market import info

connect()              # zero-config: attaches to the running terminal
print(info("EURUSD"))  # {"ok": True, "data": {"bid": ..., "ask": ...}}
```

Library functions return the same `{ok, data}` / `{ok, error}` envelopes the
CLI emits, and `import mt5_cli; mt5_cli.__version__` reports the version.

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

Alert decision records are a policy-first way to turn MT5 alert definitions into
an agent-readable watch-list. The reliable first slice emits `wake.v1` envelopes,
writes JSONL audit records, dedupes repeated alert definitions, and can run
`order dryrun` from a configured trade template. It does **not** send live
orders, create alerts, or detect that an MT5 alert fired. Use the agent's own
scheduler to poll live market/account state and compare it to the conditions
read from `mt5 alert list`.

```bash
mt5 --json alert watch --once
mt5 --json alert watch --policy-path wake-policy.json --audit-path wake-audit.jsonl
```

**Screenshot privacy:** `mt5 screenshot take` captures the MT5 window as-is,
which can include your account balance, equity, and broker login number. Review
captures before sharing them with an agent, an LLM, or a public issue.

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

mt5 --json tester ea stress \
  --expert my_strategy \
  --symbol AUDUSD \
  --tf M5 \
  --from 2024-01-01 \
  --to 2024-06-30 \
  --delays 0,100,500,random

mt5 --json tester list
mt5 --json tester show <run-id>
```

`tester ea stress` runs the same EA across an execution-delay ladder — ideal
fills, fixed latencies, and MT5's randomized delay — using the native
`ExecutionMode` tester setting. Each rung is a full backtest cached under its own
`results/<run-id>/`. The `stress.v1` envelope grades execution robustness as the
worst-case profit retention versus the ideal baseline: `robustness.verdict` is
`robust` (score ≥ 0.85), `degraded` (≥ 0.50), `fragile` (< 0.50), or `ungraded`
(no positive baseline to measure against). Delays are comma-separated
millisecond integers from `0` to `600000` and/or `random`; the ideal baseline
`0` is always included.

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
| `alert` | List MT5 terminal alerts and emit wake decisions |
| `chart` | MT5 chart/window control |
| `screenshot` | Capture and annotate MT5 screenshots |
| `config` | Show effective config and retcode help |
| `describe` | Machine catalog of commands + error codes (for agents) |
| `ea` | MQL5 Expert Advisor scaffold, compile, deploy, discovery |
| `indicator` | MQL5 custom indicator scaffold, compile, deploy, discovery |
| `tester` | MT5 Strategy Tester runs, listing, and result parsing |

Run `mt5 <group> --help` or `mt5 <group> <command> --help` for exact options,
or `mt5 --json describe` for a machine-readable catalog of every command.

## Troubleshooting

- **`MT5_CONNECTION_ERROR` / "Could not connect to MT5":** make sure the
  MetaTrader 5 terminal is running and logged in. The CLI attaches to the
  already-open terminal; it does not launch one for data commands.
- **`TERMINAL_ALREADY_RUNNING` (tester):** an EA tester run needs a fresh
  batch-mode launch — close the running `terminal64.exe` first.
- **`mt5 ea list` finds nothing:** EAs/indicators are discovered from `./ea` or
  `./indicators` in the current directory, then
  `~/.local/share/metatrader5-cli/...`. Run from your trading project, or place
  files in one of those locations.
- **Non-Windows `pip install` fails:** the `MetaTrader5` dependency ships
  Windows wheels only. This tool is Windows-only by design.

## Disclaimer

This software can place, modify, and close **real broker orders that can lose
real money**. It is provided "as is", without warranty of any kind, and is **not
financial advice**. You are solely responsible for any orders placed on your
behalf. Test on a demo account first, and keep the live-trade gates closed until
you have verified your workflow.

## Trademark

"MetaTrader" and "MT5" are trademarks of MetaQuotes Ltd. This project is an
independent, community tool and is not affiliated with, endorsed by, or
sponsored by MetaQuotes.

## License

[MIT](LICENSE) © ehukaimedia.

