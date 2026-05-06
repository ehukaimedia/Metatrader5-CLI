# Autonomous Trading Runtime — Design Spec

**Date**: 2026-04-24
**Status**: DRAFT — awaiting operator review
**Scope**: Self-contained, host-agnostic Python runtime for fully autonomous trading via the MT5-CLI core library. Drops into any repo or daemon host.

**Depends on**: `Metatrader5-CLI/docs/specs/mt5-cli-spec.md` (v0.4+). All MT5 interaction — orders, positions, rates, ticks, account state — flows through `metatrader5_cli.mt5.core.*`. This spec never references the `MetaTrader5` package directly.

**Target broker (initial)**: Trading.com US. Broker-specific constraints (FOK filling, FIFO, no hedging, leverage) are enforced by the MT5-CLI layer; adding a new broker is a MT5-CLI config change, not a strategy change.

**Reference strategy**: USDJPY "Gopher Gate" (4-gate trend-following with ATR trail). Strategy logic is isolated in one module (`strategy.py`) and swappable. This spec documents Gopher Gate as the reference implementation; the runtime itself is strategy-agnostic.

**Revision history**:
- v1 (2026-04-24): Initial spec, tied to one host (ehukai daemon) and @opus's `ehukai/trading/` module
- v2 (2026-04-24): Post-review fixes — pip value math, VLM provider, equity floor behavior, dry-run simulation, missing gate rules, threading model, trail formula, retcode handling, disconnect state, circular dep prevention, historical backtest phase
- v3 (2026-04-24): Execution substrate swapped to MT5-CLI core layer
- v4 (2026-04-24): **Host-agnostic rewrite.** Runtime is now a standalone package that any agentic team can embed. All host-specific touchpoints (alert transport, control transport, data directory, operator identity) are defined as integration interfaces in §3.5.
- v5 (2026-04-24): Post-audit fixes — two-thread architecture (analysis + monitor) to prevent VLM starving the monitor, `cli.order.poll_fill` now formally exists in CLI spec §6.7, spread invariant direction fixed + default tightened to match CLI floor, dry-run now calls `order.dryrun()` first to exercise CLI risk envelope, `strategy_factory` and `vlm_client` added as injection points, pid-file single-instance lock, explicit news_calendar-missing alert, explicit VLM failure/retry policy, ATR source shown as `indicator.atr()` call.

---

## 1. Purpose & Non-Goals

### Purpose

A fully autonomous trading runtime that:

- Runs multi-timeframe chart analysis on a scheduled cadence
- Enters, manages (trail SL, move to BE), and exits positions without operator action
- Enforces session-level safety gates layered on top of the MT5-CLI's per-order risk envelope
- Journals every decision — fills, no-ops, and gate blocks — for end-of-session review

The runtime is **self-contained**: zero dependencies on any specific host, chat platform, message bus, or operator identity. Integration with a host happens through four well-defined interfaces (§3.5). A host can be a daemon, a cron job, a web service, an agent harness — anything that can hold a long-running Python thread.

### Non-Goals (POC scope)

- **Not multi-symbol** in this revision. The runtime is single-symbol per instance (USDJPY for the reference implementation). Run multiple instances for multiple symbols.
- **Not multi-strategy within one instance.** Gopher Gate is the reference. Other strategies subclass `StrategyEngine` and swap the module; the orchestrator, gates, and manager are strategy-agnostic.
- **Not a black box.** Every decision is journaled with the gate evaluations that produced it.
- **Not a signal service.** No external webhooks, Telegram pushes, or Slack hooks are built in. Wire one via the alert transport interface (§3.5) if needed.

---

## 2. Reference Documents

| Document | Role |
|---|---|
| `Metatrader5-CLI/docs/specs/mt5-cli-spec.md` | **Execution substrate.** `metatrader5_cli.mt5.core.*` is imported directly as a library. The CLI's `core/risk.py` is the hard floor for per-order checks. |
| Gopher Gate strategy reference (external, strategy-specific) | Source of truth for G1–G4 gate logic, SL rules, trail rules, dead zones, hard-won lessons. The strategy engine codifies this document into executable checks. Supply your own document for a different strategy. |

---

## 3. Architecture

The runtime runs **two dedicated Python threads** and exposes six integration points to whatever host embeds it:

- **`analysis_thread`** — 15-min cadence in active windows; drives strategy + gates + order placement; dispatches VLM calls (blocks on `.result()` for 10–30s is acceptable here because this thread only does analysis)
- **`monitor_thread`** — 5-sec cadence while `IN_TRADE`; reads live ticks, applies trail/exit logic via `manager.py`; never blocks on VLM or analysis

The two threads share state through threadsafe primitives (`threading.Event` for state transitions, `queue.Queue` for fill notifications from analysis → monitor). This pattern prevents a slow VLM call from starving the position monitor — a problem if both loops shared one thread.

