# Ehukai TDA + Structure Sniper Integration Plan

Date: 2026-05-06

## Goal

Turn the current busy MT5 visual stack into a decision hierarchy:

1. Directional bias from higher-timeframe structure.
2. TDA context from liquidity, FVG, and active swing levels.
3. Sniper trigger from lower-timeframe sweep plus close-confirmed CHOCH/BOS.
4. AdaptiveTrailEA remains post-fill trade management, not entry logic.

## Current Components

- `EhukaiTDAOverlay.mq5` is the preferred clean presentation layer.
- `EhukaiFVG.mq5`, `EhukaiMarketStructure.mq5`, and `EhukaiLiquiditySwings.mq5` are primitive/debug overlays.
- `AdaptiveTrailEA.mq5` manages open positions after entry with breakeven and Chandelier trailing.
- `EhukaiStructure.pine` is the current TradingView reference for clean structure behavior.

## Visual Hierarchy

Use only `EhukaiTDAOverlay` on the live chart by default.

Default live-trading view:

- Show latest active structure high and low.
- Show only the nearest valid FVG in the active bias direction.
- Show only the nearest opposing liquidity or invalidation level.
- Show the latest BOS/CHOCH event.
- Hide primitive swing markers unless debug mode is enabled.
- Hide filled or distant FVGs.
- Hide swept liquidity unless it directly explains the current setup.

Primitive indicators should be loaded only for debugging or research screenshots.

## Signal State Machine

The overlay should produce one of these states:

- `NO_TRADE`: no alignment or no nearby point of interest.
- `WATCH_BUY`: bullish higher-timeframe bias and price is approaching bullish POI.
- `WATCH_SELL`: bearish higher-timeframe bias and price is approaching bearish POI.
- `ARMED_BUY`: sell-side liquidity swept or bullish FVG/discount zone touched.
- `ARMED_SELL`: buy-side liquidity swept or bearish FVG/premium zone touched.
- `TRIGGER_BUY`: lower-timeframe bullish CHOCH/BOS closes after `ARMED_BUY`.
- `TRIGGER_SELL`: lower-timeframe bearish CHOCH/BOS closes after `ARMED_SELL`.
- `MANAGE`: position is open; AdaptiveTrailEA handles BE/trailing.

## Sniper Entry Rules

Buy setup:

1. H4/D or selected directional frame is bullish or neutral-with-bullish-shift.
2. Price trades into a bullish POI: bullish FVG, sell-side liquidity sweep, or active HL/support.
3. Price sweeps below local liquidity and closes back above it, or reacts from the POI.
4. M1/M5 closes above the last internal high, creating bullish CHOCH/BOS.
5. Entry is valid only while stop can sit below the swept low or POI with acceptable risk.

Sell setup:

1. H4/D or selected directional frame is bearish or neutral-with-bearish-shift.
2. Price trades into a bearish POI: bearish FVG, buy-side liquidity sweep, or active LH/resistance.
3. Price sweeps above local liquidity and closes back below it, or rejects from the POI.
4. M1/M5 closes below the last internal low, creating bearish CHOCH/BOS.
5. Entry is valid only while stop can sit above the swept high or POI with acceptable risk.

## TDA Score

Rank opportunities from 0 to 100:

- 25 points: higher-timeframe bias alignment.
- 20 points: valid POI nearby and not fully filled.
- 20 points: liquidity sweep occurred before the trigger.
- 20 points: lower-timeframe CHOCH/BOS closed in entry direction.
- 10 points: price is close enough to entry zone for acceptable risk.
- 5 points: session timing is favorable.

Suggested display:

- `0-49`: no trade.
- `50-69`: watch.
- `70-84`: armed.
- `85+`: trigger.

## Sessions

Sessions are not required for v1 entry logic.

Use sessions later as a quality filter:

- Asia range sets liquidity map.
- London sweep/break provides expansion context.
- New York sweep/reversal provides sniper timing.

Keep session zones hidden by default because the chart is already visually dense.

## Implementation Phases

### Phase 1: Clean Overlay

Update `EhukaiTDAOverlay.mq5` with a `TDA_SNIPER` mode:

- Hide primitive clutter.
- Display only active structure levels, nearest valid FVG, nearest liquidity, and one setup label.
- Add `InpShowSniperState`, `InpShowOnlyActionableZones`, and `InpMinTDAScore`.

Acceptance criteria:

- A default live chart can run `EhukaiTDAOverlay.mq5` by itself without needing the primitive indicators.
- No more than one nearest bullish FVG and one nearest bearish FVG are visible unless manual/debug mode is enabled.
- No more than one buy-side and one sell-side liquidity area are visible unless manual/debug mode is enabled.
- The chart always shows a single current state label: `NO_TRADE`, `WATCH`, `ARMED`, or `TRIGGER`.
- Existing object prefix `ETDA_` remains stable for screenshot and CLI agents.

### Phase 2: Structure Engine Upgrade

Port the clean Pine structure behavior into `EhukaiTDAOverlay.mq5`:

- Close-confirmed BOS/CHOCH.
- HH/HL/LH/LL pivot labels with strict max count.
- Active high/low levels only.
- Internal structure used for trigger state, not constant labels.

Acceptance criteria:

- BOS/CHOCH only fires after candle close beyond the relevant swing level.
- MT5 evaluates BOS/CHOCH from the last closed candle by default, so the forming candle cannot flip panel bias intrabar.
- BOS is continuation in the current structure direction; CHOCH is a close-confirmed break against the prior HH/HL or LH/LL structure.
- Liquidity sweeps use wick-through plus close-back semantics; a wick can arm context but does not confirm directional bias.
- Wick sweeps do not flip structure bias by themselves.
- Active swing levels update in place instead of leaving historical stacked lines.
- Swing labels are capped and recent-only in sniper mode.
- The behavior visually matches `metatrader5_cli/mt5/pine/EhukaiStructure.pine` closely enough to use TradingView as the reference chart.

