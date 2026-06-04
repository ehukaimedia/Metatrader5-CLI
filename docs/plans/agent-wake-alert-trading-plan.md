# Agent Wake Alert Decision Plan

Status: Ready for merge
Date: 2026-06-04
Spec: [Agent Wake Alert Decision Spec](../specs/agent-wake-alert-trading.md)
Playground: [Agent Wake Alert Bridge](../playgrounds/specs/agent-wake-alert-bridge.html)

## Implemented Slice

- Added `mt5_cli.wake` for policy parsing, validation, dedupe state, audit logs,
  wake envelopes, and optional dry-run decisions.
- Added `mt5 alert watch` with bounded polling, `--once`, policy/state/audit path
  controls, and dry-run-only `--live` threading.
- Added `wake.v1`, `wake_watch.v1`, and `wake_audit.v1` records.
- Added validation for supported permission modes, supported adapters, supported
  trade template actions, numeric fields, allowed symbols, and max volume.
- Preserved the non-mutating boundary: `mt5 alert watch` can notify, ask, or
  dry-run, but it never places, modifies, cancels, or closes trades.
- Kept the default MCP server read and dry-run only.
- Updated the README, AGENTS contract, changelog, spec, plan, and playground to
  describe only the shipped behavior.

## Unsupported Boundaries

- Autonomous trade permission mode.
- Mobile-notification queue code.
- Direct external runtime wake adapters.
- Alert creation or writes to MT5's binary alert store.
- Confirmed fired-alert history detection.
- Any mutation path inside `mt5 alert watch`.

Unsupported modes and adapters now fail policy validation instead of flowing into
blocked or placeholder runtime paths.

## Verification Gate

Run before merge:

```bash
ruff check .
pytest -m "not integration"
mypy mt5_cli mt5 mt5_mcp
git diff --check
```

Run terminal-facing integration checks only when a live MT5 terminal is available
and the change touches real terminal behavior.