```
┌──────────────────────────────────────────────────────────────┐
│                       Host Process                           │
│  (any daemon / service / agent harness)                      │
│                                                              │
│  provides: alert_transport, control_transport, data_dir,     │
│            optional watchdog callback                        │
│                                                              │
│  ┌─ Host watchdog (optional) ─────────────────────────────┐ │
│  │  polls runtime.last_tick on host's preferred cadence   │ │
│  │  alerts if stale                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─ Autonomous Trading Runtime ───────────────────────────┐ │
│  │                                                         │ │
│  │  Thread 1: analysis_thread (15-min tick, active window) │ │
│  │  ┌──────────────┐     ┌────────────────────────────┐   │ │
│  │  │ Strategy     │────►│ Session-level Gate Layer   │   │ │
│  │  │ Engine       │     │ (gates.py, stateful)        │   │ │
│  │  │ (strategy.py)│     └────────────────────────────┘   │ │
│  │  └──────────────┘                                      │ │
│  │      may block 10-30s on VLM; isolated from monitor    │ │
│  │                                                         │ │
│  │  Thread 2: monitor_thread (5s tick, IN_TRADE only)    │ │
│  │  ┌──────────────────────────────────────────────┐     │ │
│  │  │  Position Manager (manager.py)               │     │ │
│  │  │  trail SL / BE / rollover / exit detection   │     │ │
│  │  │  never blocks on VLM; reads flags each tick  │     │ │
│  │  └──────────────────────────────────────────────┘     │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                   │
│  ┌───────────────────────▼──────────────────────────────┐   │
│  │  Runtime-owned modules (local to this package)       │   │
│  │  journal.py   (decision logging, JSONL)              │   │
│  │  orchestrator.py   (state machine, tick scheduler)   │   │
│  └───────────────────────┬──────────────────────────────┘   │
│                          │ imports (Python API)              │
│  ┌───────────────────────▼──────────────────────────────┐   │
│  │  MT5-CLI core layer (metatrader5_cli.mt5.core.*)        │   │
│  │  order.place_market / position.list / market.tick    │   │
│  │  rates.fetch / rates.range / history.stats           │   │
│  │  risk.py — per-order floor (max_lot, min_sl, spread) │   │
│  └───────────────────────┬──────────────────────────────┘   │
└──────────────────────────│──────────────────────────────────┘
                           │ singleton MT5 connection
                   ┌───────▼───────┐
                   │  MetaTrader 5 │
                   │  Trading.com  │
                   └───────────────┘
```

**Why a dedicated thread**: the analysis loop makes 10–30s VLM calls that must not block the 5-sec position monitor. The host's own loop is irrelevant to the runtime.

**Circular dependency prevention**: the runtime never imports any host module. All outbound communication is through the injected `alert_transport` callable. The host may optionally import the runtime read-only for status queries.

### 3.5 Host Integration Interfaces

The runtime exposes six integration points. Everything host-specific lives here; the rest of the runtime is pure logic.

**1. Alert transport** (required, pluggable callable)
```python
def alert_transport(text: str, severity: str) -> None: ...
#   severity ∈ {"info", "warn", "critical"}
```
The host supplies a callable the runtime invokes for all outbound communication: rollover warnings, MT5 disconnect notices, circuit-breaker trips, fill confirmations, etc. The runtime does not care whether this posts to a chat group, writes a log line, pushes a webhook, or sends an email. Default (if host supplies none): write to stderr.

**2. Control transport** (optional, pluggable)

Operator commands (`HALT`, `RESUME`, `STATUS`, `JOURNAL`, `GATES`, `PAUSE`, `UNPAUSE`) reach the runtime through whichever channel the host chooses:

| Channel | How the runtime receives it |
|---|---|
| File flag (always on) | Runtime polls `${data_dir}/HALT.flag`, `PAUSE.flag`, `DRY_RUN.flag` every monitor tick |
| HTTP endpoint | Host wires a route to `runtime.handle_command(cmd: str, args: dict)` |
| Stdin / named pipe | Host reads commands and calls `runtime.handle_command()` |
| Message bus / chat | Host parses incoming messages and calls `runtime.handle_command()` |

The file-flag channel is always available and is the minimum reliable kill path. All other channels are additive.

**3. Data directory** (configured via `AURUM_DATA_DIR` env var, default `~/.autotrader/`)

The runtime writes to:
- `${AURUM_DATA_DIR}/journal.jsonl` — append-only decision log
- `${AURUM_DATA_DIR}/HALT.flag`, `PAUSE.flag`, `DRY_RUN.flag` — control flags
- `${AURUM_DATA_DIR}/news_calendar.json` — operator-maintained news blackout windows

Host sets `AURUM_DATA_DIR` to whatever path convention fits. The runtime creates the directory if missing.

**4. Optional watchdog callback**

The runtime exposes `runtime.last_analysis_tick` and `runtime.last_monitor_tick` as threadsafe timestamps. The host can poll these and alert on staleness using its own watchdog cadence. The runtime does not provide its own watchdog — that's the host's job if it wants one.

**5. Strategy factory** (optional, for non-default strategies)
```python
strategy_factory: Callable[[dict], StrategyEngine]
```
The host can inject an alternate strategy implementation. Default: the Gopher Gate engine bundled in `autotrader.strategies.gopher_gate`. Runtime calls `strategy_factory(config)` at start and uses the returned `StrategyEngine` for all analysis ticks. Swapping strategies requires no code edits to the runtime.

