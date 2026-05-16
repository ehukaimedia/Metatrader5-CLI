# Advanced Wavelet Entry Order-Flow Proxy Confluence Specification

Date: 2026-05-11
Status: v1 companion indicator implemented; EA integration pending
Target system: `Advanced_Wavelet_Entry_Signal.mq5` + `Advanced_Wavelet_Entry_ResearchEA.mq5`
Primary timeframe: M5
Primary current research symbol: USDJPY
Default mode: observe-only diagnostics

## 1. Purpose

Add a new optional confluence layer inspired by the "Footprint Order Flow Framework" video archive while explicitly avoiding any claim that Trading.com MT5 spot FX history provides true executed bid/ask volume at price.

This layer is an **order-flow proxy** module. It should classify existing Advanced Wavelet signals by pressure, divergence, stacked pressure, and absorption proxies built from closed-bar OHLC, tick volume, spread, ATR, and structure context.

It is not a standalone signal generator. The priority remains:

1. Structure first.
2. Base Advanced Wavelet signal second.
3. Order-flow proxy evidence third.
4. Decision state: proceed, investigate, or stand down.
5. CSV diagnostics before any execution behavior changes.

## 2. Data Reality And Naming

The default implementation may use normal closed-bar data:

- `open[]`, `high[]`, `low[]`, `close[]`
- `tick_volume[]`
- `spread[]`
- server time arrays
- existing ATR, structure, pivot, wavelet, noise, rejection, and trend context from the base EA/indicator path

`MqlTick` and `CopyTicksRange` may provide bid/ask quote updates, last, volume, flags, and real volume when broker history supports them. For spot FX, `last`, `volume`, and `volume_real` are commonly absent or unusable for executed buyer/seller delta. Tick-enriched diagnostics must therefore be optional, data-quality flagged, and never required for 5-year M5 tests.

Depth of Market is not part of this design. DOM is symbol/broker dependent and is not suitable as a required historical research input.

Required naming:

- Use `OFProxyDelta`, not true delta.
- Use `OFProxyAggression`, not true footprint imbalance.
- Use `OFProxyStackedPressure`, not stacked footprint imbalance.
- Use `OFProxyAbsorption`, not confirmed institutional absorption.
- Use `OFProxyConfluenceScore`, not footprint score.
- Use `OFProxyDecisionState`, not footprint decision state.

No code, CSV, preset, or UI label should imply true futures footprint data unless the project later changes to an exchange-traded data source with reliable executed bid/ask volume at price.

## 3. Architecture Contract

Use a companion indicator first:

```text
Advanced_OrderFlow_Proxy_Confluence.mq5
```

This avoids changing the current 16-buffer contract of:

```text
Advanced_Wavelet_Entry_Signal.mq5
```

Companion indicator responsibilities:

- Compute direction-neutral proxy features from closed bars only.
- Expose raw proxy buffers through `iCustom`.
- Avoid reading or duplicating the base wavelet indicator.
- Avoid any dependency on future bars or future-confirmed pivots.
- Keep tick enrichment disabled by default.

EA responsibilities:

- Continue reading `Advanced_Wavelet_Entry_Signal` exactly as it does now.
- When `InpUseOrderFlowProxy=true`, create a second `iCustom` handle for `Advanced_OrderFlow_Proxy_Confluence`.
- Fail initialization if the requested proxy companion indicator cannot load.
- Read both indicators at shift `1` only for decisions.
- Combine base wavelet direction/score with proxy fields inside the EA.
- Export proxy fields to new schema-versioned CSV files.
- Keep trade decisions unchanged unless score adjustment or hard filtering is explicitly enabled.

The proxy indicator can output a raw side state, but the signal-specific decision state is EA-derived because it depends on the wavelet direction, threshold, spread gate, and structure context.

## 4. Proposed Companion Indicator Buffers

The companion indicator should expose these buffers:

