# Agent Wake Alert Trading Plan

Status: Proposed
Date: 2026-06-03
Spec: [Agent Wake Alert Trading Spec](../specs/agent-wake-alert-trading.md)
Playground: [Agent Wake Alert Bridge](../playgrounds/specs/agent-wake-alert-bridge.html)

## Phase 1 - Read-Only Wake Events

- Add `mt5_cli.wake` with policy parsing, validation, dedupe, and audit helpers.
- Add `mt5 alert watch --once/--poll-seconds/--json`.
- Emit `wake.v1` envelopes from fixture-backed alert records.
- Add error codes for policy, dedupe, and audit failures.
- Tests: alert fixture watch, invalid policy, duplicate suppression, envelope
  shape, and no mutation path.

## Phase 2 - Notification Adapters

- Add adapter interface with `notify(wake_event) -> envelope`.
- Implement `webhook` and `mt5_push` adapters first.
- Add MQL5 notification relay template and queue contract.
- Add relay message validation for the 255 character MQL5 notification limit.
- Tests: adapter failure envelopes, HMAC signing, queue writes, message length,
  and rate-limit classification.

## Phase 3 - Agent Wake Adapters

- Add Codex adapter for recurring/thread wake integration where available.
- Add Claude Code adapter for CLI/session wake plus hook-safe handoff.
- Add Antigravity adapter for scheduled task/hook handoff.
- Keep adapter configuration explicit and disabled by default.
- Tests: adapter command construction, disabled adapter behavior, payload
  redaction, and failure isolation.

## Phase 4 - Permissioned Trade Execution

- Add trade intent validation and policy-bound templates.
- Add `ask_permission`, `auto_dryrun`, and `auto_trade` execution states.
- Require dry-run before mutation.
- For real accounts, preserve the existing triple live gate and require daemon
  live intent.
- Tests: ask blocks mutation, approval expiry, auto dry-run stops before
  mutation, auto trade calls existing order/position functions only after dry-run,
  and real-account live gate matrix.

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