**6. VLM client** (optional, for custom LLM integration)
```python
vlm_client: Callable[[list[str]], BiasResult]
#   input: list of screenshot file paths (6 timeframes)
#   output: BiasResult dict
```
If the host has its own LLM client, secrets management, or a non-Claude VLM backend, it supplies the callable here. Default: built-in Claude API client using `AURUM_VLM_MODEL` and `ANTHROPIC_API_KEY` env vars.

### Single-instance lock (pid-file)

On start, the runtime writes `${AURUM_DATA_DIR}/runtime.pid` with its pid and an exclusive file lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). If the lock is already held by a live pid, the runtime refuses to start with error `ALREADY_RUNNING`. The pid-file is cleaned up on graceful shutdown; stale pid-files from crashed processes are detected by checking if the pid still exists and are cleared automatically.

This prevents two runtime instances accidentally sharing the same `AURUM_DATA_DIR` (which would race on journal writes and double-adopt open positions). To run multiple strategies concurrently, use different `AURUM_DATA_DIR` paths per instance.

### Operator identity

The runtime has no concept of a specific operator or agent name. Alerts identify the runtime as `autotrader/<symbol>/<strategy_id>` (e.g. `autotrader/USDJPY/gopher-gate-v1`). If the host wants to attach a human name, it does so in the `alert_transport` it supplies.

---

## 4. State Machine

One state active at a time.

```
HALTED ◄──── HALT command / circuit breaker / 3× consecutive MT5 failures (any state)
  │
  │ runtime start + MT5 healthy + no HALT flag
  ▼
IDLE
  │
  │ analysis window opens + tick fires
  ▼
ANALYZING
  │ 6-TF screenshots captured, gates evaluated
  │
  ├── no signal / gates not GREEN ──► IDLE (log NO_TRADE + reason)
  │
  ▼
PROPOSED
  │ trade proposal journaled
  │ session-level gate layer evaluated (all 13 gates)
  │
  ├── any gate blocks ──► IDLE (log BLOCKED + gate name)
  │
  ▼
EXECUTING
  │ metatrader5_cli.mt5.core.order.place_market(..., strategy_id="gopher-gate-v1")
  │ CLI envelope: {"ok": True/False, "data": {...}, "error": {...}}
  │
  ├── ok=True, retcode 10009 (filled) ──────────────────► IN_TRADE
  ├── ok=True, retcode 10008 (placed, fill pending)
  │       └── poll cli.order.poll_fill(ticket) up to 5s
  │               ├── confirmed fill ──────────────────► IN_TRADE
  │               └── not filled within 5s ──► cancel + IDLE (log TIMEOUT)
  ├── ok=False, code=RISK_* (CLI floor rejected) ──► IDLE (log BLOCKED_BY_CLI)
  ├── retcode 10027 (algo trading disabled) ─────────► HALTED
  ├── retcode 10006/10004 (rejected/requote) ──► IDLE (log REJECTED)
  └── any other retcode / ok=False ──────► IDLE (log error, no retry)
  │
  ▼
IN_TRADE
  │ position open; position monitor inner loop (5s) active
  │ cli.account.info() liveness check each monitor tick
  │
  ├── account.info() returns ok=False (connection lost)
  │       └── increment fail_count; state → DISCONNECTED
  │
  ▼
DISCONNECTED  (connection lost while position open)
  │ do NOT close position (broker auto-manages SL/TP server-side)
  │ do NOT transition to EXITED (cli returning empty != position closed)
  │ alert_transport("MT5 disconnected — position status unknown", "critical")
  │ retry cli.account.info() every 10s
  │
  ├── reconnect within 90s ──► IN_TRADE (run recovery, resume monitor)
  └── fail_count ≥ 3 (after 90s total) ──► HALTED
  │
  ▼
MANAGING
  │ SL trail fired (BE at +10p, structural trail at each key level)
  │ back to IN_TRADE until exit condition
  │
  ▼
EXITED
  │ position closed (TP hit / SL hit / kill switch / rollover close)
  │ journal updated, session P/L recalculated
  │ gates re-evaluated (loss streak check)
  │
  └──► IDLE (or HALTED if circuit breaker trips)
```

### Tick cadence

| Window | Cadence | Activity |
|---|---|---|
| 00:00–03:00 UTC (Tokyo) | Every 15 min | Full analysis tick |
| 07:00–10:00 UTC (London) | Every 15 min | Full analysis tick |
| 10:00–22:00 UTC (off-peak) | Every 60 min | Watchdog heartbeat only; no entries |
| 22:00–00:00 UTC (dead zone) | No ticks | Hard block on entries |
| IN_TRADE / MANAGING / DISCONNECTED | Every 5s | Position monitor inner loop |

Cadence windows are configured via `AURUM_ACTIVE_SESSIONS` — Gopher Gate's defaults are shown above.

---

## 5. Strategy Engine (`strategy.py`)

Codifies the Gopher Gate System into executable logic. Inputs are 6-TF chart analysis + MT5 tick data (via MT5-CLI core). Output is a `TradeProposal` or `NoTrade`.

### 6-TF Analysis