| Buffer | Name | Range | Meaning |
|---:|---|---|---|
| 0 | `OFProxyDelta` | `[-1,+1]` | Signed bar/quote pressure proxy. Positive favors buy; negative favors sell. |
| 1 | `OFProxyDivergence` | `[-1,+1]` | Positive bullish divergence proxy; negative bearish divergence proxy. |
| 2 | `OFProxyAggression` | `[-1,+1]` | Candle-level aggression proxy, not price-level executed-volume imbalance. |
| 3 | `OFProxyStackedPressure` | `[-1,+1]` | Consecutive same-side pressure cluster near structure. |
| 4 | `OFProxyAbsorption` | `[-1,+1]` | Positive means selling appears absorbed; negative means buying appears absorbed. |
| 5 | `OFProxyConfluenceScore` | `[-1,+1]` | Signed overall proxy bias. Absolute value is confidence. |
| 6 | `OFProxyRawState` | enum numeric | `+1` bullish context, `-1` bearish context, `0` neutral, `2` mixed, `-2` data invalid. |
| 7 | `OFProxyReasonCode` | integer bitmask | Debug bitmask for data availability and proxy logic. |
| 8 | `OFProxyDataMode` | enum numeric | `0` off, `1` bar proxy, `2` tick enriched, `-1` unavailable/error. |

EA-derived CSV fields may include:

- `of_proxy_decision_state`: `+1` proceed buy, `-1` proceed sell, `0` neutral, `2` investigate, `-2` stand_down.
- `of_proxy_profile_state`: `1` proceed evidence, `2` mixed/investigate, `-1` no evidence, `-2` conflict, `-3` proxy not ready.
- `of_proxy_decision_class`: stable text class such as `proceed_buy`, `proceed_sell`, `investigate`, `stand_down`, `no_evidence`, or `proxy_not_ready`.
- `of_proxy_adjusted_score`: base score after optional bonus/penalty.
- `of_proxy_block_reason`: reason a signal was blocked, if hard filtering is enabled.

Do not append these buffers to the base indicator until companion-indicator CSV evidence justifies the additional contract complexity.

## 5. Inputs

Recommended companion indicator inputs:

```text
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
```

Recommended EA inputs:

```text
InpUseOrderFlowProxy=false
InpOFIndicatorName="Advanced_OrderFlow_Proxy_Confluence"
InpOFExportCSV=true
InpOFDecisionProceedEvidence=0.08
InpOFDecisionMaxProceedConflict=0.15
InpOFDecisionStandDownConflict=0.25
InpOFDecisionNoEvidenceThreshold=0.05
InpDailyGuardsAccountWide=false
```

Defaults keep the module diagnostic-only and off for trade decisions.

## 6. Feature Definitions

All formulas use closed bars only. In indicator buffer terms, calculations for bar `i` may reference `i`, `i+1`, `i+2`, and older bars only. They must never reference `i-1` or newer bars.

### 6.1 `OFProxyDelta`

Bar-only default:

```text
range = max(high[i] - low[i], _Point)
body_efficiency = clamp((close[i] - open[i]) / range, -1, +1)
close_location = clamp(2 * ((close[i] - low[i]) / range) - 1, -1, +1)
vol_ratio = tick_volume[i] / avg(tick_volume[i+1 ... i+lookback])
raw = clamp(0.60 * body_efficiency + 0.40 * close_location, -1, +1)
OFProxyDelta = clamp(raw * min(vol_ratio, cap) / cap, -1, +1)
```

Positive means the closed bar suggests buyer pressure. Negative means seller pressure. This is not executed buyers minus sellers.

Optional tick-enriched mode may compute quote-movement pressure from bid/ask mid-price changes inside the already closed bar interval only. It remains quote pressure, not aggressor traded volume.

### 6.2 `OFProxyDivergence`

Divergence is computed from rolling closed-bar extremes, not future-confirmed pivots.

Bearish divergence:

