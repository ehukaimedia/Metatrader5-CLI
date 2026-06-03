# Agent Wake Alert Trading Spec

Status: Partially implemented - first wake slice
Date: 2026-06-03
Owner: metatrader5-cli maintainers
Related playground: [Agent Wake Alert Bridge](../playgrounds/specs/agent-wake-alert-bridge.html)

## Purpose

Define the architecture for turning MetaTrader 5 alerts and market events into
agent wakes for Codex, Claude Code, and Google Antigravity, with user-configured
permission modes that can range from notification-only to fully autonomous trade
execution.

This spec is contract-first. The first implementation slice ships bounded
`mt5 alert watch` wake envelopes, policy matching, dedupe state, audit logging,
dry-run decisions, and an MT5 push relay queue. Live mutation tools remain
future work.

## Current Source Anchors

- `mt5 alert list` reads `alerts.dat`; `mt5 alert watch` turns those records
  into wake decisions:
  `mt5/cli.py`, `mt5_cli/alert/alert.py`, `mt5_cli/wake/wake.py`,
  `tests/test_alert.py`, and `tests/test_wake.py`.
- The first slice treats alert records as wake candidates. Confirmed fired-alert
  capture and alert creation require the future MQL5 relay/service path instead
  of writing directly to MT5's binary alert file.
- The alert parser is explicitly read-only because the binary alert record layout
  has not been round-trip validated for writes: `mt5_cli/alert/alert.py`.
- The MCP server currently exposes read and dry-run tools only:
  `mt5_mcp/server.py`.
- Real-account mutation is already guarded in the library by the triple live
  gate: caller live intent, `cfg["live"] = true`, and `MT5_LIVE=1`, as enforced
  by `mt5_cli/orders/orders.py` and `mt5_cli/positions/positions.py`.
- CLI output uses the existing JSON envelope contract and always exits 0:
  `mt5/cli.py`, `README.md`, and `AGENTS.md`.

## External Source Anchors

- Codex Automations can run scheduled tasks and return to the same conversation;
  local automations work best when the laptop is awake and Codex is running:
  https://openai.com/academy/codex-automations/
- Claude Code hooks are lifecycle handlers that can run shell commands, HTTP
  endpoints, prompts, or agents, and can make permission decisions:
  https://code.claude.com/docs/en/hooks
- Google Antigravity documents hooks, scheduled tasks, permissions, and CLI
  notifications:
  https://antigravity.google/docs/hooks
  https://antigravity.google/docs/cli-reference
- MQL5 `SendNotification()` sends push notifications to mobile terminals whose
  MetaQuotes IDs are configured in the desktop terminal, has a 255 character
  message limit, is rate-limited, and does not work in the Strategy Tester:
  https://www.mql5.com/en/docs/network/sendnotification
- MetaTrader terminal alerts can also use a `Notification` action to send push
  notifications through the MT5 mobile app:
  https://www.mql5.com/en/articles/476

## Durable Wedge

Six-month thesis: even if Codex, Claude Code, Antigravity, and MetaTrader each
ship stronger native scheduling or notification features, this project remains
useful because it owns the domain-specific contract between MT5, risk gates,
agent permission modes, and broker execution. Platform schedulers can improve
without replacing the need for a local, auditable, MT5-aware bridge.

Specific painful workflow: traders and builders who already use LLM agents need
MT5 events to wake an agent, inspect current account state, optionally dry-run or
place a trade, and leave a machine-readable audit trail without scraping terminal
UI text or bypassing broker/risk controls.

Dogfoodable first slice: a bounded wake command that observes MT5 alert records
as wake candidates, emits `wake.v1` envelopes, writes audit logs, queues MT5
mobile push relay requests, and provides an agent prompt for `ask_permission`
mode.

## Goals

- Provide a common wake event contract for Codex, Claude Code, Antigravity, and
  future adapters.
- Let users configure per-rule permission behavior:
  `notify_only`, `ask_permission`, `auto_dryrun`, or `auto_trade`.
- Allow agents to place, modify, cancel, or close trades after a wake only when
  the configured policy and existing risk gates allow it.
- Preserve the existing safety posture: read and dry-run over MCP by default,
  explicit opt-in for mutations, and structured envelopes everywhere.
- Support MT5 mobile push notifications as a first-class notification sink.
- Keep calls serialized against a single MT5 terminal session.

## Non-Goals

- No trading strategy, signal generation, or market opinion is added by this
  feature.
- No blind mutation of `alerts.dat` for outbound messages.
- No direct bypass of existing order or position risk gates.
- No guarantee that a sleeping laptop, closed terminal, or disconnected agent
  will wake reliably.
- No live mutation through the default MCP server unless a future spec introduces
  a separate, explicitly armed mutation server or mutation mode.