1. Invoke a screenshot capture subprocess (bundled tool or user-supplied) for D1 → H4 → H1 → M15 → M5 → M1
2. Submit each screenshot to a **VLM backend** via `urllib.request` in a `concurrent.futures.ThreadPoolExecutor` (stdlib):
   - Trend direction (BULL / BEAR / NEUTRAL)
   - Key S/R levels within 100 pips of current price
   - FVG zones visible
   - Active OB zones
3. Synthesize into `BiasResult`: direction, confidence (0–100), key levels list

**VLM backend**: configured via `AURUM_VLM_BACKEND` env var (default: Claude API via direct HTTP). Pluggable — any callable returning the expected JSON schema works. Do not use quota-limited secondary channels (e.g. chat-panel integrations capped at N calls/day); at 6 TFs × 4 ticks/hr × 10hr window = 240 calls/day, any cap below ~500/day is unsafe.

**VLM failure handling**:
1. Each timeframe submission has a 60s timeout; on timeout, retry once with 2x backoff (120s)
2. If a TF still fails after retry: log `VLM_PARTIAL` and mark that TF's bias as `UNAVAILABLE` in the synthesis. Strategy evaluation accepts partial coverage only if D1+H1+M5+M1 are all available; H4 and M15 are nice-to-have. If any required TF is `UNAVAILABLE`, the tick aborts with outcome `VLM_FAILED` and transitions to IDLE.
3. 429 rate-limit responses: exponential backoff with jitter (2^n + random(0,1) seconds, max 60s); retry up to 3 times then abort tick
4. HTTP 5xx: treated same as timeout
5. Missing/invalid API key at startup: hard refuse to start, error `VLM_CREDENTIALS_MISSING`

### Gate Evaluation

All four gates must score GREEN. Any RED = `NoTrade`.

| Gate | Check | GREEN condition |
|---|---|---|
| G1 — M1 structure | M1 higher low at support (buy) or lower high at resistance (sell), confirmed on last 3 M1 bars. **Reject if the pattern is a wick-only spike not confirmed by M5 body close** — M1 spikes above OB/FVG zones are often stop hunts, not valid G1 signals. | Body-confirmed pattern on M1; M5 last closed bar does not reverse the signal |
| G2 — M5 momentum | Last closed M5 bar body closes beyond trigger zone (buy: above; sell: below). Wick touches do not count. | M5 body close beyond zone |
| G3 — H1 trend | H1 not making lower highs (buy) or not making higher lows (sell). | H1 aligned with bias |
| G4 — Liquidity grab guard | At support (for sells): 3+ wicks below the level without a clean M5 body close below = institutional stop hunt zone, do NOT sell into it. Either buy the wick reversal (if bias flipped) or wait for M5 body close below the entire zone. Mirror rule for buys at resistance. | For sells: <3 wicks below support without M5 close-through; for buys: <3 wicks above resistance without M5 close-through |

### Entry Parameters

```python
@dataclass
class TradeProposal:
    symbol: str
    side: str                 # "buy" | "sell"
    volume: float             # from risk calculator
    entry_price: float
    sl: float
    tp: float
    rr_ratio: float           # must be >= AURUM_MIN_RR
    gate_scores: dict         # {"G1": "GREEN", ...}
    bias_confidence: int      # 0–100
    strategy_id: str          # "gopher-gate-v1"
    key_levels: list          # structural levels used for trail planning
    reason: str               # for journal
```

### Risk Calculator

All MT5-derived values come from the MT5-CLI core layer — never hardcoded.

```python
from metatrader5_cli.mt5.core import account, market

equity     = account.info()["data"]["equity"]
sym        = market.info(symbol)["data"]
pip_size   = sym["pip_size"]           # 0.01 for USDJPY, 0.0001 for EURUSD
tick_value = sym["trade_tick_value"]   # account-currency value per tick per 1.0 lot

risk_pips = abs(entry_price - sl) / pip_size
volume    = (equity * AURUM_RISK_PCT) / (risk_pips * tick_value)
volume    = round(min(volume, AURUM_MAX_LOT), 2)
volume    = max(volume, 0.01)
```

Alternatively, pass `--risk-pct` to `order.place_market()` and let the CLI core compute volume — both paths call the same code in `metatrader5_cli.mt5.core.risk`.

### SL Placement Rules

- **Structural level** = the key S/R zone price is expected to cross through (the zone itself, not entry price or M5 close price)
- Initial SL = `structural_level ± (AURUM_ATR_MULTIPLIER × M5_ATR14 × pip_size)`
- Never place SL below 1.5× M5 ATR (tighter SLs get wicked out)
- For sells: SL above the **full wick high** of the G1 pattern + ATR buffer (the body high sits inside a known liquidity cluster; stops there will be hunted)
- Mirror rule for buys
- SL rounded to symbol digits (USDJPY 3-digit precision)
- CLI rejects SL == entry; use `entry ± 0.005` if SL rounds to entry

---

## 6. Session-Level Gate Layer (`gates.py`)

Evaluated before every `PROPOSED → EXECUTING` transition AND at runtime start. All gates are hard blocks. Every evaluation (pass or block) is written to the journal.