```text
price_makes_higher_high = high[i] > highest(high[i+1 ... i+lookback])
delta_weaker = OFProxyDelta[i] < highest(OFProxyDelta[i+1 ... i+lookback]) - min_delta_gap
OFProxyDivergence = -strength
```

Bullish divergence:

```text
price_makes_lower_low = low[i] < lowest(low[i+1 ... i+lookback])
delta_weaker_to_downside = OFProxyDelta[i] > lowest(OFProxyDelta[i+1 ... i+lookback]) + min_delta_gap
OFProxyDivergence = +strength
```

### 6.3 `OFProxyAggression`

Buy-side aggression proxy:

```text
buy_aggression =
  positive_delta_strength
  * volume_surprise_score
  * close_high_in_range_score
  * range_quality
```

Sell-side aggression proxy:

```text
sell_aggression =
  negative_delta_strength
  * volume_surprise_score
  * close_low_in_range_score
  * range_quality
```

Then:

```text
OFProxyAggression = buy_aggression - sell_aggression
```

### 6.4 `OFProxyStackedPressure`

Use consecutive same-side proxy pressure bars near structure:

```text
same_side_count = count of recent bars within InpOFStackedWindowBars
                  where sign(OFProxyAggression) == side
                  and abs(OFProxyAggression) >= threshold
stack_strength = min(1, same_side_count / InpOFStackedMinBars) * avg_abs_aggression
structure_weight = pivot_or_structure_proximity_score
OFProxyStackedPressure = side * stack_strength * structure_weight
```

This creates a proxy reaction-zone diagnostic. It is not a price-level footprint imbalance.

### 6.5 `OFProxyAbsorption`

Absorption proxy means high effort without progress at or near structure.

```text
effort = volume_surprise_score * abs(OFProxyDelta)
progress_atr = abs(close[i] - open[i]) / ATR[i]
upper_wick_ratio = upper_wick / range
lower_wick_ratio = lower_wick / range
```

Buying absorbed / bearish:

```text
positive_delta = OFProxyDelta > min_delta
high_effort = effort >= InpOFAbsorptionMinEffort
poor_progress = progress_atr <= InpOFAbsorptionMaxProgressATR
rejection_from_high = upper_wick_ratio >= InpOFAbsorptionMinWickRatio or close_location < 0.55
near_resistance = structure distance <= InpOFStructureDistanceATR
OFProxyAbsorption = negative strength
```

Selling absorbed / bullish:

```text
negative_delta = OFProxyDelta < -min_delta
high_effort = effort >= InpOFAbsorptionMinEffort
poor_progress = progress_atr <= InpOFAbsorptionMaxProgressATR
rejection_from_low = lower_wick_ratio >= InpOFAbsorptionMinWickRatio or close_location > 0.45
near_support = structure distance <= InpOFStructureDistanceATR
OFProxyAbsorption = positive strength
```

### 6.6 `OFProxyConfluenceScore`

```text
buy_of =
  w_delta      * max(OFProxyDelta, 0)
+ w_div        * max(OFProxyDivergence, 0)
+ w_aggression * max(OFProxyAggression, 0)
+ w_stack      * max(OFProxyStackedPressure, 0)
+ w_absorb     * max(OFProxyAbsorption, 0)

sell_of =
  w_delta      * max(-OFProxyDelta, 0)
+ w_div        * max(-OFProxyDivergence, 0)
+ w_aggression * max(-OFProxyAggression, 0)
+ w_stack      * max(-OFProxyStackedPressure, 0)
+ w_absorb     * max(-OFProxyAbsorption, 0)

OFProxyConfluenceScore = normalize(buy_of) - normalize(sell_of)
```

Positive supports buy. Negative supports sell.

### 6.7 EA-Derived `OFProxyDecisionState`

The EA derives the signal-specific decision from the base wavelet signal:

```text
D = base wavelet direction (+1 buy, -1 sell)
alignment = D * OFProxyConfluenceScore
```

Decision values:

