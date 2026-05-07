# Elite Market Structure Indicator Audit

Date: 2026-05-07
Agent: codex
Reference: `docs/video-transcripts/elite-market-structure-mechanical-trading-strategy_54ffc865/archive.json`

## Answer

Yes. The current Pine Script and MQL5 indicators can be improved by adopting the video's internal-structure confirmation model. The strongest improvement is not adding more labels; it is changing the signal hierarchy so CHOCH is treated as an early fractal event, while internal BOS confirms that a swing pullback has actually started or ended.

The current Pine script is already closest to this model because it has an internal pivot length and iBOS labels. The current MQL5 indicators and Python CLI mirror are still mostly swing-pivot/BOS oriented, so they would benefit more from the upgrade.

## Video Logic To Preserve

The archive and frames describe three structure layers:

1. Swing structure: a swing BOS sets the larger expectation and usually implies a swing pullback should follow.
2. Internal structure: an internal BOS, or iBOS, confirms that a swing pullback has started or ended.
3. Fractal structure: CHOCH is only an early signal that an internal pullback may be starting or ending.

Important implementation rules from the video:

- Do not treat every CHOCH as a complete swing reversal.
- Require iBOS before increasing confidence that the swing pullback is real.
- After iBOS, mark the new strong internal high or strong internal low.
- Target weak internal highs/lows while internal structure is facilitating the larger swing objective.
- Once the swing objective reaches premium/discount or a high-value HTF area, stop blindly following internal trend.
- If expected strong internal structure fails, mark the opposite side as newly weak and allow bias to flip.

Relevant visual frames:

- `frames/0008.png`: old CHOCH-only model.
- `frames/0080.png`: three-structure legend: swing/internal/fractal.
- `frames/0063.png`: iBOS confirms swing pullback behavior.
- `frames/0065.png`: internal realignment with swing structure and strong-to-weak targeting.
- `frames/0071.png`: volatile-market case where CHOCH alone is only an internal pullback clue.
- `frames/0083.png`: discount/premium plus fractal CHOCH ending an internal pullback.
- `frames/0004.png`: swing structure remains the controlling layer.
- `frames/0002.png`: range failure flips expectation.

## Current Code Fit

### Pine

File: `metatrader5_cli/mt5/pine/EhukaiStructure.pine`

The Pine script already contains:

- Swing pivots via `swingLen`.
- Close-confirmed BOS/CHOCH.
- Internal pivots via `internalLen`.
- iBOS labels when price breaks the current internal high/low inside the swing range.

Gap:

- `internalDir` is mostly visual state. It does not gate CHOCH significance, define strong/weak internal levels, or promote iBOS into the setup state machine.

### MQL5 Market Structure

File: `metatrader5_cli/mt5/mql5/Indicators/EhukaiMarketStructure.mq5`

The standalone structure indicator currently has:

- Adaptive pivot lengths.
- HH/HL/LH/LL classification.
- BOS-style bias from latest swing high/low.
- Support/resistance levels.

Gap:

- No internal structure layer.
- No CHOCH layer.
- No strong/weak high/low lifecycle.
- No premium/discount range state.

### MQL5 TDA Overlay

File: `metatrader5_cli/mt5/mql5/Indicators/EhukaiTDAOverlay.mq5`

The overlay already has:

- Close-confirmed BOS/CHOCH with a break buffer.
- Sniper states and TDA score.
- FVG and liquidity context.

Gap:

- CHOCH and BOS both contribute directly to trigger confidence.
- There is no iBOS confirmation between POI/sweep and full trigger.
- The score cannot distinguish early CHOCH from confirmed internal realignment.

### Python CLI Mirror

Files:

- `metatrader5_cli/mt5/core/ehukai.py`
- `metatrader5_cli/mt5/core/analyze.py`

The Python side mirrors swing structure, FVGs, liquidity, and sniper POC planning.

Gap:

- `ehukai.market_structure()` only returns swing-level context.
- `analyze.sniper_poc()` uses multi-timeframe majority, FVG, and sweep gates, but not internal BOS confirmation.

## Recommended Upgrade

Implement this as a spec-first structure contract, then port consistently across Pine, MQL5, and Python:

1. Add `internal_structure` to the structured output:
   - `internal_high`
   - `internal_low`
   - `internal_dir`
   - `last_ibos`
   - `strong_internal_high`
   - `strong_internal_low`
   - `weak_internal_high`
   - `weak_internal_low`
   - `range_eq`, `premium`, `discount`

2. Change TDA state progression:
   - POI/sweep only: `WATCH`
   - CHOCH after POI/sweep: `ARMED`
   - iBOS/realignment after CHOCH: `TRIGGER`

3. Keep FVG and liquidity as POIs, not as structure substitutes.

4. Update visual contracts and playground documentation only after the new labels/fields are decided:
   - `ETDA_` object contract
   - `EMS_` object contract
   - `tda_manifest.py`
   - `docs/playgrounds/mt5-codebase.html`

5. Add regression tests around synthetic OHLC sequences:
   - CHOCH without iBOS should not become trigger.
   - CHOCH plus iBOS should promote to trigger.
   - Strong internal high/low failure should flip the weak target.
   - Premium/discount should be derived from a stable dealing range, not every minor pivot.

## Risks

- Structure logic is currently duplicated across Pine, MQL5 overlays, and Python. Partial implementation will create chart/JSON disagreement.
- Sweep semantics differ between liquidity and TDA overlay behavior; align or explicitly name them before using sweeps as strong/weak structure gates.
- Premium/discount should come from the selected dealing range. If it is recalculated from every latest pivot pair, the signal will become noisy.
- Pivot confirmation lags. That is acceptable for confirmation logic, but it should not be marketed as predictive.

## Bottom Line

Adopt the video logic, but do it as a contract upgrade rather than a quick label patch. The highest-value change is to make iBOS the confirmation gate between early CHOCH and trade trigger confidence.