### Relationship to MT5-CLI risk envelope

The MT5-CLI's `core/risk.py` is the **per-order floor**: stateless, enforces `max_lot_per_order`, `min_sl_distance_points`, `max_spread_points`, FIFO/no-hedge, demo/live gate, and symbol allowlist on every order.

This layer is the **session-level ceiling**: stateful checks the CLI cannot make (consecutive losses, session-start equity, daily loss cap, dead zone window, news blackout). These run **before** the CLI call.

**Layering invariant**: session gates never relax the CLI floor — only tighten it (for rejection thresholds, "tighten" = reject at a stricter value). For every overlap:
- `AURUM_MAX_LOT` (default 1.5) ≤ CLI `max_lot_per_order` (default 2.5)
- `AURUM_MAX_SPREAD_PIPS × 10` (default 30 points, converted from 3.0 pips on 3-digit broker) ≤ CLI `max_spread_points` (default 80) — session rejects at or below CLI threshold
- Session min SL distance ≥ CLI `min_sl_distance_points` (session demands a wider-or-equal SL)

Runtime **asserts these invariants at start** by reading the CLI config (`metatrader5_cli.mt5.core.project.config()`) and comparing. Any violation is a hard startup error.

If the CLI rejects with a `RISK_*` error, log it to the journal as `BLOCKED_BY_CLI` and transition to IDLE — never retry with relaxed parameters.

### Gate table

| Gate | Default | Env var | Behavior on breach |
|---|---|---|---|
| Dead zone | 22:00–00:00 UTC | `AURUM_DEAD_ZONE_START` / `AURUM_DEAD_ZONE_END` | Block new entries; existing positions managed normally |
| Max spread | 3.0 pips (= 30 points on 3-digit broker) | `AURUM_MAX_SPREAD_PIPS` | Block entry; log spread value. Must be ≤ CLI `max_spread_points` / 10 |
| News blackout | ±15 min around high-impact events | `AURUM_NEWS_BLACKOUT_MINS` | Block entry; events loaded from `${AURUM_DATA_DIR}/news_calendar.json`. **If file is missing on startup**: runtime logs `critical` alert via `alert_transport` ("news calendar missing — news-blackout gate is INACTIVE") and continues with the gate disabled. Operator must create the file; runtime never silently skips without emitting the alert. |
| Daily loss cap | -$1500 | `AURUM_DAILY_LOSS_CAP_USD` | Block new entries until midnight UTC auto-reset; does NOT close open positions |
| Consecutive loss breaker | 3 sequential losses | `AURUM_MAX_CONSECUTIVE_LOSSES` | Block new entries; requires RESUME + manual HALT.flag deletion (does NOT auto-reset) |
| Equity floor — soft | 95% of session-start equity | `AURUM_EQUITY_FLOOR_PCT` | Block new entries only; current position managed to completion |
| Equity floor — hard | 90% of session-start equity | `AURUM_EQUITY_HARD_FLOOR_PCT` | Close all positions immediately + HALT; write HALT.flag; requires RESUME |
| Max concurrent positions | 1 | `AURUM_MAX_POSITIONS` | Block new entry while any position open |
| Max trades per session | 5 | `AURUM_MAX_TRADES_SESSION` | Block new entries for remainder of session; resets midnight UTC |
| Max lot size | 1.5 | `AURUM_MAX_LOT` | Cap volume; scale down, never reject outright |
| Algo trading enabled | — | — | CLI retcode 10027: HALT, write HALT.flag, `alert_transport(..., "critical")` |
| Margin level | > 200% | `AURUM_MIN_MARGIN_PCT` | Block new entries if margin level below threshold |
| Kill switch — command | Operator sends `HALT` via control transport | — | Close all positions + HALT immediately |
| Kill switch — file | `${AURUM_DATA_DIR}/HALT.flag` exists | — | Close all positions + HALT; checked every monitor tick |

### Simultaneous breach priority

1. Hard equity floor (90%) always wins — close positions + HALT regardless of other gates
2. Kill switch (command or file) always wins over all automated gates
3. All other gate breaches are logged together; the most restrictive (HALT > block) applies
4. Daily loss cap resets midnight UTC automatically. Consecutive-loss and hard equity floor do NOT auto-reset — both require RESUME (manual acknowledgment by design).

### Resuming from halt

Operator sends `RESUME` via control transport, or deletes `HALT.flag`. The runtime verifies current equity and gate conditions before re-entering IDLE. If the original breach condition still holds, it re-blocks immediately and emits a `critical` alert.

---

## 7. Position Manager — Trail & Exit Automation (`manager.py`)

5-second inner loop while state is `IN_TRADE`, `MANAGING`, or `DISCONNECTED`.

### Breakeven trigger

- At entry +`AURUM_BE_PIPS` pips (default +10p): move SL to `entry ± 0.005`
- One-way only: never move SL against the trade

### ATR-based structural trail

On confirmed M5 body close beyond a key structural level:

```python
from metatrader5_cli.mt5.core import indicator

atr_resp = indicator.atr(symbol, "M5", period=14, bars=1)
m5_atr14 = atr_resp["data"]["values"][-1]["atr"]   # in price units (e.g. 0.076 for 7.6 pips USDJPY)

new_sl = structural_zone_boundary + (AURUM_ATR_MULTIPLIER * m5_atr14 * direction_sign)
```

