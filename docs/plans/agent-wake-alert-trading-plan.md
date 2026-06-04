# Agent Wake Alert Trading Plan

Status: In progress
Date: 2026-06-03
Spec: [Agent Wake Alert Trading Spec](../specs/agent-wake-alert-trading.md)
Playground: [Agent Wake Alert Bridge](../playgrounds/specs/agent-wake-alert-bridge.html)

## Phase 1 - Read-Only Wake Events - Complete

- Added `mt5_cli.wake` with policy parsing, validation, dedupe, and audit helpers.
- Added `mt5 alert watch --once/--poll-seconds/--json`.
- Emitted wake envelopes from fixture-backed alert records.
- Added error codes for policy, state, audit, autonomous-block, and push-queue
  failures.
- Tests cover alert fixture watch, invalid policy, duplicate suppression, envelope
  shape, and no mutation path.

## Phase 2 - Notification Adapters - Partially Complete

- Add adapter interface with `notify(wake_event) -> envelope`.
- Future: implement `webhook` and full relay-backed `mt5_push` adapters.
- Added the MT5 push queue contract; the MQL5 relay template is still pending.
- Added relay message validation for the 255 character MQL5 notification limit.
- Tests already cover queue writes and message length. Future tests should cover
  adapter failure envelopes, HMAC signing, and rate-limit classification.

## Phase 2.5 - Confirmed Alert Fire Relay - Pending

- Add an MQL5 EA/service relay that records confirmed alert fire events and can
  create/update terminal alerts through validated terminal APIs.
- Keep direct writes to MT5 binary alert storage out of scope.
- Future tests: relay queue contract, fired-event dedupe, alert creation
  validation, and MT5 push notification handoff.

## Phase 3 - Agent Wake Adapters

- Add Codex adapter for recurring/thread wake integration where available.
- Add Claude Code adapter for CLI/session wake plus hook-safe handoff.
- Add Antigravity adapter for scheduled task/hook handoff.
- Keep adapter configuration explicit and disabled by default.
- Future tests: adapter command construction, disabled adapter behavior, payload
  redaction, and failure isolation.

## Phase 4 - Permissioned Trade Execution - Partially Complete

- Added trade intent validation and policy-bound templates.
- Added `ask_permission`, `auto_dryrun`, and blocked `auto_trade` execution
  states.
- Require dry-run before mutation.
- For real accounts, preserve the existing triple live gate and require daemon
  live intent.
- Tests already cover ask-permission no-mutation behavior, auto dry-run stops,
  and blocked auto-trade. Future tests should cover approval expiry, any live
  mutation handoff, and the real-account live gate matrix.

## Phase 5 - MCP Surface Decision

- Decide whether live mutation belongs in a separate opt-in MCP server or remains
  CLI/library-only.
- If MCP mutation is accepted, ship it as a separate explicitly armed surface
  with a different tool name, strong warnings, and tests proving the default
  `mt5-mcp` surface remains read and dry-run only.

## Verification Gate

Run before opening the implementation PR:

```bash
ruff check .
pytest -m "not integration"
```

Run integration checks only when terminal-facing behavior changes and a live MT5
terminal is available.
