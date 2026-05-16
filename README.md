# metatrader5-cli

A pip-installable tool that gives AI agents and humans hands to MetaTrader 5.

## Status

Under active refactor. The CLI is being rebuilt under `mt5_cli/`. The
previous CLI is preserved at `archive/legacy-mt5/` as cherry-pick reference
only. There is no working CLI on this branch yet.

## What this is (when shipped)

A pip-installable harness that lets AI agents and humans control MetaTrader 5
from their own external workspace. It provides:

- `mt5` — a CLI for shell use and scripts
- `mt5-mcp` — an MCP server for AI agents (Claude Code, Cursor, etc.)
- `mt5_cli` — a Python library for direct programmatic use

You install once. Your MQL5 EAs, indicators, `.set` presets, and tester results
live in YOUR project directory, never in this repo.

## Documentation

- [docs/specs/2026-05-15-mt5-universal-agent-native-design.md](docs/specs/2026-05-15-mt5-universal-agent-native-design.md) — design spec
- [docs/specs/2026-05-15-mt5-universal-review-context.md](docs/specs/2026-05-15-mt5-universal-review-context.md) — reviewer context (locked decisions, scope rules)
- [docs/plans/2026-05-15-mt5-universal-agent-native.md](docs/plans/2026-05-15-mt5-universal-agent-native.md) — implementation plan
- [docs/playgrounds/mt5-universal-refactor-playground.html](docs/playgrounds/mt5-universal-refactor-playground.html) — interactive visual companion