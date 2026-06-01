---
name: Feature request
about: Suggest an idea
labels: ["enhancement"]
---

## Problem / use case

What are you trying to do, and where does the current tooling get in the way?
Describe the concrete scenario rather than the solution. If a specific CLI
command, library call, or MCP tool is involved, name it.

## Proposed solution

Describe what you would like to see. Be specific about the behavior, inputs, and
outputs. For example: a new `mt5` command or flag, a library function, an MCP
tool, or a change to an existing one. If it touches output, show the JSON
envelope shape you expect.

## Alternatives considered

What other approaches did you try or rule out? Workarounds with the existing
commands, external scripts, or other tools are all useful context. If you
checked `mt5 describe --json` for existing functionality, mention what you
found.

## Scope check

`metatrader5-cli` is intentionally **tool-only**: it controls a running
MetaTrader 5 terminal and exposes account, market, order, position, chart,
screenshot, MQL5, and Strategy Tester functionality. It ships **no trading
strategies, indicators, or signals**, and that is a deliberate boundary.

Please confirm your request fits that scope:

- [ ] This request is for tooling that controls or reads from the MT5 terminal,
      not for a trading strategy, indicator, or signal.

If your idea involves strategy or signal logic, it likely belongs in your own
project built on top of this library rather than in the library itself, but feel
free to open the issue to discuss.

## Additional context

Anything else that helps: platform notes (this project is Windows-only, Python
3.10+), related issues, or links. Please do not paste credentials, account
numbers, or screenshots that reveal your balance, equity, or broker login.
