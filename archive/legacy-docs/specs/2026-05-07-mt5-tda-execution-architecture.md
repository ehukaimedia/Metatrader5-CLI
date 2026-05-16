# MT5 TDA Execution Architecture Spec

Date: 2026-05-07
Status: Draft for review

## Purpose

Define a clean MT5-first top-down analysis and execution architecture for Ehukai. TradingView/Pine remains a visual reference and USDOLLAR screenshot context tool. MetaTrader 5 is the primary analysis, setup detection, order placement, and trade management environment.

The goal is to produce fewer, clearer trade ideas: only high-value setups with explicit structure, POI, entry trigger, invalidation, target, and blockers.

## Context Sources

This spec is informed by the current codebase plus the archived videos:

- `elite-market-structure-mechanical-trading-strategy_54ffc865/archive.json`
- `master-liquidity-concepts-mechanical-strategy_c9b095b6/archive.json`
- `orderblocks-simplified-get-profitable-today_43e483a7/archive.json`
- `master-institutional-supply-and-demand-trading-ultimate-strategy-guide_caac644f/archive.json`

Core lesson across the videos:

1. Market structure determines direction.
2. Supply/demand, order blocks, and FVGs identify trade areas.
3. Liquidity refines probability and timing.
4. Lower-timeframe structure confirms the entry.

## Platform Roles

### TradingView / Pine

TradingView is not the execution source of truth.

Use Pine for:

- USDOLLAR daily-analysis screenshots.
- Market-structure visual prototyping.
- Cross-checking whether BOS, CHOCH, HH/HL, LH/LL, and FVG logic feels readable.

Do not use Pine as the authoritative trade execution contract.

### MetaTrader 5

MT5 is the all-around trading application.

Use MT5 for:

- Top-down analysis.
- Structured setup detection.
- Chart screenshots for agents and humans.
- Guarded order placement through the CLI.
- Trade management through the EA.

## TDA Hierarchy

The canonical TDA hierarchy is:

```text
D1/H4 directional permission
  -> M15 setup area and trade context
    -> M5/M1 entry structure
      -> risk, execution, and management gates
```

Lower-timeframe signals cannot override higher-timeframe context. A lower-timeframe CHOCH is only an entry clue until the higher-timeframe setup path is valid.

## Trade Setup Contract

Every setup returned by the MT5 analysis layer should have this shape:

```json
{
  "status": "no_trade | watch | ready",
  "direction": "buy | sell | null",
  "quality_score": 0,
  "timeframes": {
    "D1": {},
    "H4": {},
    "M15": {},
    "M5": {},
    "M1": {}
  },
  "structure": {
    "permission_timeframes": ["D1", "H4"],
    "setup_timeframe": "M15",
    "entry_timeframe": "M5",
    "bias": "bullish | bearish | neutral",
    "stage": "HH/HL | LH/LL | BOS | CHOCH | range",
    "strong_level": null,
    "weak_target": null,
    "last_confirmed_event": null
  },
  "poi": {
    "type": "fvg | order_block | supply | demand",
    "timeframe": "M15",
    "direction": "bullish | bearish",
    "upper": 0.0,
    "lower": 0.0,
    "mid": 0.0,
    "state": "open | partial | filled",
    "caused_structure_break": true,
    "mitigated": false
  },
  "liquidity": {
    "sweep_in_zone_creation": false,
    "opposing_liquidity_in_front": false,
    "liquidity_behind_zone": false,
    "poi_trap_risk": false,
    "nearest_target_liquidity": null
  },
  "entry": {
    "model": "wait_for_shift | fvg_limit | sweep_then_shift | trail_after_sweep",
    "timeframe": "M1 | M5",
    "trigger": null,
    "entry_price": null,
    "sl": null,
    "tp": null,
    "rr": null,
    "invalidation": null
  },
  "gates": [],
  "explain": []
}
```

## Market Structure Rules

Structure must be close-confirmed by default.

Required fields per timeframe:

