# Pine Elite Market Structure Code Review

Date: 2026-05-07
Agent: codex
Scope: `metatrader5_cli/mt5/pine/EhukaiStructure.pine`

## Review Notes

The Pine prototype now adds the video-inspired internal confirmation layer without changing MT5 or CLI behavior.

Key review concerns addressed during the patch:

- Internal state calculation no longer depends on `Show Internal Structure`; that toggle now controls visuals, not logic.
- Internal pivots must occur after the active swing break/dealing range start before they can arm iBOS.
- Premium/discount uses a dedicated active dealing range from confirmed swing breaks rather than a loose latest-high/latest-low pair.
- Active EQ, strong internal, and weak internal levels reuse line/label handles instead of creating a new active level object each bar.
- Historical iBOS, internal pivot, and fractal labels are capped in clean mode.
- Bullish and bearish swing break handling is mutually exclusive on the same bar.

## Residual Risks

- Pine compilation still needs to be verified in TradingView because there is no local Pine compiler in this workspace.
- Strong/weak level semantics are a first tuning pass; visual replay should decide whether weak targets should use swing extremes, newly formed internal pivots, or both.
- Sweep labels remain uncapped from the previous implementation when sweeps are shown. They are off by default, but should be capped in a later cleanup if sweep debug mode becomes common.
- The dashboard was not expanded yet; the state label is the intended tuning surface for this first pass.

## Suggested Replay Checks

- Confirm CHOCH can appear without promoting the model to confirmed iBOS.
- Confirm bullish iBOS promotes `Strong iL` and `Weak iH`.
- Confirm bearish iBOS promotes `Strong iH` and `Weak iL`.
- Confirm a close through a strong internal level flips the internal state label.
- Confirm hiding internal visuals does not change the state label behavior.
