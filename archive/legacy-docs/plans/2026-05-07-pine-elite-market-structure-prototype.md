# Pine Elite Market Structure Prototype Plan

Date: 2026-05-07

## Goal

Dial in the elite market structure video logic in TradingView Pine before porting it to MQL5 or the Python CLI mirror.

## Scope

Primary file:

- `metatrader5_cli/mt5/pine/EhukaiStructure.pine`

No MQL5, Python, or automation behavior changes in this pass.

## Prototype Rules

- Swing BOS/CHOCH defines the active dealing range.
- Swing BOS/CHOCH may seed internal direction for the new leg, but it must not be labeled as confirmed iBOS until an internal break prints.
- If a seeded leg closes through its seeded weak high/low on a later bar, promote the seed to confirmed iBOS.
- Fractal CHOCH is an early internal pullback clue.
- Internal BOS is the confirmation event.
- Bullish iBOS promotes the prior internal low to `Strong iL` and the range high to `Weak iH`.
- Bearish iBOS promotes the prior internal high to `Strong iH` and the range low to `Weak iL`.
- Closing through expected strong internal structure flips internal expectation and marks a failure state.
- Strong internal high/low failures should print a visible failure marker and expose alert hooks.
- Premium/discount comes from the active swing dealing range equilibrium, not minor internal pivots.

## Tuning Notes

- Use `Internal Pivot Length` to control confirmation sensitivity.
- Use `Fractal Pivot Length` to control early CHOCH frequency.
- Keep `Show Fractal CHOCH` off while tuning if the chart gets noisy.
- Use `Show Structure State Label` to compare the model against replay without relying on every historical marker.

## Porting Gate

Port to MT5 only after the Pine prototype is visually replayed through at least:

- one clean bullish iBOS continuation,
- one clean bearish iBOS continuation,
- one CHOCH that fails to produce iBOS,
- one strong internal high/low failure,
- one premium/discount swing pullback example.

## MQL5 Port Notes

- `EhukaiMarketStructure.mq5` v1.12 mirrors the Pine v1.0 elite-v1 state machine while preserving the `EMS_` object prefix and existing swing/BOS visual contract.
- MT5 overlay additions: elite state panel, range EQ, strong/weak internal levels, iBOS events, and strong internal failure markers.
- `EhukaiTDAOverlay.mq5` v1.18 carries the same elite structure state so the normal one-indicator chart does not need the primitive debug indicators stacked. Historical elite events, full liquidity drawings, and strong/weak internal rails are off by default in agent screenshot mode; the state panel keeps the logic visible without forcing lines through candles.
- `EhukaiTDAOverlay.mq5` v1.18 keeps FVG visible by default, caps clean agent screenshots to the nearest FVG zones, still uses liquidity as structured/sweep context, clears old `EMS_`, `EFVG_`, and `ELS_` chart objects, and adds a `GUIDE:` panel that turns structure/FVG/sweep context into `WAIT`, `WATCH`, or `NO TRADE` guidance with a nearest POI and invalidation level.
- `EhukaiTDAOverlay.mq5` v1.19 moves the default chart to manual-analysis mode: D1/H4/M15/M5/M1 structure panel, more swing labels, recent BOS/CHOCH/iBOS rails, visible FVG zones on every timeframe, and liquidity reduced to recent small sweep hints.
- `EhukaiTDAOverlay.mq5` v1.23, `EhukaiMarketStructure.mq5` v1.12, `EhukaiStructure.pine` v1.0, and Python `ehukai.market_structure()` now align to the video/Pine `8 / 3 / 1` structure contract. The canonical `elite-v1` rule is: swing BOS/CHOCH on the last closed bar sets direction, internal structure confirms pressure, and FVG/POI supplies execution context.
- MetaEditor can be driven from PowerShell with `/compile:<mq5>` and `/log:<log>`; both `EhukaiTDAOverlay.mq5` v1.23 and `EhukaiMarketStructure.mq5` v1.12 compile with 0 errors / 0 warnings in the MT5 data folder.
