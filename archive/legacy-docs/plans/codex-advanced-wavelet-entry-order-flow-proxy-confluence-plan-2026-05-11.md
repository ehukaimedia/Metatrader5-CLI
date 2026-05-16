# Plan - Advanced Wavelet Entry Order-Flow Proxy Confluence

Date: 2026-05-11
Status: Companion indicator and v2 EA CSV integration implemented; validation pending

## Goal

Add a closed-bar, non-repainting order-flow proxy confluence layer to Advanced Wavelet Entry. The layer preserves the useful concepts from the Footprint Order Flow Framework as spot-FX-safe proxy diagnostics without claiming true executed bid/ask footprint data.

Current USDJPY M5 evidence to preserve as baseline context:

- HC80 no-TP 24-bar tiny-trade smoke: 113 trades, +$10.21, profit factor 1.13.
- ATR TP 1.5 / ATR SL 3.0 tiny-trade smoke: 113 trades, +$5.58, profit factor 1.10.
- The no-TP baseline left MFE uncaptured; the first ATR TP variant took profit but did not improve the baseline.

## Phase 0 - Repository And Data Audit

1. Read project instructions and current architecture:
   - `skills/trading.com/SKILL.md`
   - `docs/playgrounds/`
   - current Advanced Wavelet spec, plan, safety review
   - current indicator and EA
   - local footprint/order-flow video archive and generated contact sheets

2. Confirm current indicator/EA contract:
   - `Advanced_Wavelet_Entry_Signal.mq5` existing 16-buffer order
   - `Advanced_Wavelet_Entry_ResearchEA.mq5` current `iCustom` input order
   - EA closed-shift-1 decision logic
   - current signal/trade CSV headers and delayed forward-return labels

3. Data audit in MT5:
   - `tick_volume` availability
   - `real_volume` nonzero rate
   - spread values
   - `CopyTicksRange` success/failure
   - `last`, `volume`, `volume_real` nonzero rates
   - `TICK_FLAG_BUY` / `TICK_FLAG_SELL` occurrence rate
   - number of ticks copied per M5 bar in real-tick mode

Decision gate: if FX trade fields are zero/absent, continue with bar-only proxy as default. If quote tick data is reliable, keep tick enrichment optional and diagnostic.

## Phase 1 - Spec Acceptance

Confirm before writing MQL5:

- companion indicator remains the first implementation path
- buffer map and input names use `OFProxy*` terminology
- EA derives the signal-specific `OFProxyDecisionState`
- proxy CSVs use a schema-versioned/new-filename migration
- exit diagnostics are included as CSV fields only in v1
- score adjustment and hard filter stay disabled by default

Recommended decision: build a companion indicator first to avoid destabilizing the current 16-buffer Advanced Wavelet indicator and EA input contract.

## Phase 2 - Implement Companion Indicator

Created:

```text
metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/MQL5/Indicators/Advanced_OrderFlow_Proxy_Confluence.mq5
```

The indicator exposes:

1. `OFProxyDelta`
2. `OFProxyDivergence`
3. `OFProxyAggression`
4. `OFProxyStackedPressure`
5. `OFProxyAbsorption`
6. `OFProxyConfluenceScore`
7. `OFProxyRawState`
8. `OFProxyReasonCode`
9. `OFProxyDataMode`

Implementation requirements:

- closed-bar only
- no future-bar pivots
- no tick-by-tick retraining
- no per-bar heavy tick loops by default
- no dependency on `Advanced_Wavelet_Entry_Signal`
- all buffers initialized on every calculated bar
- tick enrichment disabled by default and data-quality flagged if later enabled

Validation status:

- Repo-package MetaEditor compile: 0 errors, 0 warnings.
- Terminal-data MetaEditor compile: 0 errors, 0 warnings.

## Phase 3 - EA CSV Integration

Implemented after spec acceptance:

```text
metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/MQL5/Experts/Advanced_Wavelet_Entry_ResearchEA.mq5
```

Add optional inputs:

```text
InpUseOrderFlowProxy=false
InpOFIndicatorName="Advanced_OrderFlow_Proxy_Confluence"
InpOFExportCSV=true
InpDailyGuardsAccountWide=false
InpOFATRPeriod=14
InpOFDeltaLookback=48
InpOFDivergenceLookback=24
InpOFStructureLookback=36
InpOFVolumeRatioCap=2.50
InpOFDivergenceMinDeltaGap=0.10
InpOFAggressionMinDelta=0.20
InpOFAggressionMinVolumeRatio=1.15
InpOFStackedMinBars=3
InpOFStackedWindowBars=5
InpOFAbsorptionMinEffort=0.65
InpOFAbsorptionMaxProgressATR=0.25
InpOFAbsorptionMinWickRatio=0.35
InpOFStructureDistanceATR=1.20
InpOFNeutralThreshold=0.10
InpOFMixedThreshold=0.15
InpOFDecisionProceedEvidence=0.08
InpOFDecisionMaxProceedConflict=0.15
InpOFDecisionStandDownConflict=0.25
InpOFDecisionNoEvidenceThreshold=0.05
```

