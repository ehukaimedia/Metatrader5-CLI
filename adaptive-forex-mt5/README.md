# adaptive-forex-mt5

A live multi-pair scanner that watches the Ehukai TDA stack (the deterministic SMC framework in [`metatrader5_cli/`](../metatrader5_cli)) and emits trade-idea alerts to your phone. Operator decides whether to take each setup manually.

**Default mode is alerts-only.** The bot does NOT place orders; it pushes a structured trade idea (entry, SL, TP, R:R, reasoning) via ntfy when the framework's gates align, and journals every event for post-hoc review.

Auto-placement mode exists (`agent.alerts_only=false`) but is not the recommended workflow — see *Why alerts-only* below.

---

## Quick start

### 1. Setup

```powershell
cd C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\adaptive-forex-mt5
copy config.example.json config.json
```

Edit `config.json`:
- `pairs` — symbols to scan (default: 11 majors + JPY/EUR/GBP crosses)
- `agent.alerts_only` — `true` to push alerts only (default), `false` to auto-place
- `agent.min_rr` — reject setups below this R:R (default 3.0)
- `agent.min_quality_score` — minimum gate-pass-rate (default 0.85)
- `agent.min_stop_points` — minimum structural SL distance in points (default 80; consider 150+ for JPY crosses — see *Known limits*)
- `ntfy.topic` — your ntfy.sh channel
- `mt5_cli.live` — `false` for demo, `true` for live

### 2. Run

Two long-running processes, each in its own terminal so they survive your shell session ending:

```powershell
Start-Process powershell -ArgumentList '-NoExit','-Command','python dashboard.py'
Start-Process powershell -ArgumentList '-NoExit','-Command','python agent.py'
```

### 3. Expose the dashboard remotely (Tailscale)

The dashboard binds `127.0.0.1:8765` deliberately — no LAN exposure. To reach it from your phone via your tailnet:

```powershell
tailscale serve https / http://localhost:8765
```

Then visit `https://<this-machine>.<your-tailnet>.ts.net/` from any tailnet device. To stop sharing: `tailscale serve --https=443 off`.

**Do not** use `tailscale funnel` (public-internet exposure).

### 4. Subscribe to alerts

Install ntfy on your phone, subscribe to the topic in `config.json`. You'll get push notifications when the bot detects a READY setup.

---

## Files

| File | Purpose |
|---|---|
| `agent.py` | Scan loop — polls all 11 pairs every 60s, runs `mt5 analyze sniper-poc`, dispatches alerts or placements based on `alerts_only` |
| `journal.py` | Append-only `logs/trades.jsonl` with `placement`, `skip`, `outcome`, `error`, `ready_alert` records — full setup contract per event |
| `dashboard.py` | Local web view (`http://localhost:8765/`) showing closed trades + reasoning + per-pair stats |
| `alerts.py` | ASCII-safe ntfy push wrapper |
| `bench_llm.py` | Latency + JSON-validity benchmark for candidate LLMs (Qwen 3.6, ehukai-gemma4) — used for evaluating LLM review options |
| `test_e2e.py` | Real-broker round-trip test (gated by `--allow-live` flag) verifying outcome attribution, active-strategy guard, and magic-derivation parity |
| `skills/trading.com/SKILL.md` | Broker-specific constraints (FOK, FIFO, 1:50 leverage) |
| `config.example.json` | Default config (alerts_only: false) |
| `config.json` | Operator config (gitignored) |
| `logs/trades.jsonl` | Append-only journal (gitignored) |

---

## How an alert reads on your phone

When sniper-poc returns READY, you get an ntfy push like:

```
🔔 GBPJPY SELL idea
Entry: 213.482
SL:    213.560 (7.8p)
TP:    213.140 (34.2p)
R:R 4.39  Quality 0.88
M15 BEARISH BOS at LH
```

Everything you need to manually decide whether to take it, at what size, with what entry adjustment.

---

## Why alerts-only

A short summary of why we landed here, after a day of running the bot in auto-place mode:

1. The Photon SMC framework correctly identifies **direction**. The bot's first three real trades all had the right directional read.
2. The framework's structural SL is **too tight for JPY-cross spreads**. Today's GBPJPY trade was stopped out 5.2 pips below entry; price then rallied 36 pips in the bot's intended direction. Classic SL-too-tight failure.
3. At micro-lot (0.001), even profitable setups capture cents. To trade meaningful size, you need a wider SL — which the framework doesn't currently produce.
4. The operator's manual entries (different timing, larger size, wider SL) outperformed the bot's mechanical execution by orders of magnitude on the same directional reads.

