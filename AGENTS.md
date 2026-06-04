# AGENTS.md — using metatrader5-cli from an agent

`metatrader5-cli` is built to be driven by LLM agents and autonomous workflows.
This file is the contract an agent needs to integrate reliably.

## The envelope contract

Every command emits one JSON envelope on **stdout** and **always exits 0**.
Parse the envelope; never branch on the exit code or read stderr.

```json
{ "ok": true,  "data": { ... } }
{ "ok": false, "error": { "code": "MT5_CONNECTION_ERROR", "message": "human text", "data": { ... } } }
```

- Branch on `ok`. On failure, branch on `error.code` (a stable string), not on
  `error.message` (human-facing, may change).
- `--json` works in **any position**: `mt5 --json market info EURUSD` and
  `mt5 market info EURUSD --json` are equivalent.
- An unexpected internal error still returns a valid envelope with
  `error.code = "MT5_INTERNAL_ERROR"` and exit 0 — the contract never breaks.

## Two ways to integrate

**1. Shell out to the CLI.** Spawn `mt5 --json <command>` and parse stdout.

```bash
mt5 --json status
mt5 --json market info EURUSD
mt5 --json rates fetch USDJPY H1 --bars 100
mt5 --json order dryrun EURUSD buy --volume 0.01 --sl 1.1600
mt5 --json position list
mt5 --json alert watch --once
```

**2. MCP server (recommended for LLM tool loops).**

```bash
pip install metatrader5-cli[mcp]
mt5-mcp        # runs an MCP server over stdio
```

Point any MCP client at it to get typed tools: `status`, `account_info`,
`account_risk`, `market_info`, `market_tick`, `market_search`, `rates_fetch`,
`rates_latest`, `history_deals`, `history_stats`, `position_list`,
`order_list_pending`, `order_dryrun`.

## Safety — read this before automating trades

- The MCP server exposes **read + dry-run only**. It cannot place, modify, or
  close live orders. Use `order_dryrun` to validate intent (margin, lot size,
  MT5 retcode) before a human or the CLI commits.
- Real-account mutations via the CLI require **all three** gates, by design:
  `cfg["live"] = true` **and** `MT5_LIVE=1` **and** the `--live` flag. Missing any
  one returns `RISK_LIVE_GATE_BLOCKED`.
- Demo and contest accounts bypass the live gate by design — but they are still
  live broker execution environments. Use tiny volume and explicit intent.
- `mt5 alert watch` is non-mutating decision/audit plumbing only in the first
  slice: it can emit `wake.v1` envelopes, ask for permission, run dry-runs, write
  audit logs, and return the decision envelope. It reads alert definitions as a
  watch-list and does not create alerts, detect confirmed fired-alert history, or
  send live orders. Agents that need real market-movement triggers should poll
  live market/account state on their own schedule and then call the trading CLI
  explicitly if policy and user permission allow it.

## Concurrency & latency

- Each `mt5 ...` invocation is a fresh OS process that connects to **one
  single-session** MT5 terminal. **Serialize your calls** — do not fan out many
  parallel `mt5` processes against the same terminal; they race the one handle.
- Each shell-out pays Python startup + a connect, so for tight loops prefer the
  MCP server (one long-lived process) or import the library directly
  (`from mt5_cli.market import info`) instead of spawning a process per call.

## Error codes you should handle

| Code | Meaning | Retryable? |
|------|---------|------------|
| `MT5_CONNECTION_ERROR` | Terminal not reachable | after (re)connect |
| `MT5_INVALID_PARAMS` | Bad arguments | no — fix the call |
| `MT5_INVALID_SYMBOL` | Unknown symbol | no |
| `MT5_NO_DATA` | No data for the request | maybe |
| `MT5_ORDER_REJECTED` | Broker rejected (see `error.data.mt5_retcode`) | depends on retcode |
| `MT5_TICKET_NOT_FOUND` | No such order/position ticket | no |
| `RISK_LIVE_GATE_BLOCKED` | Live gate not fully armed | no — arm all three gates |
| `RISK_*` (other) | A risk guard blocked the order | no — adjust the order |
| `MT5_INTERNAL_ERROR` | Unexpected internal error | maybe |

Run `mt5 <group> --help` for exact options of any command.
