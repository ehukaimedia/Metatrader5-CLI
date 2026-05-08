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