**Conclusion:** the bot is a high-quality signal generator with a robust audit trail. The trade management (SL, TP, sizing) is better left to the operator until the framework's stop-placement logic is improved.

---

## Journal record kinds

Every event is a single line in `logs/trades.jsonl`. Five kinds:

| Kind | When |
|---|---|
| `ready_alert` | Alerts-only: bot detected READY setup, pushed alert, did NOT place |
| `placement` | Auto-place mode: bot placed an order, with full final-setup reasoning |
| `skip` | Setup didn't pass gates — full setup contract preserved for post-hoc false-negative review |
| `outcome` | Position closed (TP, SL, manual, BE-trail). Records profit, swap, commission, net, realized_r |
| `error` | Subprocess or broker error |

Each `ready_alert`, `placement`, and `skip` carries the full `_reasoning()` block: structure, POI, liquidity, entry, gates_passed, gates_failed (with details), quote, bias_counts, explain.

**Aggregate stats** (`journal.stats()`):
- Win/loss/breakeven counts using **net P/L** (profit + swap + commission)
- Total realized R, average realized R per closed trade
- Per-pair breakdown

---

## Dashboard

Live web view at `http://localhost:8765/` (or via Tailscale). Auto-refreshes every 5s.

Shows:
- Stats row: total / open / wins / losses / win rate / net P/L / total R / avg R
- By-pair grid: per-pair W/L/total/net/realized-R-sum
- Trade cards: each trade with direction, entry/SL/TP, R:R, quality, gates that passed, plain-English `explain`, outcome (open / win / loss with profit and realized R)

Read-only — no order placement from the web view.

---

## Safety model

| Layer | Mechanism |
|---|---|
| Default mode | Alerts-only — no order placement at all |
| Order placement (when enabled) | Goes through `mt5 order ready-limit` which already enforces: READY status + initial dry-run + setup refresh + entry-drift check + immediate dry-run + risk.py |
| Per-pair dedup | `active_strategies()` blocks a second placement on a (symbol, magic) that already has an open position OR pending order |
| Global cap | `max_concurrent_positions` counts both open positions AND pending orders |
| Daily cap | `max_trades_per_day` |
| Live intent | Only flows when `mt5_cli.live=true` AND `--live` flag inheritance |
| Demo-default | `mt5_cli.live=false` by default |
| Dashboard | Binds `127.0.0.1` only; `0.0.0.0` would expose on LAN |
| E2E test | `python test_e2e.py` refuses without `--allow-live`; refuses to flip `live` on its own |

---

## Trading.com specifics

This POC is built against Trading.com US, a CFTC/NFA-regulated retail broker. Constraints (encoded in `skills/trading.com/SKILL.md`):

- **FOK-only filling** (`auto` auto-selects FOK)
- **Netting + FIFO** — only 1 position per (symbol, magic) at a time
- **1:50 leverage** cap on majors
- **Spread-only commission**
- **Rollover at 22:00 UTC** — spreads spike, agent has rollover guard

Magic numbers are auto-derived from `strategy_id` via the CLI's SHA-256 formula:
```
magic = int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000
```
Range: `[100000, 180000)`. The 11 POC magics are pinned in MT5's `AdaptiveTrailEA.set` preset so EA trail management survives terminal restart.

---

## Known limits

| Limit | Detail |
|---|---|
| **SL too tight on JPY crosses** | `min_stop_points: 80` = 8 pips, but JPY crosses see 3-5 pip spreads + 5+ pip wicks routinely. Consider raising to 150 (15 pips) for JPY crosses specifically. |
| **No news filter** | Agent will alert into NFP/CPI/FOMC. Operator must check the calendar manually. |
| **No M5 swept-high alternative** | Sniper-poc is M1-FVG only. The Photon framework also takes M5 sweep entries when M15 structure is ambiguous; not implemented. |
| **active_strategies includes all magics** | Counts ALL pending orders + positions on the account, not just our 11 POC magics. If you run other strategies on the same account, they consume our cap. |
| **3-day history window** | `recent_deals(days=3)` won't resolve outcomes for trades held longer than 3 days. |
| **No prompt versioning** | Future LLM A/B comparison would need a `prompt_version` field on placements. |
| **No crash-recovery replay** | If agent crashes with open journal placements, restart only checks last 3 days of deals against current positions; doesn't replay orphans. |

---

## Test infrastructure

```powershell
# Unit tests for the underlying CLI (216 tests):
python -m pytest metatrader5_cli/mt5/tests/test_core.py -q

# End-to-end test against the real broker (places real micro-lot orders):
cd adaptive-forex-mt5
python test_e2e.py --allow-live
```