Where:
- `structural_zone_boundary` = the key S/R zone price, not the M5 close price
- `direction_sign` = +1 for sell (SL trails above), -1 for buy (SL trails below)

Trail fires only when:
1. M5 body (not wick) closes cleanly beyond the structural zone
2. `new_sl` improves on current SL (profit direction only)
3. Within 15 min of 22:00 UTC: widen by additional 15 pips (rollover protection)

Key levels are passed in `TradeProposal.key_levels` from the strategy engine.

### Rollover guard (22:00 UTC)

- 21:45 UTC: `alert_transport("ROLLOVER in 15 min — monitoring spread", "info")`
- 21:55 UTC: if `ask - bid > 3 × baseline_spread`: close position at market; log `ROLLOVER_CLOSE`
- 22:05 UTC: resume normal management if position still open

### Exit conditions (priority order)

1. Kill switch (immediate market close)
2. Hard equity floor breach (market close all)
3. SL hit (CLI-reported ticket absence from `position.list()`)
4. TP hit (same detection)
5. Rollover spread spike at 21:55 UTC
6. Dead zone: no forced close; manage through

---

## 8. Recovery & Watchdog

### Runtime restart mid-trade

On `runtime.start()`:
1. Call `metatrader5_cli.mt5.core.position.list()` — if open positions exist not tracked in local state:
   a. Search `journal.jsonl` for the most recent `fill` event matching the ticket (or `strategy_id`)
   b. Restore `TradeProposal` (entry, sl, tp, key_levels, strategy_id) from that journal record
   c. Set manager state from live CLI position data (SL/TP may have been trailed since fill — live wins over journal)
2. Set state to `IN_TRADE`, start position monitor
3. Do NOT re-run strategy or gate evaluation — treat as already executing

If no fill journal record exists for an adopted ticket (e.g. opened outside this runtime): log warning, manage conservatively (trail only, no new entries until position exits).

### MT5 connection loss (mid-trade)

See `DISCONNECTED` state in §4. The MT5-CLI bridge auto-reconnects once transparently on disconnect (per CLI spec §14); if that fails, core functions return `{"ok": false, "error": {"code": "MT5_CONNECTION_ERROR"}}`. Key invariant: `position.list()` returning empty under `MT5_CONNECTION_ERROR` does NOT mean the position closed. Only transition to EXITED when connectivity is confirmed restored AND the ticket is absent from `position.list()`.

### Watchdog (host-side)

The runtime exposes `runtime.last_analysis_tick` and `runtime.last_monitor_tick` as threadsafe timestamps. The host polls these on its own cadence. Suggested thresholds:
- `now - last_analysis_tick > 3 × expected_cadence` → warn
- state is `IN_TRADE` and `now - last_monitor_tick > 30s` → critical (position unmanaged)

The runtime does not provide its own watchdog. If the host has no watchdog, the file-flag kill switch is still available.

---

## 9. Operator Controls

### Commands (received via control transport — §3.5)

| Command | Effect |
|---|---|
| `HALT` | Close all positions, write HALT.flag, transition to HALTED |
| `RESUME` | Verify gate conditions, clear HALT.flag if all pass, transition to IDLE |
| `STATUS` | Return current state, open positions, session P/L, active gate values (as structured dict) |
| `JOURNAL [N]` | Return last N journal entries (default 5) |
| `GATES` | Return all gate thresholds vs current live readings |
| `PAUSE` | Write PAUSE.flag (block new entries only) |
| `UNPAUSE` | Clear PAUSE.flag |

All commands return a dict; the host formats and delivers the response via its chosen channel.

### File-based controls (checked every monitor tick, always available)

| File | Effect |
|---|---|
| `${AURUM_DATA_DIR}/HALT.flag` | Hard halt + close all positions |
| `${AURUM_DATA_DIR}/PAUSE.flag` | Block new entries; positions managed normally |
| `${AURUM_DATA_DIR}/DRY_RUN.flag` | Dry-run mode (see below) |

### Dry-run mode

In dry-run, all logic executes including gate evaluation, VLM analysis, and trail/exit calculations. The execution path differs:

- Runtime first calls `metatrader5_cli.mt5.core.order.dryrun(...)` with the exact `TradeProposal` parameters. This runs the CLI risk envelope (`max_lot_per_order`, `min_sl_distance_points`, `max_spread_points`, FIFO/hedge, margin) and the broker-side `mt5.order_check()` pre-flight. If dry-run returns `ok=False`, the proposal is journaled as `BLOCKED_BY_CLI_DRYRUN` and the state returns to IDLE — exactly as a live order would behave.
- Only if `order.dryrun()` returns `ok=True` does the runtime create a `SimulatedPosition`:

```python
@dataclass
class SimulatedPosition:
    ticket: int              # synthetic negative ID
    symbol: str
    side: str
    entry: float
    sl: float
    tp: float
    volume: float
    open_ts: str
    current_sl: float        # updated by manager on trail triggers
    peak_profit_pips: float
    is_open: bool
```

