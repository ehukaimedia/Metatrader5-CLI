# Visual TDA Cleanup Review - USDJPY

Date: 2026-05-07

## Finding

The USDJPY M15 chart was visually too noisy for agent TDA. The screenshot still showed `TDA v1.15`, so MT5 had not reloaded the freshly compiled overlay and was still rendering old liquidity/elite rail behavior.

## Cleanup Applied

- `EhukaiTDAOverlay.mq5` v1.17 adds clean agent screenshot mode.
- Clean agent mode hides liquidity drawings even if an old chart input enables them.
- Clean agent mode hides elite EQ and strong/weak internal rails by default; the state panel still carries the logic.
- Clean agent mode caps FVG display tighter and limits swing labels to the latest decision points.
- Clean agent mode clears stale `EMS_`, `EFVG_`, and `ELS_` objects so old debug overlays do not pollute the one-indicator chart.
- `EhukaiTDAOverlay.mq5` v1.18 adds a manual trade-guide panel: bias, sweep context, nearest FVG POI, and invalidation level.
- v1.18 keeps full liquidity pools hidden by default, but can show tiny `BSL sweep` / `SSL sweep` markers when sweep context matters.
- v1.18 stores nearest bullish/bearish FVG bounds and latest support/resistance in the overlay context so the guide can say `WAIT`, `WATCH`, or `NO TRADE` without requiring multiple indicators.
- `EhukaiTDAOverlay.mq5` v1.19 switches the default chart experience to manual analysis mode, adds a top-down structure panel for D1/H4/M15/M5/M1, restores more swing labels, and draws recent BOS/CHOCH/iBOS break rails as the actual market-structure map.
- v1.19 keeps FVGs primary on every timeframe, raises the default visible FVG cap, moves the guide into a readable panel, and limits liquidity to recent tiny sweep hints rather than full liquidity rails.
- `EhukaiTDAOverlay.mq5` v1.20 fixes the manual-chart clutter regression by hiding top-right status headers, FVG text labels, and BOS/CHOCH text labels by default.
- v1.20 moves the trade guide to the left side under the top-down panel, reduces default visible break rails and swing labels, and keeps FVG rectangles/midlines as the primary visual POI instead of text labels through the active candles.
- `EhukaiTDAOverlay.mq5` v1.21 restores clarity for entry timeframes by using adaptive FVG thresholds: M1/M5 can show smaller imbalances while higher timeframes remain stricter.
- v1.21 limits structure-break visuals to the latest close-confirmed BOS/CHOCH/iBOS rail by default and adds a compact marker so stale opposite-side rails do not masquerade as current trade guidance.
- `EhukaiTDAOverlay.mq5` v1.22 keeps active historical FVGs visible by default: filled FVGs are removed, while open or partially filled historical FVGs remain eligible and are selected by proximity to current price.

## Verification

- Compiled `EhukaiTDAOverlay.mq5` v1.17 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Compiled `EhukaiTDAOverlay.mq5` v1.18 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Compiled `EhukaiTDAOverlay.mq5` v1.19 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Compiled `EhukaiTDAOverlay.mq5` v1.20 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Compiled `EhukaiTDAOverlay.mq5` v1.21 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Compiled `EhukaiTDAOverlay.mq5` v1.22 into the MT5 data-folder indicators directory.
- MetaEditor compile log: `0 errors, 0 warnings`.
- Follow-up screenshot artifact before MT5 reload:
  `docs/code-reviews/visual-tda-usdjpy-clean-v116/USDJPY_M15_20260507_210434_394203.png`

## Operator Note

If the top-down panel does not say `TDA v1.22 TOP-DOWN`, remove and reattach `EhukaiTDAOverlay`. A clean reload should show one top-down panel, one guide panel, the latest compact structure-break marker, active historical FVG zones, and no top-right text pileup. Full liquidity rails and dense text labels should remain off unless explicitly enabled.
