# Agent Wake Alert Decision Spec

Status: Ready for merge
Date: 2026-06-04
Owner: metatrader5-cli maintainers
Related playground: [Agent Wake Alert Bridge](../playgrounds/specs/agent-wake-alert-bridge.html)

## Purpose

Define the reliable alert-seeded decision slice for agent workflows. MT5 alert
definitions are read as a watch-list, converted into structured `wake.v1`
decision records, optionally dry-run against the existing order-risk path, and
audited as JSONL. The watcher is non-mutating.

The agent remains responsible for scheduled market polling and any human-approved
trading command it chooses to run after inspecting live account and market state.

## Source Anchors

- CLI command: `mt5/cli.py` exposes `mt5 alert watch`.
- Alert source: `mt5_cli/alert/alert.py` reads `alerts.dat` and is read-only.
- Decision core: `mt5_cli/wake/wake.py` validates policies, dedupes records,
  writes audit logs, and calls `mt5_cli.orders.dryrun` when configured.
- Safety gates: `mt5_cli/orders/orders.py` preserves the existing dry-run and
  live-trade triple-lock behavior.
- Tests: `tests/test_alert.py`, `tests/test_wake.py`, and `tests/test_cli.py`.
- Agent contract docs: `README.md` and `AGENTS.md`.

## Durable Wedge

Six-month thesis: even if agent platforms improve their own scheduling and wake
features, this repo still owns the MT5-specific layer: structured terminal
state, broker/risk validation, policy limits, deterministic envelopes, local
dedupe, and an audit trail. Platform schedulers can call this slice; they do not
replace it.

Specific workflow: a trader or builder keeps MT5 alert definitions as a local
watch-list, lets an agent poll market/account state on a schedule, and uses this
tool to turn matching watch items into reviewable decision records before any
separate trading command is considered.

## Goals

- Keep MT5 alert handling read-only.
- Emit one structured JSON envelope for agent consumption.
- Validate wake policies before processing alert records.
- Support `notify_only`, `ask_permission`, and `auto_dryrun`.
- Run `order dryrun` only when an explicit policy trade template exists.
- Persist dedupe state so the same alert definition is not replayed forever.
- Write JSONL audit records for every emitted decision.
- Preserve the default MCP server as read and dry-run only.

## Non-Goals

- No alert creation or writes to `alerts.dat`.
- No confirmed MT5 fired-alert history detection.
- No direct wake integration for external runtimes or mobile push notifications.
- No live order placement from `mt5 alert watch`.
- No mutation-capable MCP surface.
- No trading strategy, signal generation, indicator logic, or market opinion.

## Architecture

The shipped slice has five steps:

1. `mt5 alert watch` reads terminal alert definitions through the existing
   read-only alert parser.
2. Each unseen alert record becomes a `wake.v1` event with a stable dedupe key.
3. The policy engine selects the first enabled matching policy, or the safe
   default `notify_only` policy when none matches.
4. If the policy is `ask_permission` or `auto_dryrun` and includes a valid trade
   template, the watcher calls the existing order dry-run function.
5. The watcher writes a `wake_audit.v1` JSONL record, saves dedupe state, and
   returns a `wake_watch.v1` envelope.

All terminal calls remain serialized by the caller. Tight loops should prefer a
single long-lived process or library calls over spawning parallel CLI processes.

## Command Contract

```bash
mt5 --json alert watch --once
mt5 --json alert watch --policy-path wake-policy.json --audit-path wake-audit.jsonl
```

Supported options:

- `--alerts-path`: override the alert file path.
- `--policy-path`: read wake policy JSON.
- `--state-path`: override dedupe state JSON.
- `--audit-path`: override audit JSONL.
- `--iterations`: bounded poll count.
- `--once`: alias for `--iterations 1`.
- `--poll-seconds`: delay between bounded iterations.
- `--live`: pass live intent to dry-run checks only; the watcher still does not
  send orders.

## Wake Watch Envelope