- Position monitor's 5-sec loop queries live `market.tick()` for current bid/ask and applies trail/exit logic against `SimulatedPosition.current_sl`
- SL hit: detected when live bid (sell) or ask (buy) crosses `current_sl`
- TP hit: detected when live bid (sell) or ask (buy) crosses `tp`
- All events journaled with `"dry_run": true`

This validates the full state machine including trail logic and exit detection, not just entry decisions.

---

## 10. Journal

Append-only JSONL at `${AURUM_DATA_DIR}/journal.jsonl`.

### Decision record (every analysis tick — including no-ops)

```json
{
  "ts": "2026-04-24T01:00:00Z",
  "tick": "analysis",
  "state_before": "IDLE",
  "outcome": "NO_TRADE",
  "reason": "G2_RED: M5 not closed above trigger zone",
  "gate_evals": {
    "dead_zone": "PASS",
    "spread": "PASS (1.2p)",
    "daily_loss": "PASS (-$12.50 of -$100 cap)",
    "consecutive_losses": "PASS (1 of 3)",
    "equity_floor_soft": "PASS (99.8%)"
  },
  "bias": {"direction": "SELL", "confidence": 72},
  "gate_scores": {"G1": "GREEN", "G2": "RED", "G3": "GREEN", "G4": "GREEN"}
}
```

### Trade record (on fill or dry-run fill)

```json
{
  "ts": "2026-04-24T01:15:00Z",
  "event": "fill",
  "ticket": 204340000,
  "symbol": "USDJPY",
  "side": "sell",
  "volume": 0.15,
  "entry": 155.960,
  "sl": 156.074,
  "tp": 155.618,
  "rr_ratio": 3.0,
  "key_levels": [155.800, 155.600, 155.400],
  "strategy_id": "gopher-gate-v1",
  "dry_run": false,
  "equity_before": 10119.50,
  "gate_evals": {"dead_zone": "PASS", "spread": "PASS (1.1p)", "...": "..."}
}
```

### End-of-session review

`runtime.journal_summary(date="today")` returns:
- Session P/L, win/loss count, win rate
- Each trade: entry, exit, P/L, reason, gate scores, trail events
- Gate breaches that blocked entries (with counts and values)

---

## 11. Rollout Plan

### Phase -1 — Historical bar replay (before any live deployment)

1. Backtest harness replays bars via `metatrader5_cli.mt5.core.rates.range()` through the strategy engine and manager. Tick-precision replay available via `rates.ticks_range()`.
2. Feed historical M1/M5/H1/H4/D1 data over at least 3 months
3. Run gate logic against replayed bars; compare simulated decisions against known good/bad setups
4. Minimum signal: 20+ simulated trades before Phase 0

### Phase 0 — Live dry-run validation (1 week)

1. Deploy runtime with `DRY_RUN.flag` active
2. 5+ full trading sessions through active windows
3. Review journal: verify gate logic, SL placement, trail triggers, SimulatedPosition behavior
4. Zero unexpected decisions in a full session before Phase 1

### Phase 1 — Micro-lot live (1 week)

1. Remove `DRY_RUN.flag`
2. Set `AURUM_MAX_LOT=0.01`, `AURUM_RISK_PCT=0.001` (0.1% risk)
3. Validate execution path: fills, journal entries, trail execution, exit detection
4. Minimum signal: 5 live trades with correct behavior before Phase 2

### Phase 2 — Standard size

1. `AURUM_MAX_LOT=1.5`, `AURUM_RISK_PCT=0.01` (1% risk)
2. Full autonomous operation; operator reviews journal each session

---

## 12. Module Structure