The e2e test verifies:
1. Magic-derivation parity for all 11 pairs (no broker action)
2. Active-strategy guard — places one far pending limit, verifies `active_strategies()` reflects it, asserts the per-pair guard predicate
3. Outcome attribution — places market-buy 0.001, injects synthetic placement, closes via CLI, calls only `agent.resolve_outcomes()`, asserts journal records the outcome with profit/swap/commission/net/realized_r

---

## Audit trail

Five rounds of code review during initial build (2026-05-07 / 2026-05-08), all in `docs/code-reviews/codex-adaptive-forex-mt5-*.md`:

- `7405ca1` initial POC
- `f583d88` outcome attribution + runtime perimeter
- `c019720` per-pair concurrency, full reasoning, R metrics
- `c614fff` e2e safety, stats, drift_points, concurrency
- `ff73a59` final blockers closed → **Green for supervised demo**
- `c3dedd2` production fix: position list/show now exposes `magic` (was the cause of duplicate-placement risk)

---

## Resuming work / handoff

Project state is captured in auto-memory at `~/.claude/projects/.../memory/project_adaptive_forex_mt5.md`. New Claude Code sessions at the master path auto-load it.

```powershell
cd C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI
claude
# then: "continue the adaptive-forex-mt5 work"
```

## Process layout (phase 1)

Three Python processes plus one persistent reviewer agent:

```powershell
cd C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\adaptive-forex-mt5
Start-Process powershell -ArgumentList '-NoExit','-Command','python dashboard.py'
Start-Process powershell -ArgumentList '-NoExit','-Command','python agent.py'
Start-Process powershell -ArgumentList '-NoExit','-Command','python trade_manager.py'
```

Then register the reviewer agent (one-time):

```powershell
ehukaiconnect agent create ClaudeReviewer --skill .ehukaiconnect/skills/ClaudeReviewer/SKILL.md
```

Launch the reviewer terminal per your ehukaiconnect platform docs; it reads
its skill and waits for `dispatch_wake` events on `trade_review-*` tasks.

## Trade manager (replaces AdaptiveTrailEA for our magics)

`trade_manager.py` runs a 1-second loop:

1. Heartbeat upsert to `state.db`.
2. List MT5 positions, filter to the poc-magic set
   (derived from `cfg.pairs` + `cfg.agent.strategy_id_prefix`).
3. For each: bootstrap from `trades.jsonl`, infer stage from the current SL,
   then run BE-move (R-based, 0.80R default) → Chandelier trail
   (ATR(22)x3.0 on M5).

Manual trades (magic=0) are NEVER touched by the manager. Phase 3 will add
an explicit allowlist for adopting them.

The manager is **fail-closed**: a poc-magic position with no journal placement
record is logged as `kind=unmanaged_poc_position` (rate-limited to once per
ticket per minute) and left alone. The dashboard surfaces a red banner so
silent failures are visible.

The modify pipeline is **confirm-before-promote**: `last_sl_set` is only
written after MT5 confirms `position.sl == requested_sl`. If a broker call's
ack is lost, the next loop re-reads position state first; if MT5 is already
at the requested SL, the row is promoted with no second broker call.
Cooldown-elapsed retries reuse the same `idempotency_key` so a delayed ack
cannot land twice.

## LLM review pipeline (advisory only)

On every READY alert, `agent.py`:

1. Computes a `setup_fingerprint` over the deterministic setup
   (pair, direction, entry/sl/tp, POI bounds/id, structure event, bar time).
2. Writes the alert payload to
   `.ehukaiconnect/shared/files/alerts/<alert_id>.json`.
3. Creates an `ehukaiconnect` task assigned to `ClaudeReviewer`.

The reviewer wakes, runs `mt5 --json analyze topdown` + `mt5 --json rates`
+ optional screenshots, and emits a verdict
(`take` / `skip` / `adjust`) into
`.ehukaiconnect/shared/files/verdicts/<alert_id>-claude.json`.

`agent.py` polls closed `trade_review-*` tasks each scan, journals
`kind=llm_verdict`, and pushes an enriched ntfy.

**Reviewer verdicts are advisory.** They never modify orders directly. Phase 2
adds a two-of-two consensus auto-trade lane on top of this foundation.

## Phase-2: Autopilot consensus mode

**Status:** infrastructure built; master flag `autopilot.enabled` defaults
**OFF**. The pipeline runs in shadow mode whenever review is enabled — both
reviewers vote on every alert and `kind=consensus_verdict` is journaled
for calibration — but no trades are placed until the operator explicitly
flips the flag after weeks of shadow data prove the consensus reliable.

### Two reviewers (different model families)

```powershell
ehukaiconnect agent create CodexReviewer --skill .ehukaiconnect/skills/CodexReviewer/SKILL.md
```