EA behavior:

- Base behavior unchanged when disabled.
- Create a second indicator handle only when enabled.
- Read proxy buffers with `CopyBuffer(..., 1, 1, ...)` only.
- Combine base wavelet direction/score with proxy fields inside the EA.
- Export proxy fields to new schema-versioned CSV files or run tags.
- Do not change trading decisions unless score adjustment or hard filtering is explicitly true.
- Preserve `InpAllowTrading=false` as default.

CSV migration rule: do not append proxy rows to existing baseline CSV filenames with old headers. Current implementation writes `ofproxy_v2` filenames when proxy CSV export is enabled.

Validation status:

- EA reads the proxy companion indicator through a second `iCustom` handle only when `InpUseOrderFlowProxy=true`.
- Proxy reads use shift `1`.
- If the proxy is enabled but cannot be loaded, initialization fails so the run cannot produce misleading blank proxy diagnostics.
- Trading decisions remain unchanged in diagnostic mode.
- v2 signal CSV exports alignment, evidence, conflict, profile state, decision class, and signal direction.
- v2 trade CSV records proxy state at entry and attempts to record proxy state at exit.
- Invalid base signal states are ignored, and FOK preference is reset before each order attempt.
- Proxy-not-ready rows are explicitly classified instead of being silently indistinguishable from proxy-disabled rows.
- Daily guard scope can be widened from per-symbol/magic to account-wide with `InpDailyGuardsAccountWide=true`.

## Phase 4 - Observe-Only CSV Validation

Run observe-only diagnostics first.

Suggested tests:

- USDJPY M5, 2021.05.09-2026.05.09
- GBPUSD M5, same period where data exists
- AUDUSD M5
- EURJPY M5

Base thresholds:

- discovery threshold: indicator score `0.50` to collect enough data
- high-confidence analysis: score buckets `0.70`, `0.75`, `0.80`, `0.85`

Output buckets:

- baseline wavelet score only
- `OFProxyDecisionState` proceed
- `OFProxyDecisionState` investigate
- `OFProxyDecisionState` stand_down
- delta aligned vs opposed
- absorption aligned vs opposed
- stacked pressure aligned vs opposed
- divergence aligned vs opposed
- spread bucket
- session bucket

Metrics:

- signal count
- active months
- average and median forward returns at 3/6/12/24/48 bars
- win rate by forward horizon
- MFE/MAE from trade CSV when execution is enabled
- spread burden
- stability by year
- stability by symbol

Pass condition for next phase:

- proxy states show stable separation between proceed and stand-down buckets across years/symbols
- trade count remains analyzable
- no single-year or single-trade dependency
- no clear data-quality mismatch between real-tick and bar-only tests

## Phase 5 - Backtest Smoke Tests With Existing Risk Controls

Compare against current baselines:

1. Baseline high-confidence wavelet, no TP, 24-bar time exit.
2. Diagnostic-only proxy, no trade change.
3. Small proxy score adjustment only.
4. Block stand-down only, if CSV evidence is strong.
5. Require proceed only after block-stand-down has proven stable.
6. Exit overlay diagnostics only.

Keep constraints:

- 0.01 lots
- demo-only guard
- one position per symbol/magic
- daily max trades
- daily loss guard
- spread-aware entry filter
- no hedging assumptions

No profitability claim should be made from these smoke tests.

## Phase 6 - Exit-Management Research

Use the proxy layer to test whether exits can avoid cutting winners or overstaying losers:

1. Opposing stand-down exit after minimum hold bars.
2. Opposing absorption/divergence warning exit after MFE threshold.
3. 24-to-48 bar extension only when wavelet score and proxy state remain aligned.
4. Conservative ATR trailing only after MFE exceeds a minimum ATR and proxy weakens.

Evaluate each overlay against the baseline, not in isolation.

## Phase 7 - Limited Optimization

Do not optimize the full proxy module at first. Use a small set only after CSV evidence:

- `InpOFAggressionMinDelta`
- `InpOFAggressionMinVolumeRatio`
- `InpOFStackedMinBars`
- `InpOFAbsorptionMinEffort`
- `InpOFAbsorptionMaxProgressATR`
- `InpOFScoreBonusWeight`
- `InpOFPenaltyWeight`

Reject settings that:

- reduce trades to too few per year
- improve only one symbol/year
- depend on one large trade
- worsen forward validation
- increase drawdown materially
- fail spread sensitivity checks

## Phase 8 - Forward Demo Observation

Only after backtest and forward-split diagnostics:

- enable tiny demo execution with 0.01 lots
- keep `InpAllowTrading=false` as default in released `.set` files
- use dedicated magic numbers per symbol
- export proxy state at entry and exit
- compare live demo proxy states with tester behavior

## Deliverables After Acceptance

1. Companion indicator.
2. EA CSV integration patch.
3. CSV schema update.
4. README update.
5. Default observe-only `.set` file with `ofproxy_v1` run tag.
6. Safety review update after code review.