```
autotrader/                    # host-agnostic package; drop into any repo
├── __init__.py                # Package init, platform guard (Windows for MT5-CLI);
│                              # startup checks via metatrader5_cli.mt5.core.account
│                              # (MT5 connected, algo trading enabled, demo when AURUM_LIVE=0)
├── journal.py                 # Append-only JSONL at ${AURUM_DATA_DIR}/journal.jsonl
├── orchestrator.py            # State machine, two-loop tick scheduler, flag watcher.
│                              # Accepts host-supplied alert_transport + control_transport.
│                              # All MT5 interaction via metatrader5_cli.mt5.core.*
├── strategy.py                # G1–G4 gate evaluation, TradeProposal, risk calculator.
│                              # Reference implementation = Gopher Gate; subclass
│                              # StrategyEngine to swap for a different strategy.
│                              # Imports: metatrader5_cli.mt5.core.{market, rates, account}
├── gates.py                   # Session-level gate layer (stateful). GateResult datatype.
│                              # Dual equity floor (soft 95% / hard 90%).
├── manager.py                 # Trail/exit automation, SimulatedPosition for dry-run,
│                              # rollover guard, structural level trail math (M5 ATR-based).
│                              # Imports: metatrader5_cli.mt5.core.{position, market, order, indicator}
├── runtime.py                 # Top-level entry: `Runtime(alert_transport, control_transport,
│                              # data_dir, config).start()`. What the host imports.
└── tests/
    ├── test_gates.py          # Session-gate unit tests (mocked CLI)
    ├── test_manager.py        # Trail/exit logic against synthetic price series
    ├── test_strategy.py       # G1–G4 evaluation with fixture screenshots + mocked VLM
    └── test_runtime_e2e.py    # Full state machine, dry-run mode, mocked CLI core
```

**Dependencies**: `metatrader5_cli` (the MT5-CLI package) is the only required runtime dependency. No dependency on any specific host daemon, message bus, or chat platform.

**VLM + screenshot capture**: bundled as `autotrader/tools/capture_6tf.py` (subprocess-invoked). Users can replace with their own capture tool by pointing `AURUM_CAPTURE_CMD` at a different executable.

---

## 13. Environment Variables — Full Reference

| Variable | Default | Description |
|---|---|---|
| `AURUM_SYMBOL` | `USDJPY` | Trading symbol |
| `AURUM_RISK_PCT` | `0.01` | Risk per trade as fraction of current equity |
| `AURUM_MAX_LOT` | `1.5` | Hard lot size cap (must be ≤ CLI `max_lot_per_order`) |
| `AURUM_MIN_RR` | `3.0` | Minimum risk:reward ratio |
| `AURUM_MAX_SPREAD_PIPS` | `3.0` | Max spread before blocking entry. Equals 30 points on a 3-digit broker (USDJPY), below the CLI `max_spread_points` floor |
| `AURUM_MAX_POSITIONS` | `1` | Max concurrent positions |
| `AURUM_MAX_TRADES_SESSION` | `5` | Max trades per session; resets midnight UTC |
| `AURUM_DAILY_LOSS_CAP_USD` | `1500.0` | Max daily loss ($) before blocking new entries |
| `AURUM_MAX_CONSECUTIVE_LOSSES` | `3` | Loss streak before halt (no auto-reset) |
| `AURUM_EQUITY_FLOOR_PCT` | `0.95` | Soft equity floor — block new entries only |
| `AURUM_EQUITY_HARD_FLOOR_PCT` | `0.90` | Hard equity floor — close all + HALT |
| `AURUM_MIN_MARGIN_PCT` | `200.0` | Min margin level (%) before blocking entries |
| `AURUM_NEWS_BLACKOUT_MINS` | `15` | Minutes before/after high-impact events |
| `AURUM_DEAD_ZONE_START` | `22` | Dead zone start hour (UTC) |
| `AURUM_DEAD_ZONE_END` | `0` | Dead zone end hour (UTC) |
| `AURUM_ACTIVE_SESSIONS` | `tokyo,london` | Comma-separated named session keys (see CLI `market sessions`) |
| `AURUM_ATR_MULTIPLIER` | `1.5` | SL trail ATR multiplier |
| `AURUM_BE_PIPS` | `10` | Pips in profit before breakeven trigger |
| `AURUM_DATA_DIR` | `~/.autotrader/` | Data directory (journal, flags, calendar) |
| `AURUM_VLM_BACKEND` | `claude-api` | VLM provider identifier |
| `AURUM_VLM_MODEL` | `claude-haiku-4-5-20251001` | Model ID for Claude API backend |
| `AURUM_CAPTURE_CMD` | bundled | Screenshot capture command (must emit JSON paths to stdout) |
| `AURUM_STRATEGY_ID` | `gopher-gate-v1` | Tag applied to all orders. The CLI resolves this to a magic int: either from the `strategy_ids` map in CLI config, or auto-derived via SHA-256 hash (see MT5-CLI spec §6.7). Two runtime instances with different `AURUM_STRATEGY_ID` values are always isolated in `history.stats(strategy_id=...)` — no CLI config required. |
| `AURUM_DRY_RUN` | `0` | Set `1` to force dry-run (also via DRY_RUN.flag file) |
| `AURUM_LIVE` | `0` | Set `1` for live trading; combined with CLI `--live` gate |

---

## 14. Tunables

Defaults chosen with rationale documented. Adjust via env var or config file.

| Tunable | Default | Rationale |
|---|---|---|
| **Minimum RR** (`AURUM_MIN_RR`) | `3.0` | Matches Gopher Gate reference strategy; operator-configurable |
| **Session equity reset** | Midnight UTC daily | Aligns with forex daily close (22:00 UTC); runtime restart also resets |
| **Consecutive-loss reset** | Manual RESUME only | 3 losses in a row indicates strategy/market condition issue, not statistical blip |
| **ATR timeframe** | M5 ATR(14) | Validated against Gopher Gate sample trades; M15 ATR available via `AURUM_ATR_TIMEFRAME=M15` |
| **Active sessions** | Tokyo + London | NY session excluded by default because most retail operators are asleep during Asian-Pacific hours; re-enable via `AURUM_ACTIVE_SESSIONS=tokyo,london,ny` |
| **News calendar** | Operator-maintained JSON at `${AURUM_DATA_DIR}/news_calendar.json` | No external HTTP at POC. Upgrade to ForexFactory RSS once stable; MT5-CLI has no calendar API in current `MetaTrader5` package version. |
| **VLM model** | `claude-haiku-4-5-20251001` | Fast, cost-effective for chart VLM; upgrade to Sonnet if accuracy insufficient |
