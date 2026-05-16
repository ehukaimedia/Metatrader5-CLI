# Ehukai Volume Profile POC Indicator

## Goal

Add a lightweight MT5 volume-profile indicator that improves top-down trade analysis by exposing reactive price levels:

- Point of Control (POC): highest tick-volume price row in the selected profile.
- Value Area High / Low (VAH / VAL): default 70% value area around POC.
- Profile High / Low: range extremes of the calculated profile.
- Histogram by price: right-side visual map of where volume concentrated.

The indicator is confluence, not an execution trigger. It should help humans and agents answer:

- Is price trading above, below, or inside value?
- Is the selected FVG/POI near POC, VAH, or VAL?
- Is price returning to a high-volume node where reaction/chop is more likely?
- Is price moving through a low-volume region where expansion is more likely?

## Sources

- TradingView support: Volume profile displays trading activity at price levels over a specified period, uses rows and time period, separates up/down volume by bar direction, and defines POC, profile high/low, value area, VAH, and VAL.
- Archived TradingView tutorial: visual frames show fixed/visible/session profile concepts, right-side histograms, red POC line, value-area customization, and up/down/total-volume display modes.

## Implementation

### MQL5 Visual Indicator

File: `metatrader5_cli/mt5/mql5/Indicators/EhukaiVolumeProfilePOC.mq5`

Stable contract:

- Object prefix: `EVP_`
- Label: `VP POC <price> | VA <val>-<vah>`
- Geometry: right-side histogram, POC line, VAH/VAL dashed lines, optional profile high/low.

Defaults:

- `InpLookbackBars = 120`
- `InpRows = 48`
- `InpValueAreaPercent = 70`
- Closed-bar calculation (`rates_total - 2`) for stable screenshot reads.

Forex limitation:

MT5 forex symbols generally expose tick volume, not exchange trade volume. This is acceptable because TradingView also documents tick volume for forex/CFD-style instruments.

### CLI Structured Context

Function: `ehukai.volume_profile(symbol, timeframe, bars=120, rows=48, value_area_pct=70)`

Command:

```powershell
mt5 --json ehukai volume-profile USDJPY M15 --bars 120 --rows 48
```

Returned fields include:

- `poc` / `point_of_control`
- `value_area_high`
- `value_area_low`
- `profile_high`
- `profile_low`
- `price_context`: `above_value_area | inside_value_area | below_value_area`
- `poc_distance_pips`
- `rows_detail`
- `high_volume_nodes`

## Non-Goals

- Do not add POC as a hard trade gate yet.
- Do not use this for autonomous order placement until journal data proves it improves outcomes.
- Do not claim equivalence with TradingView's lower-timeframe internal calculations; this implementation distributes each bar's tick volume across touched price rows as a stable approximation.