- Current structure: bullish, bearish, neutral.
- Stage: HH/HL, LH/LL, BOS, CHOCH, or range.
- Last confirmed swing high and swing low.
- Strong level: the structure point that caused a meaningful break.
- Weak target: the opposing structure point expected to be taken if order flow continues.
- Last event: BOS, CHOCH, iBOS, or none.
- Signal bar: the closed bar used for the decision.

Visual labels are secondary. The structured JSON is the source of truth.

## POI Rules

Valid trade areas are not any old rectangle.

A POI is valid only if it meets at least one of these conditions:

- It caused a meaningful BOS or CHOCH.
- It is an unfilled or partially filled FVG in the active setup direction.
- It is an order block or supply/demand zone tied to the strong high/low that caused the break.

Priority:

1. Unmitigated POI that caused the current setup break.
2. Fresh open FVG aligned with the setup direction.
3. Partial FVG or mitigated zone only if structure still supports the idea.

## Liquidity Rules

Liquidity is context, not direction.

Do not draw every liquidity pool on the chart. The execution model should compute liquidity as scoring and blockers:

- `sweep_in_zone_creation`: improves POI quality.
- `opposing_liquidity_in_front`: improves probability.
- `liquidity_behind_zone`: warns that the POI may be a trap.
- `nearest_target_liquidity`: helps define TP.

Visual liquidity should stay subtle:

- One recent sweep marker.
- One target-liquidity hint if relevant.
- No long full-chart liquidity rails by default.

## Visual TDA Contract

The MT5 overlay should show only what helps the operator decide.

Required visible elements:

- Left-side top-down panel.
- Active strong and weak levels.
- Latest real BOS/CHOCH only.
- Valid active FVGs and POIs.
- Clear guide state: WAIT, WATCH, READY, or NO TRADE.
- Entry and invalidation only when a setup is actionable.

Default hidden elements:

- Old BOS/CHOCH rails.
- Dense liquidity rails.
- Debug labels.
- Full text labels on every FVG.
- Any line that extends through candles without a decision purpose.

## Execution Boundary

The TDA overlay must not execute trades.

Execution should flow through:

```text
structured setup plan
  -> dry-run order check
    -> operator or agent approval
      -> guarded order placement
        -> AdaptiveTrailEA management
```

The setup planner may produce a placement command, but order placement must remain guarded by `core.order` risk checks.

For supervised live-capable testing, the CLI may offer an execution bridge that consumes the setup contract. That bridge must:

- Require `status = ready`.
- Run a broker dry-run before any placement.
- Refresh the setup and quote after the dry-run.
- Reject the order if the setup stops being READY or the entry drifts beyond the configured tolerance.
- Run an immediate second dry-run using the final setup.
- Require SL, TP, and a strategy ID.
- Use the normal live-intent and risk gates without adding a demo-only account-type block.

Current implementation: `order ready-limit` follows this bridge and routes final placement through `core.order.place_limit()`.

## Future Alert Agent

The future scanner should monitor symbols/timeframes and ping only when a high-value setup reaches WATCH or READY.

Not in current implementation scope:

- Fully autonomous order entry.
- Continuous live scanning daemon.
- Notification integrations.
- Model-based discretionary decisions.

Current scope is to define and later implement a deterministic setup contract that such an agent can consume.

## Acceptance Criteria

The MT5 TDA system is acceptable when:

- A human can open the chart and see the trade path within about 10 seconds.
- An agent can read the JSON and explain why the setup is WAIT, WATCH, READY, or NO TRADE.
- A valid setup contains direction, POI, trigger, SL, TP, RR, invalidation, and blockers.
- Liquidity improves or blocks setups without cluttering the chart.
- Pine and MT5 agree on the core structure language, but MT5 remains the execution source of truth.
- A supervised READY placement can be exercised with `order ready-limit` without bypassing broker dry-run, quote freshness, SL/TP, strategy ID, or the existing live-intent risk gate.