## Architecture

The target system has five layers:

1. `mt5 alert watch` or `mt5-alertd` detects MT5 terminal alerts, market
   conditions, or strategy-supplied signal files.
2. The wake normalizer emits one `wake.v1` envelope per deduped event.
3. The policy engine resolves the matching user rule and produces an action
   plan: notify, ask, dry-run, or trade.
4. The adapter layer wakes Codex, Claude Code, Antigravity, a webhook, and/or the
   MT5 mobile notification bridge.
5. The executor calls existing `mt5_cli.orders` and `mt5_cli.positions`
   functions only after dry-run and policy checks pass.

All MT5 calls must be serialized through one process-owned bridge handle. A wake
daemon should prefer library calls over spawning a new `mt5` process for every
poll.

## Wake Event Contract

The daemon emits one JSON envelope on stdout and to the audit log:

```json
{
  "ok": true,
  "data": {
    "schema": "wake.v1",
    "event_id": "01J...",
    "dedupe_key": "terminal:login:source:symbol:condition:price:timestamp",
    "source": "mt5.alert",
    "observed_at": "2026-06-03T00:00:00Z",
    "terminal": {
      "data_path": "C:/Users/.../Terminal/<hash>",
      "server": "broker-server"
    },
    "account": {
      "login": 123456,
      "trade_mode": "demo"
    },
    "symbol": "EURUSD",
    "trigger": {
      "kind": "price",
      "condition": "Bid <",
      "price": 1.08,
      "source_text": "alert"
    },
    "policy_id": "eurusd-breakdown-ask",
    "permission_mode": "ask_permission",
    "proposed_action": null
  }
}
```

Failure envelopes use the existing `{ok: false, error: {code, message, data?}}`
shape and still exit 0 for CLI commands.

## Trade Intent Contract

A wake may carry a proposed trade intent only if it came from an explicit policy
rule or a strategy-supplied signal file that the user configured as trusted.
Generic price alerts do not imply a trade.

```json
{
  "schema": "trade_intent.v1",
  "action": "place_market",
  "symbol": "EURUSD",
  "side": "buy",
  "volume": 0.01,
  "sl": 1.075,
  "tp": 1.09,
  "order_type": "market",
  "comment": "wake eurusd-breakout",
  "client_order_id": "wake-01J...",
  "max_slippage_pips": 2.0,
  "ttl_seconds": 120
}
```

Allowed `action` values:

- `place_market`
- `place_limit`
- `place_stop`
- `modify_order`
- `cancel_order`
- `cancel_all_pending`
- `close_position`
- `close_all_positions`
- `move_sl`
- `break_even`

Every trade intent must include a stable `client_order_id` and be idempotent
within its `ttl_seconds` window.

## Permission Modes

`notify_only`: Send notifications and audit the wake. No dry-run, no trade.

`ask_permission`: Dry-run when a trade intent exists, wake the target agent, and
ask the user for approval. No live mutation happens until an explicit approval is
recorded. The approval expires at the configured `approval_ttl_seconds`.

`auto_dryrun`: Run risk and broker validation automatically, notify the result,
and stop before mutation.

`auto_trade`: Run dry-run first, then mutate only if the policy, account class,
risk limits, and live gates all pass. In the first implementation slice,
`auto_trade` is explicitly blocked with `WAKE_AUTONOMOUS_BLOCKED` after dry-run
because live mutation is future work.

All account classes require an explicit wake policy before mutation. Real-money
accounts additionally require the existing triple live gate. For a daemon, the
caller live intent is supplied only by starting the daemon with an explicit live
execution flag, for example `mt5 alert watch --live`, or by a future adapter
field that is cryptographically or locally permission-bound.

## Policy Contract

Policies are loaded from config and must be validated before the watcher starts.

```json
{
  "wake_policies": [
    {
      "id": "eurusd-breakdown-ask",
      "enabled": true,
      "match": {
        "source": "mt5.alert",
        "symbol": "EURUSD",
        "condition": "Bid <"
      },
      "permission_mode": "ask_permission",
      "adapters": ["codex", "mt5_push"],
      "limits": {
        "allowed_symbols": ["EURUSD"],
        "max_volume": 0.02,
        "max_open_positions": 1,
        "cooldown_seconds": 600,
        "approval_ttl_seconds": 300
      },
      "trade_template": {
        "schema": "trade_intent.v1",
        "action": "place_market",
        "side": "buy",
        "volume": 0.01,
        "sl": 1.075,
        "tp": 1.09
      }
    }
  ]
}
```

Validation failures return `WAKE_POLICY_INVALID`. A matching wake with no policy
returns `WAKE_POLICY_NOT_FOUND` and may still notify if a default notification
policy exists.

