# MT5 TDA Execution Architecture Plan

Date: 2026-05-07
Status: Draft

## Goal

Move the project from chart clutter toward an execution-grade MT5 TDA model that can later support high-value setup alerts.

No automated alert agent or autonomous execution will be built in this plan unless explicitly requested later.

## Current Understanding

- TradingView/Pine is mainly for USDOLLAR screenshots and visual structure comparison.
- MetaTrader 5 is the primary analysis and execution workspace.
- The TDA overlay should be readable for humans and screenshots.
- The Python/CLI layer should own the exact structured setup contract.
- AdaptiveTrailEA should remain the post-fill trade manager.

## Design Direction

Use this hierarchy:

```text
D1/H4 permission
  -> M15 setup area
    -> M5/M1 entry structure
      -> FVG/OB/POI execution plan
        -> risk gates
```

Structure leads. FVG/order block supplies the trade area. Liquidity refines quality and timing. Risk gates decide whether a setup can become actionable.

## Phase 0: Architecture Artifacts

Status: complete

- Create `docs/specs/2026-05-07-mt5-tda-execution-architecture.md`.
- Create `docs/plans/2026-05-07-mt5-tda-execution-architecture-plan.md`.
- Create `docs/playgrounds/mt5-tda-execution-playground.html`.

## Phase 1: Structured Setup Contract

Status: implemented in `metatrader5_cli/mt5/core/analyze.py`

Add or revise a Python setup-planning module that returns:

- `status`: no_trade, watch, ready.
- `direction`: buy, sell, or null.
- `quality_score`.
- D1/H4/M15/M5/M1 structure reads.
- Valid POI/FVG/order-block candidate.
- Liquidity context.
- Entry trigger, SL, TP, RR, and invalidation.
- Gate list with exact blockers.

Candidate location:

- Extend `metatrader5_cli/mt5/core/analyze.py`, or create a focused `metatrader5_cli/mt5/core/setup.py` if the contract grows beyond the current sniper POC.

Implemented notes:

- `analyze.sniper_poc()` now returns `status` as `no_trade`, `watch`, or `ready`.
- The setup stack is D1/H4 permission, M15 setup context, and M5/M1 entry structure.
- Output now includes `quality_score`, `structure`, `poi`, `liquidity`, `entry`, and `explain`.
- FVG POIs expose `caused_structure_break`, `mitigated`, and `poi_quality`.
- Liquidity is contract context, not chart clutter: `sweep_in_zone_creation`, `opposing_liquidity_in_front`, `liquidity_behind_zone`, `poi_trap_risk`, and `nearest_target_liquidity`.
- Trap geometry is local to the POI. A sweep must be geometrically in front of or near the zone to help the setup, and behind-zone liquidity uses a separate tolerance instead of the entry-distance threshold.
- Order commands are only attached when the setup reaches `ready`.

## Phase 2: Visual Cleanup

Update `EhukaiTDAOverlay.mq5` so the default chart favors clarity:

- Show top-down panel.
- Show latest meaningful BOS/CHOCH only.
- Show active strong and weak levels.
- Show current valid FVG/POI zones.
- Show subtle liquidity hints only when relevant.
- Hide stale rails, dense labels, and unrelated debug visuals.

The chart should support a human decision path, not act as the execution brain.

## Phase 3: POI and Order Block Logic

Add a deterministic POI selector:

- FVGs remain first-class.
- Order blocks/supply/demand zones qualify only when they caused a meaningful structure break.
- Mitigated zones are lower priority.
- Filled FVGs are not entry POIs but may remain historical context if needed.

This phase should include tests for:

- Bullish continuation from strong low to weak high.
- Bearish continuation from strong high to weak low.
- CHOCH transition that is not yet a full trade.
- FVG below/above price as valid pullback POI.
- Trap warning when liquidity is mainly behind the zone.

## Phase 4: MT5 Screenshot TDA Alignment

Update screenshot TDA manifests and frame context so agents receive the same source of truth as the chart:

- Visual screenshot.
- Structured setup contract.
- Top-down notes.
- Active POIs.
- Gate blockers.

Agents should not need to infer all logic from pixels.

## Phase 5: Later Alert Agent

Deferred until requested.

The alert agent should scan symbols and ping only when:

- D1/H4 permission is clear.
- M15 setup context is valid.
- M5/M1 entry structure reaches WATCH or READY.
- Risk gates pass or are close to passing.

The alert should include:

- Direction.
- Timeframe stack.
- POI.
- Trigger.
- SL/TP/RR.
- Why it is high value.
- What would invalidate it.

## Phase 6: Supervised READY Placement

Status: implemented for live-capable demo testing

Add a guarded placement bridge for setups that already reach READY:

- `order ready-limit` calls `analyze.sniper_poc()` and rejects anything other than `status=ready`.
- The command runs a broker `order dryrun`, refreshes the setup and quote, rejects stale or drifting entries, runs an immediate second dry-run, and only then calls the normal `order limit` placement path.
- SL, TP, and `strategy_id` are required before placement.
- The implementation does not add a demo-only account-type block because some broker demo accounts report as real/live-capable. It relies on the existing `--live` / `MT5_LIVE=1` live-intent and risk gates.

## Non-Goals

- Do not make the TDA overlay place trades.
- Do not make Pine the execution source of truth.
- Do not add more chart visuals without a contract field that explains why they exist.
- Do not build the alert scanner in this pass.

## Verification

For each implementation phase:

- Run existing pytest suite.
- Compile changed MQL5 files with MetaEditor when MQL5 changes.
- Capture screenshots for D1, H4, M15, M5, and M1 on USDJPY.
- Compare screenshot visuals against structured JSON.
- Document discrepancies before further tuning.

## Decision Checkpoints

Before code implementation:

- Confirm the setup contract fields.
- Confirm whether order blocks are implemented now or after FVG cleanup.
- Confirm visual defaults for liquidity.

Before future alerting:

- Confirm what quality score threshold qualifies as high value.
- Confirm notification channel.
- Confirm whether alerts are advisory only or can stage dry-run orders.