```json
{
  "ok": true,
  "data": {
    "schema": "wake_watch.v1",
    "count": 1,
    "policy_source": "file",
    "state_path": "C:/.../wake-state.json",
    "audit_path": "C:/.../wake-audit.jsonl",
    "alert_count": 1,
    "events": [
      {
        "schema": "wake.v1",
        "event_id": "wake-abcdef1234567890",
        "source": "mt5.alert",
        "symbol": "AUDUSD",
        "policy_id": "audusd-breakdown",
        "permission_mode": "auto_dryrun",
        "trigger": {
          "kind": "price",
          "condition": "Bid <",
          "price": 0.7186
        },
        "proposed_action": {
          "schema": "trade_intent.v1",
          "action": "place_market",
          "symbol": "AUDUSD",
          "side": "buy",
          "volume": 0.01,
          "sl": 0.7
        },
        "execution": {
          "decision": "dryrun_passed",
          "dryrun": {"ok": true, "data": {"dry_run": true}},
          "mutation": null
        }
      }
    ]
  }
}
```

Known failures use the repository envelope contract:

```json
{
  "ok": false,
  "error": {
    "code": "WAKE_POLICY_INVALID",
    "message": "Policy 'example' has invalid permission_mode 'unsupported'."
  }
}
```

## Policy Contract

```json
{
  "wake_policies": [
    {
      "id": "audusd-breakdown",
      "enabled": true,
      "match": {
        "source": "mt5.alert",
        "symbol": "AUDUSD",
        "condition": "Bid <"
      },
      "permission_mode": "auto_dryrun",
      "adapters": ["audit"],
      "limits": {
        "allowed_symbols": ["AUDUSD"],
        "max_volume": 0.02
      },
      "trade_template": {
        "schema": "trade_intent.v1",
        "action": "place_market",
        "side": "buy",
        "volume": 0.01,
        "sl": 0.7,
        "tp": 0.73
      }
    }
  ]
}
```

Supported `permission_mode` values:

- `notify_only`: emit and audit the wake; no dry-run.
- `ask_permission`: dry-run when a trade template exists; no mutation.
- `auto_dryrun`: dry-run automatically and stop.

Supported `adapters` values:

- `audit`
- `stdout`

The command always returns the envelope on stdout and writes the audit file. The
adapter list is retained only as explicit result metadata for those two shipped
sinks.

Supported trade template actions:

- `place_market`
- `place_limit`
- `place_stop`

Policy validation returns `WAKE_POLICY_INVALID` for unsupported permission modes,
adapters, actions, numeric fields, or malformed limits.

## Audit Log

Every emitted wake writes one compact JSONL record:

```json
{
  "schema": "wake_audit.v1",
  "event_id": "wake-abcdef1234567890",
  "policy_id": "audusd-breakdown",
  "permission_mode": "auto_dryrun",
  "decision": "dryrun_passed",
  "dryrun": {"ok": true, "data": {"dry_run": true}},
  "mutation": null,
  "adapters": [{"name": "audit", "ok": true, "mode": "jsonl"}]
}
```

The default audit and state files live in the user-local runtime directory, not
inside the repository.

## Error Codes

Implemented wake-specific errors:

- `WAKE_AUDIT_WRITE_FAILED`
- `WAKE_POLICY_INVALID`
- `WAKE_STATE_READ_ERROR`
- `WAKE_STATE_WRITE_FAILED`

Dry-run and limit failures reuse the existing `MT5_*` and `RISK_*` error codes.

## Acceptance Criteria

- `mt5 alert watch --json` emits a valid `wake_watch.v1` envelope and exits 0.
- Fixture-backed alert files can exercise the command without a live terminal.
- Duplicate alert definitions are deduped through persisted state.
- Unsupported permission modes and adapters fail policy validation.
- `ask_permission` and `auto_dryrun` never mutate.
- `--live` is passed only to dry-run checks.
- The default MCP server remains read and dry-run only.
- Tests cover policy validation, dedupe, audit output, dry-run execution, CLI
  option threading, and unsupported removed paths.