### Phase 3: Entry Alerts

Add alerts, not auto-entry:

- `WATCH_BUY/SELL`.
- `ARMED_BUY/SELL`.
- `TRIGGER_BUY/SELL`.

The first version should help the trader decide. Auto-entry can come later only after visual and replay validation.

Acceptance criteria:

- Alerts include symbol, timeframe, setup direction, state, TDA score, nearest POI, invalidation level, and trigger reason.
- Alerts are rate-limited so one setup does not spam on every tick.
- Alert states are reproducible from chart visuals and future CLI JSON output.

### Phase 4: AdaptiveTrailEA Hand-Off

Leave `AdaptiveTrailEA` focused on post-fill management.

Later optional enhancement:

- Read setup metadata from chart objects or global variables.
- Tune BE and trailing profile based on setup type.

Acceptance criteria:

- No entry automation is added to `AdaptiveTrailEA` in this phase.
- Existing magic-number scoped trade management behavior remains unchanged.
- Any future hand-off uses explicit metadata rather than visually scraping chart objects.

## Files Affected

Primary implementation file:

- `metatrader5_cli/mt5/mql5/Indicators/EhukaiTDAOverlay.mq5`

Reference and comparison files:

- `metatrader5_cli/mt5/pine/EhukaiStructure.pine`
- `metatrader5_cli/mt5/mql5/Indicators/EhukaiMarketStructure.mq5`
- `metatrader5_cli/mt5/mql5/Indicators/EhukaiFVG.mq5`
- `metatrader5_cli/mt5/mql5/Indicators/EhukaiLiquiditySwings.mq5`

Do not modify in this phase except for optional compatibility metadata:

- `metatrader5_cli/mt5/mql5/Experts/AdaptiveTrailEA.mq5`

Likely later CLI files:

- `metatrader5_cli/mt5/mt5_cli.py`
- `metatrader5_cli/mt5/core/*`
- `metatrader5_cli/mt5/tests/*`

## Proposed Inputs

Add these inputs to `EhukaiTDAOverlay.mq5`:

- `InpMode = TDA_AGENT_SCREENSHOT | TDA_MANUAL_ANALYSIS | TDA_SNIPER`
- `InpShowSniperState = true`
- `InpShowOnlyActionableZones = true`
- `InpMinTDAScore = 70`
- `InpDirectionalTimeframe = PERIOD_H4`
- `InpTriggerTimeframe = PERIOD_M5`
- `InpRequireLiquiditySweep = false`
- `InpRequireFVGTouch = false`
- `InpAlertOnWatch = false`
- `InpAlertOnArmed = true`
- `InpAlertOnTrigger = true`

## State Definitions

`NO_TRADE`:

- No directional alignment, no nearby POI, or score below threshold.

`WATCH_BUY` / `WATCH_SELL`:

- Directional bias exists.
- A valid POI is near enough to matter.
- No lower-timeframe trigger yet.

`ARMED_BUY` / `ARMED_SELL`:

- Directional bias exists.
- Price interacted with the POI or swept relevant liquidity.
- Waiting for lower-timeframe CHOCH/BOS close.

`TRIGGER_BUY` / `TRIGGER_SELL`:

- Armed state is active.
- Lower-timeframe close-confirmed CHOCH/BOS occurs in the setup direction.

`MANAGE`:

- Position exists and trade management belongs to `AdaptiveTrailEA`.

## Review Questions

Reviewers should challenge these decisions:

- Should sniper mode require both FVG touch and liquidity sweep, or allow either?
- Should H4 be the default directional timeframe for all symbols, or should presets differ by asset?
- Should M5 or M1 be the default trigger timeframe?
- Should swept liquidity remain visible after it contributes to an armed state?
- Should the TDA score gate alerts, visuals, or both?
- Should session timing be excluded from v1 scoring or included as a small bonus?

## Validation Plan

Manual validation:

- Compile all modified MQL5 files in MetaEditor with zero errors.
- Compare MT5 `EhukaiTDAOverlay` against TradingView `EhukaiStructure.pine` on the same symbol/timeframe.
- Replay at least one bullish and one bearish setup.
- Confirm states transition in order: `NO_TRADE -> WATCH -> ARMED -> TRIGGER`.
- Confirm noisy chart objects do not accumulate over time.

CLI validation:

- Add JSON output only after the visual state machine is stable.
- Test that CLI-reported state matches MT5 chart state for fixed screenshots.
- Add regression tests for bullish trigger, bearish trigger, neutral/no-trade, and sweep-without-close-confirmation.

Strategy validation:

- Strategy agent consumes the JSON state, not chart object names.
- Backtests should use the same state definitions as the indicator.
- No auto-entry should be considered until the visual and CLI state agree over replay examples.

## Risks

- Pivot-based structure can lag. That is acceptable for confirmation, but not for predictive entries.
- Too many required filters may remove good trades. Start permissive, then score quality.
- Too few filters may create noisy alerts. Use `InpMinTDAScore` and state transitions to control this.
- MT5 and TradingView candle indexing may differ. Use visual replay comparison before claiming parity.
- Broker/server time can distort session logic. Keep sessions out of v1 required logic.

## First Implementation Step

Implement `TDA_SNIPER` mode inside `EhukaiTDAOverlay.mq5` without touching the EA:

1. Add the new mode and inputs.
2. Limit rendered zones and liquidity in sniper mode.
3. Add setup scoring.
4. Draw one state label.
5. Add alerts after visual state is stable.