## Adapter Requirements

Codex adapter:

- Use Codex automation or thread wake capability for scheduled or recurring
  checks.
- First slice: include a prompt in the wake payload for the target agent to
  consume; direct thread wake is future adapter work.
- Local reliability is bounded by Codex availability and the machine being
  awake.

Claude Code adapter:

- Use Claude Code CLI/session resume for external wakes.
- First slice: include a prompt in the wake payload; direct session wake is
  future adapter work.
- Use hooks for in-session safety, logging, and permission policy reinforcement.
- Do not rely on hooks alone as an external scheduler.

Antigravity adapter:

- Use scheduled tasks for recurring checks where appropriate.
- First slice: include a prompt in the wake payload; direct task/session wake is
  future adapter work.
- Use hooks for execution-loop policy and diagnostics.
- Use CLI notifications for task-completion notification when configured.

Webhook adapter:

- POST the `wake.v1` envelope with an HMAC signature.
- Retry with backoff.
- Never include secrets in the payload.

MT5 push adapter:

- First slice: write an `mt5_push_request.v1` local queue file for a future MQL5
  relay service or EA that reads the queue and calls `SendNotification()`.
- Respect the MQL5 255 character message limit and rate limits.
- Report relay failures as `MT5_NOTIFICATION_FAILED` with MQL5 `GetLastError()`
  when available.

## MT5 App Messaging

Yes, this feature can leverage MetaTrader 5 mobile push notifications, but the
safe path is not to mutate `alerts.dat` from Python.

Two supported approaches:

1. User-created MT5 terminal alerts can set `Action = Notification` and send
   messages to the MetaTrader mobile app through the configured MetaQuotes ID.
   This is useful for user-authored terminal alerts.
2. `metatrader5-cli` can ship or generate an MQL5 relay service/EA. The Python
   daemon writes notification requests to a file inside the terminal data
   directory, and the relay calls `SendNotification()` from inside MT5.

The relay approach is preferred for CLI-originated messages because it avoids
writing the binary alert store and gives the project a testable queue contract.

## Error Codes To Add

- `WAKE_POLICY_INVALID`
- `WAKE_POLICY_NOT_FOUND`
- `WAKE_DEDUPE_REPLAY`
- `WAKE_ADAPTER_FAILED`
- `WAKE_PERMISSION_REQUIRED`
- `WAKE_PERMISSION_EXPIRED`
- `WAKE_AUTONOMOUS_BLOCKED`
- `WAKE_AUDIT_WRITE_FAILED`
- `MT5_NOTIFICATION_FAILED`
- `MT5_NOTIFICATION_RATE_LIMITED`
- `MT5_NOTIFICATION_RELAY_UNAVAILABLE`

## Audit Log

Every wake and trade decision writes a JSONL audit record:

```json
{
  "schema": "wake_audit.v1",
  "event_id": "01J...",
  "policy_id": "eurusd-breakdown-ask",
  "permission_mode": "ask_permission",
  "decision": "asked_user",
  "dryrun": null,
  "mutation": null,
  "adapters": [
    {"name": "codex", "ok": true},
    {"name": "mt5_push", "ok": true}
  ]
}
```

The audit log location must be configurable and default to a user-local runtime
directory outside the repository.

## Acceptance Criteria

- `mt5 alert watch --json` emits valid wake envelopes and exits 0 on known
  failures.
- `mt5 alert watch --once --json` can be tested without a live terminal by using
  fixture alert files.
- Duplicate alert observations do not trigger duplicate actions.
- `ask_permission` never mutates without a recorded approval.
- `auto_trade` performs a dry-run first and returns `WAKE_AUTONOMOUS_BLOCKED`
  instead of mutating in the first implementation slice.
- Real-account autonomous execution requires policy opt-in, daemon live intent,
  `cfg["live"] = true`, and `MT5_LIVE=1`.
- The default MCP server remains read and dry-run only.
- MT5 push relay messages are truncated or rejected before exceeding the MQL5
  `SendNotification()` limit.
- Unit tests cover policy validation, dedupe, permission expiry, adapter failure,
  dry-run-before-mutation, and real-account gate blocking.

## Open Questions

- Should the mutation-capable agent surface be a separate `mt5-mcp-live` server,
  an opt-in MCP mode, or CLI-only for the first implementation?
- Should approvals be stored in a local file, OS keychain-backed store, or agent
  transcript artifact?
- Which adapters should be included in the first implementation slice: Codex and
  MT5 push only, or all three agent platforms?
- Should the MQL5 relay be generated by `mt5 ea new`, shipped as a template, or
  compiled and deployed by a dedicated `mt5 notify install-relay` command?
