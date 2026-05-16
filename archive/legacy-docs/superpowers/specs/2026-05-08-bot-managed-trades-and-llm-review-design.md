# Bot-managed trades + dispatcher-driven LLM review — design

**Date:** 2026-05-08
**Authors:** Claude1 + Codex1 (Metatrader5-CLI workspace)
**Operator:** ehukaimedia
**Status:** awaiting operator approval before writing-plans

## Goal

Two coordinated changes on top of the alerts-only adaptive-forex-mt5 POC:

1. **Dispatcher-driven LLM review pipeline.** Every `ready_alert` becomes an
   ehukaiconnect task assigned to a reviewer agent. The reviewer runs top-down
   analysis (`mt5 ehukai topdown / screenshot / structure`) and returns a
   per-alert verdict (take / skip / adjust this trade's entry/SL/TP). Verdicts
   are advisory; they never directly place, modify, or cancel orders.
2. **Python-side trade manager**, replacing AdaptiveTrailEA for our magics.
   Once a position is open under a poc-magic, the manager handles BE move and
   Chandelier-style trail in Python, anchored on a SQLite state store.

The bot's entry mode stays alerts-only (config flag `agent.alerts_only=true`).
Management is a different lifecycle phase — when a poc-magic position exists
(e.g. after operator flips alerts_only off, or via the phase-3 manual-trade
allowlist), the manager owns its SL/TP from then on.

## Non-goals (phase 1)

- Managing manual magic=0 trades. The operator's GBPJPY/USDJPY positions stay
  on whatever the operator sets manually. The phase-3 allowlist is the agreed
  adoption mechanism (deferred to a separate spec).
- LLM-driven gate/parameter tuning (e.g. raise `min_stop_points` for JPY).
  Verdicts in phase 1 are strictly per-alert. Global tuning is a later phase.
- Auto re-entry, scaling in, hedging. One position per (symbol, magic).

## Architectural invariants

These are enforced regardless of where in the code path you are.

- **LLM is advisory.** Reviewer-agent verdicts are journaled and pushed via
  ntfy. No code path lets a verdict directly call `mt5 order ...` or modify a
  position. Order actions are taken only by the deterministic executor in
  response to operator-approved or preconfigured triggers.
- **One position per (symbol, magic).** Already enforced by `active_strategies`
  in `agent.py`. The manager respects the same scoping.
- **No silent unmanaged poc-magic positions.** If a position exists with magic
  in the poc-set but no journal placement record (so bootstrap fails closed),
  the manager logs `kind=unmanaged_poc_position` each loop and surfaces it on
  the dashboard.
- **JSONL is append-only audit.** `logs/trades.jsonl` is never mutated.
  Mutable runtime state lives in `state.db`. The two are reconciled on
  restart, never merged.
- **Magic=0 stays untouched in phase 1.** No code path in the manager mutates
  any position whose magic is not in the poc-set.
- **Live-intent gate honored everywhere.** The manager reuses
  `cfg["mt5_cli"]["live"]` — the same flag agent.py uses for placement. If
  `live=false`, every modify path is a no-op that logs `manage_skip
  reason=not_live`. There is no second "manager-only live" flag.
- **POC magic set is derived, not pasted.** Computed each loop from
  `derive_magic(f"{prefix}-{pair}")` over `cfg.pairs` (same function as
  agent.py / journal.py). Renaming or adding pairs auto-propagates.

## Architecture

```
                      ┌─────────────────────────┐
                      │ agent.py scan loop      │
                      │ (entry detector)        │
                      └─────┬──────────────┬────┘
                            │              │
                  on READY  │              │  on placement (when alerts_only=false)
                            ▼              ▼
       ┌─────────────────────────┐    ┌──────────────────────────────┐
       │ dispatcher task         │    │ logs/trades.jsonl            │
       │ type=trade_review       │    │ kind=placement (existing)    │
       │ assignee=ReviewerAgent  │    └──────────────┬───────────────┘
       │ description=alert json  │                   │
       └────────┬────────────────┘                   │ bootstrap
                │ dispatch_wake                      ▼
                ▼                       ┌──────────────────────────────┐
       ┌─────────────────────────┐      │ state.db (SQLite)            │
       │ Reviewer agent          │      │ table: managed_position      │
       │ - mt5 topdown/screenshot│      │ stage, init_sl, hwm/lwm, ... │
       │ - vision + structure    │      └──────────────┬───────────────┘
       │ - emits verdict         │                     │
       └────────┬────────────────┘                     │
                │ task update --status done            │
                │ description=verdict json             │
                ▼                                      │
       ┌─────────────────────────┐                    │
       │ agent.py verdict poller │                    │
       │ - journal as            │                    │
       │   kind=llm_verdict      │                    │
       │ - push enriched ntfy    │                    │
       └─────────────────────────┘                    │
                                                      │
                                  ┌───────────────────┴──────────────┐
                                  │ trade_manager.py loop (1s)       │
                                  │ for each MT5 pos with magic ∈    │
                                  │ poc-set: compute BE+Chandelier,  │
                                  │ call mt5 position modify when    │
                                  │ tighten >= min_improvement       │
                                  │ journal kind=manage_action       │
                                  └──────────────────────────────────┘
```

## Component: dispatcher LLM review pipeline

### Trigger and payload

In `agent.py` `place_new_orders`, the existing alerts-only branch (around
line 302) currently calls `journal.log_ready_alert` and `alerts.push`. After
those, add `dispatch_review(cfg, pair, scan_data)` which shells out:

```
ehukaiconnect task create
  --type trade_review
  --priority high
  --assignee <cfg.agent.reviewer_agent>
  --description '<json: pair, dir, entry, sl, tp, rr, gates, structure, ts>'
```

The full alert payload is too large for a single CLI argument. We write it to
`.ehukaiconnect/shared/files/alerts/<ts>-<pair>.json` and pass the path in
`description`. Reviewer reads the file by path.

### Reviewer agent

A dedicated persistent ehukaiconnect agent named `ClaudeReviewer` (created via
`ehukaiconnect agent create`, separate identity from Claude1's coordinator
role) wakes on `dispatch_wake`. Its skill at
`.ehukaiconnect/skills/ClaudeReviewer/SKILL.md` instructs it to:

1. Read alert payload from the path in task description.
2. Run `mt5 --json ehukai topdown <pair>` and screenshot the relevant TFs.
3. Emit a structured verdict (see below) by writing
   `.ehukaiconnect/shared/files/verdicts/<alert_id>.json` and calling
   `task update --status done --description <path>`.

Reviewer terminal is started via `Start-Process` like agent.py / dashboard.py
so it survives the Claude Code session that spawned it.

### Verdict schema (phase 1)

```json
{
  "alert_id": "<ts>-<pair>",
  "decision": "take" | "skip" | "adjust",
  "adjusted_entry": 1.0850 | null,
  "adjusted_sl":    1.0820 | null,
  "adjusted_tp":    1.0920 | null,
  "confidence": 0.0..1.0,
  "reasoning_summary": "<= 280 chars",
  "reasoning_full": "string",
  "model": "<id>",
  "ts": "<iso>"
}
```

`take` and `skip` are pure verdicts. `adjust` is the only branch that proposes
new levels — and even then they are advisory, surfaced to the operator as
"reviewer suggests SL=X" in the enriched ntfy. Operator action is still
required.

### agent.py side: closure poller

A small loop in `agent.py` (or its own short-lived check at end of each
`scan_once`) calls:

```
ehukaiconnect task list --type trade_review --status done --since <last_seen>
```

For each new closed task: read the verdict file, append
`kind=llm_verdict` to `trades.jsonl`, push enriched ntfy. The `--since`
cursor lives in `state.db` so we don't double-process.

### Why dispatcher (vs other options)

- **Persistent reviewer terminal** is cheaper than spawning a headless Claude
  per alert (~$0.20-0.30/alert, $45-90/mo at 5-10/day per memory note).
  Prompt-cache stays warm across alerts inside one session.
- Dispatcher already runs (port 8811) with wake/cooldown/stale logic.
- Bus-visible — operator can `send-to ReviewerAgent ...` to debug or override.
- Tasks persist; on reviewer crash, dispatcher re-wakes on restart.

## Component: Python TradeManager

### Claim model

**Phase 1 (this spec):** manage only positions with magic in the poc-set
(11 magics, listed in memory `project_adaptive_forex_mt5.md`). Manual
magic=0 is never touched.

**Phase 3 (deferred — separate spec):** explicit allowlist file at
`adaptive-forex-mt5/managed_positions.json` keyed by ticket+symbol+account
with fields `{ticket, symbol, mode, initial_risk, be_r, trail_model, expires_at, operator_note}`.
Not built in phase 1 — design left in this doc as a forward reference only.

Comment-field tagging was considered and rejected: the MT5 comment field is
truncated/awkward to mutate safely.

### state.db schema

SQLite, file at `adaptive-forex-mt5/state.db` (sibling of `trades.jsonl`).
WAL mode. Schema reflects Codex1's review: confirm-before-promote
idempotency, broker-precision risk fields, active-position uniqueness,
heartbeat-driven dead-process detection.

```sql
CREATE TABLE managed_position (
    ticket              INTEGER PRIMARY KEY,
    account             INTEGER NOT NULL,
    symbol              TEXT    NOT NULL,
    magic               INTEGER NOT NULL,
    direction           TEXT    NOT NULL,    -- 'buy' | 'sell'
    entry_price         REAL    NOT NULL,
    initial_sl          REAL    NOT NULL,
    initial_tp          REAL,
    initial_risk_price  REAL    NOT NULL,    -- abs(entry - initial_sl) in price units
    initial_risk_points REAL    NOT NULL,    -- initial_risk_price / point
    point               REAL    NOT NULL,    -- broker point (e.g. 0.001 for JPY pairs)
    digits              INTEGER NOT NULL,
    opened_time         TEXT    NOT NULL,    -- MT5 position open time
    source_order_ticket INTEGER,             -- placement order ticket from journal, if known
    journal_anchor      TEXT,                -- ts of matched placement record in trades.jsonl
    stage               TEXT    NOT NULL,    -- 'init' | 'be_armed' | 'trailing' | 'closed'
    favorable_extreme_price REAL,            -- buy: max(bid) since open; sell: min(ask) since open
    last_sl_set         REAL,                -- only set AFTER MT5 confirms position.sl == requested_sl
    pending_action      TEXT,                -- NULL | 'modify_sl'
    requested_sl        REAL,
    idempotency_key     TEXT,                -- hash of (ticket, requested_sl, stage_to)
    last_action_ts      TEXT,
    last_unmanaged_warning_ts TEXT,          -- per-ticket rate limit for the warning event
    created_ts          TEXT    NOT NULL,
    updated_ts          TEXT    NOT NULL
);

-- Enforce one active position per (account, symbol, magic). Closed positions
-- are excluded so historical rows do not block new entries.
CREATE UNIQUE INDEX active_pos_uniq
    ON managed_position (account, symbol, magic)
    WHERE stage != 'closed';

CREATE TABLE cursor (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- e.g. cursor.name='last_verdict_seen', value='2026-05-08T16:37:15Z'

CREATE TABLE heartbeat (
    process   TEXT PRIMARY KEY,    -- 'agent' | 'manager' | 'dashboard'
    last_seen TEXT NOT NULL,
    pid       INTEGER,
    notes     TEXT
);
-- agent.py / trade_manager.py / dashboard.py upsert each loop. Dashboard
-- renders a red banner when any process's last_seen is older than
-- 2 * its loop_seconds.
```

### Bootstrap (restart-safe)

The poc-magic set is **derived**, not pasted from memory. Compute on every
loop iteration:

```python
poc_magics = {
    derive_magic(f"{cfg.agent.strategy_id_prefix}-{pair}")
    for pair in cfg.pairs
}
```

This uses the same `derive_magic` already in `journal.py:26`. If `cfg.pairs`
or `strategy_id_prefix` change, the manager naturally tracks the new set.

Each manager loop iteration (default 1s):

1. List MT5 positions with `mt5 --json position list`.
2. Filter to `magic ∈ poc_magics`.
3. For each filtered position:
   1. **Already known.** If a `managed_position` row exists for the ticket
      and `stage != 'closed'`: use it.
   2. **Match by ticket.** Else look up `kind=placement` records in
      `trades.jsonl` where `placement.ticket == position.ticket`. If exactly
      one match → seed.
   3. **Fallback by (magic, symbol).** If no ticket match, filter open
      placements (no `outcome` yet) by `(magic, symbol)`. If exactly one
      match → seed using its data; record `source_order_ticket =
      placement.ticket`.
   4. **Ambiguous or zero match → fail closed.** Emit
      `kind=unmanaged_poc_position` (rate-limited via
      `last_unmanaged_warning_ts`, default ≥60s gap), do not modify.

Seeding fields when a journal match is found:

- `initial_sl = placement.sl`
- `initial_risk_price = abs(entry - initial_sl)`
- `initial_risk_points = initial_risk_price / point`
- `point` and `digits` from `mt5 --json symbol info <pair>`
- `journal_anchor = placement.ts`
- `opened_time` from `position.time`

#### Stage inference on bootstrap

Never loosen an SL on bootstrap. After seeding, infer `stage` from the
**current** `position.sl` relative to `entry`:

- **Buy:**
  - If `position.sl >= entry + BE_Buffer_Points * point` → at least
    `be_armed`. Compare `position.sl` against the current Chandelier stop:
    if `position.sl >= chandelier_now` → `trailing`, else `be_armed`.
  - Else → `init`.
- **Sell:** mirror image.

If inferred stage is `be_armed` or `trailing`, set
`last_sl_set = position.sl` immediately (this is a known-good SL set by the
prior process or by the EA before handoff). Subsequent loops only TIGHTEN.

### Management logic (mirrors AdaptiveTrailEA)

The Python manager replicates the EA's two stages. Defaults match the EA:

**Stage 1: Breakeven move**
- Trigger: when current favorable distance >= `BE_Trigger_R * initial_risk`.
  Default `BE_Trigger_R = 0.80`. If `initial_risk_points` unavailable (it's
  required by bootstrap, so this should not happen in phase 1), fall back to
  `BE_Trigger_Points = 80` like the EA.
- Action: set SL to `entry ± BE_Buffer_Points` (default 5 points beyond entry
  in the favorable direction). Update `stage = 'be_armed'`.

**Stage 2: Chandelier trail**
- After BE armed: every loop, recompute Chandelier stop on M5 with ATR(22)
  multiplier 3.0 over a 22-bar lookback of extremes. Source: `mt5 --json rates`.
- Tighten SL only if new stop is at least `Min_SL_Improvement_Points = 5`
  beyond the current SL (broker-friendly, avoids no-op modifies).
- Update `stage = 'trailing'`, refresh `favorable_extreme_price` and
  `last_sl_set`.

**Spread guard:** skip any modify when `spread_points > Max_Spread_Points`
(default 100, matching EA).

**TP runner removal** (EA's `Allow_TP_Removal`): off by default in phase 1.
Can be enabled later through config.

### Modify call and idempotency

**Critical:** `last_sl_set` is the *confirmed* SL only. It is never written
speculatively. Per Codex1's review, the flow is request → call → confirm →
promote.

State machine per loop iteration on a `managed_position` row:

1. **Compute target.** Decide whether BE or Chandelier produces a tightening
   `new_sl`. If not a tightening (or fails `min_sl_improvement_points` /
   spread guard), no-op.
2. **Reuse pending action if any.** If `pending_action == 'modify_sl'` and
   `requested_sl` is still relevant (i.e. still a tightening from current
   `position.sl`):
   - Re-read `position.sl` first. If `position.sl == requested_sl`: promote
     (see step 5). The previous attempt actually succeeded; we just lost the
     ack.
   - Else if cooldown elapsed (default 5s since `last_action_ts`): proceed
     to step 3 with the same `idempotency_key`.
   - Else: skip this loop, retry next loop.
3. **Stage the request.** Write `pending_action='modify_sl'`,
   `requested_sl=new_sl`, `idempotency_key=hash(ticket, new_sl, stage_to)`,
   `last_action_ts=now`. Commit.
4. **Call MT5.** Reuse the existing live-intent gate
   `cfg["mt5_cli"]["live"]` — if `live=false`, log `kind=manage_skip
   reason=not_live` and clear `pending_action`. Else call:
   ```
   mt5 --json position modify <ticket> --sl <new_sl> --filling fok
   ```
5. **Confirm and promote.** On any return value, re-read `mt5 --json
   position list` for the ticket:
   - If `position.sl == requested_sl`: promote `last_sl_set = requested_sl`,
     update `stage`, clear `pending_action / requested_sl /
     idempotency_key`, journal `kind=manage_action` with
     `old_sl, new_sl, trigger`.
   - If position closed (TP hit / SL hit during the call): set
     `stage='closed'`, journal `kind=outcome` (existing kind), clear
     pending fields.
   - Else (modify rejected, e.g. invalid stops, requote): leave
     `pending_action` set. Next loop retries after cooldown. Journal
     `kind=manage_skip reason=<retcode>`.

This eliminates the "skip forever after unknown result" failure mode the
prior draft had — every iteration re-derives state from MT5 truth.

### Journal events emitted

New `kind` values appended to `trades.jsonl` (immutable audit):

- `kind=manage_action` — every successful BE move or trail tighten. Fields:
  `ticket, stage_from, stage_to, old_sl, new_sl, trigger, ts`.
- `kind=manage_skip` — every loop where guards rejected a modify. Fields:
  `ticket, reason ('spread' | 'min_improvement' | 'spread_cap' | ...), ts`.
  Rate-limited (once per ticket per 30s) to avoid log churn.
- `kind=unmanaged_poc_position` — see fail-closed bootstrap above.
- `kind=llm_verdict` — see review pipeline above.
- `kind=review_request` — when agent.py creates a review task. Fields:
  `task_id, alert_id, ts`.

Existing kinds (`placement`, `skip`, `outcome`, `error`, `ready_alert`) are
unchanged.

### Manager loop and process model

Two reasonable layouts; the design picks (B):

- **(A) Inside agent.py.** Adds a manager call to each `scan_once` iteration.
  Simple, but couples 1s management to the slower scan cadence (currently
  bar-cadence). Rejected: management needs sub-bar reactivity.
- **(B) Separate `trade_manager.py` process.** Started alongside agent.py and
  dashboard.py via `Start-Process`. Loop cadence 1s. Reads MT5 + state.db,
  writes to journal + state.db. Crash-safe via fail-closed bootstrap.

Adopt **(B)**. Same Start-Process pattern as the existing two processes.

### Dashboard surface

`dashboard.py` reads `state.db` (read-only) and renders three new surfaces:

1. **Managed positions** — one row per `managed_position` row where
   `stage != 'closed'`: `ticket, symbol, direction, stage, entry,
   initial_sl, last_sl_set (current SL), favorable_extreme_price,
   unrealized R, last_action_ts`. Also surfaces any `pending_action` so
   in-flight modifies are visible.
2. **Process heartbeat** — table rendered from the `heartbeat` table.
   Process row goes red if `now - last_seen > 2 * loop_seconds`.
3. **Unmanaged poc-position banner** — red bar at the top of the dashboard
   when any `managed_position` has a recent `last_unmanaged_warning_ts`
   (within the last loop tick). Surfaces silent failure of the bootstrap
   match.

## Config additions (`adaptive-forex-mt5/config.json`)

```json
{
  "agent": {
    "alerts_only": true,
    "reviewer_agent": "ClaudeReviewer",
    "review_enabled": true
  },
  "manager": {
    "enabled": true,
    "loop_seconds": 1,
    "be_trigger_r": 0.80,
    "be_buffer_points": 5,
    "be_trigger_points_fallback": 80,
    "chandelier_atr_period": 22,
    "chandelier_atr_multiplier": 3.0,
    "chandelier_extreme_lookback": 22,
    "chandelier_timeframe": "M5",
    "min_sl_improvement_points": 5,
    "max_spread_points": 100,
    "allow_tp_removal": false
  }
}
```

`config.example.json` is updated to match. `config.json` (gitignored) keeps
operator overrides.

## Restart and crash recovery

| Process | What persists | Recovery rule |
|---|---|---|
| agent.py | `trades.jsonl`, `state.db.cursor`, `state.db.heartbeat` | restart from `last_verdict_seen` cursor; replay missed task closures; resume heartbeat upserts |
| trade_manager.py | `state.db.managed_position`, `state.db.heartbeat` | rebuild from MT5 position list joined to journal placements; fail-closed on ambiguity; replay any `pending_action` rows by re-confirming MT5 state |
| dashboard.py | `state.db.heartbeat` (write) | restart, re-read `trades.jsonl` + `state.db` |
| Reviewer agent | task queue, `shared/files/{alerts,verdicts}/` | dispatcher re-wakes; idempotent because task statuses are persisted |

Tailscale serve config persists across reboots (verified in handoff memory).

## Phasing

- **Phase 1 (this spec, foundation)**
  - LLM review pipeline (read-only) wired to one persistent reviewer agent
  - Python TradeManager process with bot-magic scope and SQLite state
  - New journal kinds, dashboard view
  - Reviewer skill template under `.ehukaiconnect/skills/<reviewer>/SKILL.md`
- **Phase 2 (this spec, autopilot — see section below)**
  - Two-of-two consensus auto-trade lane with shadow-mode practice period
  - Adds second reviewer agent + consensus evaluator + autopilot executor
  - Master flag default OFF; operator flips after measured calibration
- **Phase 3 (deferred — separate spec)**
  - Allowlist file `managed_positions.json` for adopting manual trades
  - LLM verdict reasoning archive for off-line A/B
- **Phase 4 (deferred)**
  - LLM-driven gate-param tuning suggestions (e.g. raise `min_stop_points`
    for JPY crosses) — operator approves before applying

## Phase 2: Autopilot mode

This section adds two-of-two consensus auto-placement on top of the phase-1
foundation. Operator's "I want a mode for when I'm away" request, with the
hard guarantee that **reviewers never set broker levels** — they only vote
on the deterministic setup the bot has already produced.

### Invariants (additive)

These extend, not replace, the phase-1 invariants.

- **Advisory-only stays.** Reviewers never place, modify, or cancel orders,
  and never propose or normalize broker levels in the auto path. They vote
  on the bot's original READY setup; a vote is a yes/no on those exact
  levels. Adjustment-style verdicts route to human review or shadow-only.
- **2-of-2 strict consensus.** Both reviewers must vote `take` with the
  same direction, both `confidence >= autopilot.min_confidence`, and both
  must explicitly accept the deterministic `entry/sl/tp`. If either votes
  `skip` / `adjust` / `unclear` / times out → no auto trade.
- **Different model families.** Reviewer pair = Claude + Codex (different
  training lineages, real independence). Two-of-two from the same family
  is not allowed in autopilot config.
- **No level synthesis.** No midpoints, no "use the more conservative
  reviewer's adjustment." If both reviewers wanted different levels,
  that's two trades nobody actually reviewed → skip.
- **Shadow-first.** `autopilot.enabled` defaults OFF and stays OFF until
  operator flips it after evidence-based calibration (see calibration
  section). Shadow records run regardless of the flag.
- **Gate parity.** Every phase-1 entry gate (READY, RR, spread, trap,
  one-position-per-strategy, daily-trade-cap) must still pass at place
  time, plus the autopilot-specific guards (allowlist, news blackout,
  daily auto cap, daily loss cap, micro-lot, kill-switch off).

### Components added

1. **Second reviewer agent.** A dedicated `CodexReviewer` agent (alongside
   the phase-1 `ClaudeReviewer`), spawned via `ehukaiconnect agent create`
   with its own skill template. Same dispatcher integration: `agent.py`
   creates **two** `trade_review` tasks per `ready_alert`, one per
   reviewer, in parallel.
2. **Consensus evaluator.** A small function in `agent.py`'s closure poller
   that, on each loop, joins task closures by `alert_id`. When both
   reviewers' tasks for a given alert are `done`, it computes the
   consensus verdict and journals `kind=consensus_verdict` regardless of
   `autopilot.enabled`.
3. **Autopilot executor.** Runs after consensus evaluator. If
   `autopilot.enabled` AND consensus says `take` AND all gate-parity
   checks pass AND kill-switch is off, calls
   `mt5 order ready-limit ...` at micro-lot using **the bot's original
   setup levels** (not anything the reviewers said). Otherwise journals
   `kind=autopilot_skip` with the failed gate.
4. **Kill-switch.** A row in `state.db.cursor` named `autopilot_kill`. Two
   ways to flip it: dashboard button, or bus message `AUTOPILOT ABORT`
   from operator. Once set, autopilot executor halts immediately and
   ntfy-pushes a confirmation. Cleared explicitly via dashboard or bus.

### Setup fingerprint (binds verdicts to a specific setup)

Without a fingerprint, the autopilot executor's "still READY" check could
pass against a *different* READY setup that arrived a few bars after the
one the reviewers actually voted on — auto-placing on a fresh cousin
setup nobody approved. The fingerprint pins each verdict to the exact
setup snapshot.

`setup_fingerprint` is a stable hash computed at the time `ready_alert`
is emitted, over:

- `pair`, `direction`
- `entry`, `sl`, `tp` (rounded to broker `digits`)
- POI: `id` and `(top, bottom)` bounds
- Structure event: `last_confirmed_event.type` + `last_confirmed_event.level.time`
- Setup bar time (entry timeframe)

It propagates through:

- `ready_alert` record (new field)
- alert payload file under `.ehukaiconnect/shared/files/alerts/`
- each reviewer's verdict (the verdict implicitly votes on this
  fingerprint; emitted by the reviewer back into its verdict file)
- `consensus_verdict` record

The autopilot executor MUST verify the fingerprint matches the current
setup before placing — see gate parity update below.

### Consensus verdict schema

```json
{
  "alert_id": "<ts>-<pair>",
  "setup_fingerprint": "<hex>",
  "alert_ts": "<iso>",
  "reviewers": ["ClaudeReviewer", "CodexReviewer"],
  "votes": [
    { "reviewer": "ClaudeReviewer", "decision": "take", "direction": "buy",
      "confidence": 0.84, "accepted_levels": true,
      "reviewed_fingerprint": "<hex>",
      "verdict_path": ".ehukaiconnect/shared/files/verdicts/<alert_id>-claude.json" },
    { "reviewer": "CodexReviewer",  "decision": "take", "direction": "buy",
      "confidence": 0.79, "accepted_levels": true,
      "reviewed_fingerprint": "<hex>",
      "verdict_path": ".ehukaiconnect/shared/files/verdicts/<alert_id>-codex.json" }
  ],
  "consensus": "take" | "no_consensus",
  "consensus_reason": "2-of-2 take, conf min=0.79 >= 0.75, levels accepted, fingerprints match",
  "ts": "<iso>"
}
```

`accepted_levels` derives mechanically from each reviewer's phase-1
verdict: `true` iff `decision == "take"` and every `adjusted_*` field is
`null`. A reviewer who proposes any adjustment is implicitly rejecting the
deterministic levels and cannot satisfy the autopilot consensus rule.

`reviewed_fingerprint` must equal the alert's `setup_fingerprint` for the
vote to count. If they differ (reviewer raced or read a stale payload) →
the vote is treated as `unclear`.

`consensus="take"` requires every condition in the strict invariant
above. Anything else → `consensus="no_consensus"` with the failing reason.

### Gate parity (autopilot executor checks in order)

Each gate either passes or fails the auto-place attempt. First failure
short-circuits and journals `kind=autopilot_skip reason=<gate_name>`:

1. `autopilot.enabled == true`
2. `state.db.cursor.autopilot_kill == off`
3. `consensus.consensus == "take"`
4. `pair ∈ autopilot.pair_allowlist`
5. **Alert age:** `now - consensus.alert_ts <= autopilot.max_alert_age_seconds`.
   Stale alerts (e.g. reviewers took longer than `decision_timeout_seconds + one
   scan loop`) are dropped with `reason=stale_setup`.
6. **Setup fingerprint binds to the live setup.** Re-run `sniper_poc(pair)`.
   The current setup must satisfy ONE of:
   - `current.setup_fingerprint == consensus.setup_fingerprint` (exact match), OR
   - Same `direction`, same POI `id`, same structure `last_confirmed_event`,
     AND each of `entry / sl / tp` differs from consensus by <=
     `autopilot.max_entry_drift_points`.
   Anything else → `reason=stale_setup`. This preserves the rule that
   reviewers approved the bot's original setup, not a fresh cousin.
7. `cfg.mt5_cli.live == true` (manager-shared gate)
8. `spread_points <= max_spread_points`
9. News blackout: no high-impact event within
   `[-news_blackout_minutes_before, +news_blackout_minutes_after]`
   (data source: TBD — separate ticket; until then, fail closed if
   `autopilot.news_source == null`)
10. `volume == autopilot.lot_size` (micro-lot only, hard-coded path)
11. Daily caps: `autopilot_trades_today < autopilot.daily_trade_cap` and
    `autopilot_realized_loss_today < autopilot.daily_loss_cap_usd`. Both
    counters scope to **net realized autopilot P/L only** — manual / phase-3
    adopted trades do not count toward the autopilot loss cap.
12. `active_strategies` does not already contain `(pair, magic)`
    (existing phase-1 invariant, re-checked here)

If all 12 pass → call `mt5 order ready-limit ...` with the bot's
deterministic levels (NOT any reviewer-adjusted levels). Journal
`kind=autopilot_placement` (distinct from manual `kind=placement`) so
dashboard can split the two cleanly.

### Calibration / shadow phase

While `autopilot.enabled=false` (the default), the system still runs both
reviewers on every alert and journals every `kind=consensus_verdict`. The
dashboard surfaces:

- Counts: shadow `take` consensus / `no_consensus` per pair
- "Would-have" P/L: for each shadow `take`, attribute the deterministic
  setup against actual market over the next 24h using the bot's TP/SL
  rules (already implemented for outcome attribution in phase 1)
- Rolling consensus accuracy: hit-rate and R-multiple distribution

The operator flips `autopilot.enabled=true` only after these metrics meet
their personal bar (no threshold pre-encoded — operator's call).

### Config additions (`adaptive-forex-mt5/config.json`)

```json
{
  "autopilot": {
    "enabled": false,
    "reviewer_agents": ["ClaudeReviewer", "CodexReviewer"],
    "min_confidence": 0.75,
    "pair_allowlist": ["USDJPY"],
    "lot_size": 0.001,
    "daily_trade_cap": 5,
    "daily_loss_cap_usd": 5.00,
    "news_blackout_minutes_before": 15,
    "news_blackout_minutes_after": 30,
    "news_source": null,
    "decision_timeout_seconds": 90,
    "max_alert_age_seconds": 180,
    "max_entry_drift_points": 30
  }
}
```

`news_source: null` is intentional — no news provider wired yet, so the
news-blackout gate fails closed. Operator must wire a source before
flipping `enabled` to true. This is enforced in code, not just docs.

### New journal kinds (phase 2)

- `kind=consensus_verdict` — every joined pair of reviewer verdicts
  (shadow + live). Fields per the schema above.
- `kind=autopilot_placement` — successful auto-placement. Same shape as
  existing `kind=placement` plus `consensus_alert_id, reviewer_confidences`.
- `kind=autopilot_skip` — gate failure or no_consensus. Fields:
  `alert_id, gate, reason, ts`.
- `kind=autopilot_kill` — kill-switch state change. Fields: `prev, new,
  source ('dashboard' | 'bus'), ts`.

### Failure modes specific to phase 2

| Failure | Behavior |
|---|---|
| One reviewer crashes / hangs | `decision_timeout_seconds` elapses → consensus = no_consensus, log `autopilot_skip reason=reviewer_timeout`, ntfy operator |
| Reviewer returns malformed verdict | Treated as `unclear` → no_consensus, log error, ntfy operator |
| Both reviewers vote take but levels differ from deterministic setup | Per the invariant: not a take. Skip with `reason=levels_not_accepted` |
| Kill-switch flipped mid-decision | Executor checks kill flag last (gate 2); if flipped between consensus and place, abort |
| News provider becomes null after enabling | Gate 8 fails closed → no auto trades until restored |
| Reviewer disagreement (one take, one skip) | `consensus=no_consensus`, ntfy with both verdicts so operator can manually decide |
| Reviewer races / reads stale payload — `reviewed_fingerprint` mismatches `setup_fingerprint` | Vote treated as `unclear` → `consensus=no_consensus`, log `reason=fingerprint_mismatch` |
| Setup drifted between alert and place attempt — gate 6 fails | `autopilot_skip reason=stale_setup` with the failing sub-condition (fingerprint vs drift) |

### Spawn / shutdown

Both reviewer agents are spawned via `ehukaiconnect agent create` and run
in their own persistent terminal sessions (Start-Process, sibling of
agent.py / dashboard.py / trade_manager.py). Their skills under
`.ehukaiconnect/skills/{ClaudeReviewer,CodexReviewer}/SKILL.md` instruct
them on the verdict schema and the explicit-accept-levels requirement.

Reviewer process death is detected via the `heartbeat` table (extended
with rows for `claude_reviewer` and `codex_reviewer`). Dashboard banner
goes red on any reviewer death; if `autopilot.enabled=true` and either
reviewer is offline, all consensus evaluations short-circuit to
`no_consensus` until recovery.

## Operator approval gates that remain alerts-only

The "alerts-only" ground rule applies to **entry** placement. For management,
the bot is autonomous within its own poc-magic positions — that's what the
operator asked for ("our own bot to manage trades after we place the trades
instead of the EA"). No tap-to-confirm on each BE/trail tighten; the EA
didn't require that and the Python replacement maintains parity.

If the operator wants a tap-to-confirm flow for management actions, that's a
config flag we can add later (`manager.confirm_each_action: true`). Out of
scope for phase 1 unless they reverse course.

## Open questions for operator

(Phase-1 reviewer-agent identity question is resolved: dedicated
`ClaudeReviewer` + `CodexReviewer` agents.)

1. **First managed trade rollout.** Phase 1 ships as **infrastructure
   ready** — the manager has nothing to manage today because alerts-only mode
   means no bot placements exist. Do you want a smoke test where we flip
   `alerts_only=false` for ONE pair (say USDJPY at 0.001 lots) to exercise
   the full lifecycle once before phase 2 builds on it?
2. **Reviewer model defaults.** ClaudeReviewer = Claude Opus 4.7 with prompt
   caching ($0.20-0.30/alert per memory) or Sonnet (~5-10× cheaper for
   similar chart-reasoning quality)? CodexReviewer model is whatever the
   Codex CLI is configured with on this workspace.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Python manager dies, position runs to original SL | Fail-closed bootstrap restores state on restart; warning banner if process is dead is added to dashboard |
| LLM review crashes / hangs | Verdict polling timeout; alert remains as plain ntfy; advisory only so safety unaffected |
| Race between scan loop and manager loop | Each owns a different MT5 surface (scan reads rates/structure; manager reads positions). No write contention. `mt5 position modify` is broker-atomic |
| Trading.com FOK-only fills reject modifies | EA already handles this; mirror with `--filling fok` and one warn-once log per ticket |
| State.db corruption | SQLite WAL mode; nightly snapshot copy if we need durability harder than that |

## Test plan (high level — fleshed out in writing-plans)

- Unit: BE-trigger math, Chandelier computation, idempotency-key reuse
- Integration: bootstrap from a fake `trades.jsonl` + MT5 position fixture
- e2e: extend `test_e2e.py` with one managed-position lifecycle on demo;
  gated by `--allow-live` like the existing entry e2e
- Restart drill: kill `trade_manager.py`, verify state.db rehydrates correctly

## References

- Memory: `project_adaptive_forex_mt5.md` (POC handoff state, magic list)
- Memory: `reference_photon_smc_framework.md` (mechanical management rules)
- Memory: `project_mt5_cli_spec.md` (Trading.com FOK + netting + FIFO)
- Code: `metatrader5_cli/mt5/mql5/Experts/AdaptiveTrailEA.mq5` (logic to port)
- Sketch (now superseded by this doc): `.ehukaiconnect/shared/docs/dispatcher-trade-review-sketch.md`
