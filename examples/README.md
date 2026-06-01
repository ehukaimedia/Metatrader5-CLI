# Examples

Runnable examples that show how to drive `metatrader5-cli` from your own code.

Everything in this directory is **read-only or dry-run**. The examples inspect
account, market, and position state and validate order intent with
`order dryrun` — they never place, modify, or close a live order.

## Requirements

- Windows with MetaTrader 5 installed and Python 3.10+.
- `metatrader5-cli` installed (see the project [README](../README.md)).
- A **running** MetaTrader 5 terminal, logged in to the account you want to
  inspect. The examples talk to a live terminal; without one they return a
  connection error envelope.

## Running an example

```bash
python examples/agent_loop.py
```

`agent_loop.py` is a small, read-only agent loop: it polls terminal and account
state and validates order intent with a dry run, parsing each command's JSON
envelope (it branches on the envelope's `ok` field, never on the exit code).

## Going further

For the full agent integration contract — the envelope shape, error-code
handling, the three live-trade safety gates, and the optional MCP server — see
[../AGENTS.md](../AGENTS.md).