```text
+1 = proceed buy
-1 = proceed sell
 0 = neutral / no actionable confluence
 2 = investigate / mixed evidence
-2 = stand_down / conflict or invalid data
```

Proceed when the base wavelet signal is eligible, proxy pressure aligns with `D`, aggression or stacked pressure supports `D`, no strong opposing absorption or divergence appears, and spread/session gates pass.

Investigate when evidence is mixed, divergence appears, absorption appears against the setup, or tick data quality is questionable in tick-enriched mode.

Stand down when proxy pressure strongly opposes `D`, opposing absorption is strong, spread fails, required structure is absent, or data quality is invalid.

## 7. Reason-Code Bitmask

Recommended bits:

| Bit | Decimal | Name | Meaning |
|---:|---:|---|---|
| 0 | 1 | `OF_DATA_AVAILABLE` | Proxy data usable. |
| 1 | 2 | `OF_BAR_PROXY_MODE` | Bar-only proxy mode. |
| 2 | 4 | `OF_TICK_ENRICHED_MODE` | Optional tick-enriched mode used. |
| 3 | 8 | `OF_TICK_DATA_UNAVAILABLE` | Tick enrichment requested but unavailable. |
| 4 | 16 | `OF_DELTA_BUY` | Delta proxy favors buy. |
| 5 | 32 | `OF_DELTA_SELL` | Delta proxy favors sell. |
| 6 | 64 | `OF_PRICE_DELTA_AGREE` | Price direction and delta proxy agree. |
| 7 | 128 | `OF_BULLISH_DIVERGENCE` | Bullish divergence proxy. |
| 8 | 256 | `OF_BEARISH_DIVERGENCE` | Bearish divergence proxy. |
| 9 | 512 | `OF_BUY_AGGRESSION` | Buy aggression proxy. |
| 10 | 1024 | `OF_SELL_AGGRESSION` | Sell aggression proxy. |
| 11 | 2048 | `OF_BUY_STACK` | Bullish stacked pressure proxy. |
| 12 | 4096 | `OF_SELL_STACK` | Bearish stacked pressure proxy. |
| 13 | 8192 | `OF_SELLING_ABSORBED` | Bullish absorption proxy. |
| 14 | 16384 | `OF_BUYING_ABSORBED` | Bearish absorption proxy. |
| 15 | 32768 | `OF_STRUCTURE_PRESENT` | Structure/pivot context exists. |
| 16 | 65536 | `OF_STRUCTURE_ALIGNED` | Proxy aligns with intended structure/direction. |
| 17 | 131072 | `OF_SPREAD_PASS` | Spread filter passes. |
| 18 | 262144 | `OF_PROCEED` | Proceed state. |
| 19 | 524288 | `OF_INVESTIGATE` | Investigate state. |
| 20 | 1048576 | `OF_STAND_DOWN` | Stand-down state. |
| 21 | 2097152 | `OF_SCORE_BONUS_APPLIED` | Optional bonus applied. |
| 22 | 4194304 | `OF_SCORE_PENALTY_APPLIED` | Optional penalty applied. |
| 23 | 8388608 | `OF_HARD_FILTER_BLOCKED` | Hard filter blocked a base signal. |

## 8. Combining With The Existing Score

Default behavior:

```text
InpUseOrderFlowProxy=false
InpOFUseAsScoreAdjustment=false
InpOFUseAsHardFilter=false
InpAllowTrading=false
```

Optional score adjustment after CSV validation:

```text
alignment = D * OFProxyConfluenceScore
bonus = InpOFScoreBonusWeight * max(alignment, 0)
penalty = InpOFPenaltyWeight * max(-alignment, 0)

if OFProxyDecisionState == 2:
    penalty += small_investigate_penalty
if OFProxyDecisionState == -2:
    penalty += larger_stand_down_penalty

OFProxyAdjustedScore = clamp(BaseSignalScore + bonus - penalty, 0, 1)
```

Hard filter, only after validation:

