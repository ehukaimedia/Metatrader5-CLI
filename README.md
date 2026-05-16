# metatrader5-cli

A pip-installable tool that gives AI agents and humans hands to MetaTrader 5.

## Status

- **Phase 2 complete** — `mt5_cli/` library shipped (bridge, market, rates,
  orders, positions, account, history, risk, config, reports, chart,
  screenshot). 240+ unit tests, bridge singleton enforced.
- **Phase 3a complete** (tag `phase-3a-complete` at `854f9dd`) — `mt5` CLI
  shipped with 11 command groups wrapping the library. Three Codex review
  cycles closed (11 findings resolved). 367 pytest passing.
  Verified end-to-end against live Trading.com demo (24/24 commands).
- **Phase 3b in progress** — MQL5 plugin host (compiler, deployer,
  discovery, scaffold templates for user EAs/indicators).
- **Phase 4 TODO** — Strategy Tester driver.
- **Phase 5 TODO** — `mt5-mcp` MCP server (FastMCP).
- **Phase 6 TODO** — full XDG/APPDATA path resolution + portability tests.

## Install

```bash
git clone https://github.com/ehukaimedia/Metatrader5-CLI.git
cd Metatrader5-CLI
pip install -e .
```

The `mt5` console script is registered automatically.

## Quickstart

Run with a Trading.com MT5 terminal already open and logged in:

```bash
mt5 --help                                  # list all 13 command groups
mt5 status                                  # account + connection summary
mt5 --json market info EURUSD               # symbol info (JSON for agents)
mt5 rates fetch USDJPY H1 --bars 10         # recent OHLCV bars
mt5 chart list                              # enumerate open charts
mt5 chart new EURUSD --timeframe M15        # File > New Chart > EURUSD
mt5 order dryrun EURUSD buy --volume 0.01 --sl 1.1600   # validate without placing
mt5 screenshot take                          # capture the active MT5 window
```

Every command supports `--json` for parseable envelopes. Exit code is
always 0; success/failure lives in the envelope's `ok` field.

## Configuration

Config lives at `~/.config/metatrader5-cli.json` (override via `MT5_CONFIG`
env var). Trading.com is the current single-broker scope (FOK filling,
no hedging, 22:00 UTC rollover). Multi-broker support is a future task.

Live trading requires all three: `cfg["live"]: true` + `MT5_LIVE=1` env
+ `--live` CLI flag. DEMO and CONTEST accounts bypass the triple lock
by design.

## User workspace layout

`metatrader5-cli` is a tool — you install it once and run `mt5` from your
own project directory. Your MQL5 EAs, indicators, `.set` presets, and
tester results live in YOUR project, never in this repo:

```
my-trading-project/
├── ea/                       # your MQL5 Expert Advisors
│   ├── my_strategy.mq5
│   └── my_strategy.ex5       # built by `mt5 ea compile my_strategy`
├── indicators/               # your MQL5 indicators
│   └── my_signal.mq5
├── presets/                  # tester .set files (Phase 4)
├── results/                  # tester run snapshots (Phase 4)
└── .metatrader5-cli.json     # optional per-project config override
```

`mt5` discovers EAs/indicators in this order: `./ea` / `./indicators`
(CWD) → `~/.local/share/metatrader5-cli/{ea,indicators}/`
(XDG_DATA_HOME convention; `%APPDATA%/metatrader5-cli/` on Windows).
First match wins.

You can also keep your EAs and indicators centrally under
`~/.local/share/metatrader5-cli/` and run `mt5` from anywhere. The tool
ships only minimal MQL5 skeletons (`ea_minimal.mq5`,
`indicator_minimal.mq5`); the strategy / calculation logic is yours to
author. See [mt5_cli/skills/USER_WORKSPACE.md](mt5_cli/skills/USER_WORKSPACE.md)
for the full resolution chain.

## Command groups

| Group | Commands |
|-------|----------|
| `connect` / `status` | explicit (re)connect + account snapshot |
| `account` | `info`, `balance`, `risk` |
| `market` | `info`, `tick`, `depth`, `search`, `sessions` |
| `rates` | `fetch`, `latest`, `ticks` |
| `order` | `market`, `limit`, `stop`, `dryrun`, `list-pending`, `cancel`, `modify`, `cancel-all`, `poll-fill` |
| `position` | `list`, `close`, `close-all`, `move-sl`, `breakeven` |
| `history` | `orders`, `deals`, `stats` (with `--from` / `--to` date filters) |
| `chart` | `find-window`, `list`, `current-title`, `switch-tf`, `symbol`, `ensure`, `new`, `close`, `cycle`, `attach`, `attach-ea` |
| `screenshot` | `take`, `dom`, `annotate`, `list` |
| `config` | `show`, `retcode` |
| `ea` | `new`, `list`, `compile`, `deploy` (MQL5 Expert Advisor authoring — Phase 3b) |
| `indicator` | `new`, `list`, `compile`, `deploy` (MQL5 custom indicator authoring — Phase 3b) |

## Documentation

- [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](docs/specs/2026-05-15-mt5-universal-agent-native-design.md) — design spec
- [docs/specs/2026-05-15-mt5-universal-review-context.md](docs/specs/2026-05-15-mt5-universal-review-context.md) — reviewer context (locked decisions, scope rules)
- [docs/plans/2026-05-15-mt5-universal-agent-native.md](docs/plans/2026-05-15-mt5-universal-agent-native.md) — implementation plan
- [docs/playgrounds/mt5-universal-refactor-playground.html](docs/playgrounds/mt5-universal-refactor-playground.html) — interactive visual companion
- [docs/code-reviews/](docs/code-reviews/) — Codex review files (each phase has its own)