Plus the existing `ClaudeReviewer`. Run each in its own terminal so the
ehukaiconnect dispatcher can wake both on every `trade_review-*` task.

### What happens on a READY alert (autopilot OFF — current default)

1. agent.py stamps `setup_fingerprint` and `alert_id`, journals
   `kind=ready_alert`, writes payload to `.ehukaiconnect/shared/files/alerts/`.
2. Two `trade_review-*` tasks are created in parallel — one for each
   reviewer agent.
3. Each reviewer wakes, runs `mt5 --json analyze topdown` etc., writes a
   verdict to `.ehukaiconnect/shared/files/verdicts/<alert_id>-{claude,codex}.json`,
   closes the task.
4. agent.py polls done tasks, journals `kind=llm_verdict` and pushes
   enriched ntfy.
5. agent.evaluate_pending_consensus joins by `alert_id`, computes
   strict 2-of-2 consensus, journals `kind=consensus_verdict`.
6. Because `autopilot.enabled=false`, that's it. No broker action.

### What changes when you flip `autopilot.enabled=true`

After step 5, the executor runs 12 fail-fast gates:

1. autopilot.enabled
2. kill_switch != on
3. consensus.consensus == take
4. pair in autopilot.pair_allowlist
5. alert age <= max_alert_age_seconds
6. setup_fingerprint matches OR each level drift <= max_entry_drift_points
7. cfg.mt5_cli.live (no broker call without it)
8. spread <= max_spread_points
9. news.is_blackout_active is False (fails closed when news_source is null)
10. lot_size > 0
11. daily_trade_cap not exceeded; daily_loss_cap_usd not exceeded
   (counts AUTOPILOT placements only — manual trades don't count)
12. (pair, magic) not already in active_strategies

On all-pass it places via:

```
mt5 --live --json order limit <PAIR> <DIR> --price <ENTRY> --sl <SL> --tp <TP> --volume <V> --magic <M>
```

Crucially, `<ENTRY>`, `<SL>`, `<TP>` are the EXACT levels stored on the
ready_alert when it fired — never re-evaluated, never reviewer-adjusted.

### Kill-switch

To halt autopilot from anywhere:

```
ehukaiconnect send-to 0 --from operator "AUTOPILOT ABORT"
```

agent.py polls the bus each scan; on detection it flips
`state.db.cursor.autopilot_kill = "on"` and journals `autopilot_kill`.
The dashboard shows the kill-switch state with a red pill when on.

### Pre-flight before flipping `autopilot.enabled` to true

- Wire a real news source (the default `news_source: null` fails ALL
  autopilot gates by design).
- Confirm shadow `consensus_verdict` records show `consensus=take` rate
  matching your expectations on the dashboard.
- Verify `cfg.mt5_cli.live=true` AND points at a DEMO account first.
- Set `pair_allowlist` to the single pair you want to test on.
- Confirm `daily_trade_cap`, `daily_loss_cap_usd`, `lot_size`.

## Phase-3: Manual-trade adoption (allowlist)

By default the trade manager only touches positions whose magic is in the
poc-set (phase-1 invariant). To hand a manual-magic-0 position to the bot
for BE+Chandelier trail, add it to `managed_positions.json`:

```json
[
  {
    "ticket": 204841232,
    "symbol": "GBPJPY",
    "account": 9999,
    "mode": "trail_only",
    "be_r": 0.80,
    "trail_model": "chandelier_atr22_3.0",
    "expires_at": "2026-05-15T00:00:00Z",
    "operator_note": "GBPJPY manual long, hand to bot for trail"
  }
]
```

See `managed_positions.example.json` for the full schema. The actual file
is gitignored.

### Behavior

- Missing file = no adoptions (safe default).
- `expires_at` in the past = entry filtered out.
- Missing required fields, malformed JSON, or non-list root = silently
  ignored (operator can fix and reload).
- Each adoption logs `kind=adoption` (audit) and synthesizes a
  `kind=placement` (with `adopted=true`) so the existing trade-manager
  bootstrap path can ticket-match without an agent placement record.
- Synthesis is **idempotent** — re-running the manager loop on the same
  allowlisted ticket does NOT duplicate the placement.

### What the bot does to an adopted trade

Same as a poc-magic trade — BE move at the configured `be_r`, then
Chandelier trail with the configured `trail_model`. The operator's
existing SL is the starting `initial_sl`; the manager only ever
TIGHTENS, never loosens.

### Removing a trade from adoption

Either set `expires_at` to a past time, or delete the entry from
`managed_positions.json` and restart `trade_manager.py`. The state.db row
becomes a no-op once the position closes (manual or by trailed SL hit).