```text
if InpOFUseAsHardFilter:
    if InpOFBlockStandDown and OFProxyDecisionState == -2:
        block
    if InpOFBlockInvestigate and OFProxyDecisionState == 2:
        block
    if InpOFRequireProceed and OFProxyDecisionState != D:
        block
```

Use small initial bonus/penalty weights such as `0.03` to `0.08`. Do not optimize broad ranges until CSV evidence shows stable separation.

## 9. Exit-Management Research Extension

Current USDJPY M5 baseline evidence:

- HC80 no-TP 24-bar tiny-trade smoke: 113 opened/closed trades, +$10.21 total, profit factor 1.13.
- The no-TP run left a low median capture of available MFE, so it may be exiting poorly.
- ATR TP 1.5 / ATR SL 3.0: 113 opened/closed trades, +$5.58 total, profit factor 1.10.
- The first ATR TP test took profits but underperformed the no-TP baseline and should not be treated as an improvement.

Proxy exit diagnostics should be exported before acting on them:

- `of_proxy_exit_warning_against_position`
- `of_proxy_hold_confirmation`
- `of_proxy_exhaustion`
- proxy state at entry
- proxy state at planned 24-bar exit
- whether a 24-to-48 bar extension would have been supported

Candidate exit overlays to validate later:

1. Close on opposing stand-down after minimum hold bars.
2. Close on opposing absorption after MFE exceeds a threshold.
3. Extend from 24 to 48 bars only when wavelet and proxy remain aligned.
4. Activate a conservative trail only after MFE exceeds a minimum ATR and proxy weakens.

Because lot size is 0.01, partial exits may not be practical. Prefer full-position exit overlays.

## 10. CSV Schema Migration

The current EA writes fixed headers and uses append mode. Adding columns to existing filenames would corrupt mixed-schema CSVs. The first proxy implementation must use one of these safe paths:

- New run tags such as `*_ofproxy_v1`.
- New filenames with an `ofproxy_v1` suffix.
- `InpAppendCSV=false` when writing a new schema.
- A `schema_version` column at the start of new proxy-enabled CSVs.

Signal CSV additions:

```text
schema_version
of_proxy_data_mode
of_proxy_delta
of_proxy_divergence
of_proxy_aggression
of_proxy_stacked_pressure
of_proxy_absorption
of_proxy_confluence_score
of_proxy_raw_state
of_proxy_decision_state
of_proxy_reason_code
of_proxy_adjusted_score
of_proxy_ticks_copied
of_proxy_tick_data_quality
of_proxy_exit_warning
of_proxy_hold_confirmation
```

Trade CSV additions:

```text
schema_version
of_proxy_state_at_entry
of_proxy_score_at_entry
of_proxy_reason_at_entry
of_proxy_state_at_exit
of_proxy_score_at_exit
of_proxy_reason_at_exit
of_proxy_exit_warning_seen
of_proxy_hold_extension_used
of_proxy_bars_extended
```

## 11. Non-Repaint And No-Leak Rules

1. EA decisions continue reading only closed shift `1`.
2. Indicator calculations for bar `i` read only `i`, `i+1`, `i+2`, and older bars.
3. Divergence uses rolling past extremes, not future-confirmed pivots.
4. Stacked pressure uses only completed prior/current closed bars.
5. Absorption does not wait for future failure movement.
6. Forward returns remain delayed EA labels only.
7. Tick-enriched mode requests only the already closed bar interval.
8. No closed bar buffer values change after closure.

## 12. Acceptance Criteria Before Code

The spec is accepted when these decisions are confirmed:

- Companion indicator remains the first implementation path.
- Tick enrichment is postponed or explicitly diagnostic-only.
- Buffer map and input names above are accepted.
- EA-derived decision-state logic is implemented in the EA, not hidden inside the companion indicator.
- CSV schema migration uses new filenames/run tags or append-disabled writes.
- Default remains observe-only and diagnostic-first.
- Proxy terminology appears consistently in code, docs, CSV, and UI labels.
