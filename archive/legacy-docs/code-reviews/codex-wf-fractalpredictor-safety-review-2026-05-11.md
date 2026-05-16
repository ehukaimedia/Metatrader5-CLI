# WF Fractal Predictor Safety Review - 2026-05-11

## Scope

Reviewed the installed MT5 package:

- `C:\Users\arsen\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Indicators\WF_FractalPredictor.mq5`
- `C:\Users\arsen\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\WF_FractalTrainerEA.mq5`
- `C:\Users\arsen\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Include\WF_FractalPredictorCore.mqh`

## Compile

PASS.

- `WF_FractalPredictor.mq5`: 0 errors, 0 warnings.
- `WF_FractalTrainerEA.mq5`: 0 errors, 0 warnings.

## Safety Checklist

| Area | Status | Notes |
| --- | --- | --- |
| Future leakage | PASS | Features for predictions are built from shift `1`, the last closed bar, and older bars only. Fractal labels are processed at `InpFractalRightBars + 1`, after the required right-side bars have closed. |
| Closed-bar learning | PASS | Both indicator and trainer process model updates only on new bars. Tick-by-tick retraining is avoided. |
| Confirmed fractals | PASS | `WF_IsHighFractal` and `WF_IsLowFractal` require older left bars and newer right bars; the new-bar processing offset avoids using the forming bar as confirmation. |
| Historical prediction repainting | CAUTION | The indicator clears and redraws visible buffers, and only writes the current closed-bar prediction at buffer shift `1`. It does not maintain a persistent historical prediction trail. This avoids rewriting old predictions, but it also means past prediction arrows are not preserved for visual audit. |
| Confirmed label repainting | PASS | Confirmed HH/HL/LH/LL labels are historical labels that appear after the fractal confirmation delay. |
| Overhead | PASS | EA uses `CopyRates` for a bounded required window on each new bar. Indicator redraws a bounded `InpDrawBars` range. Adaptive profile count is capped by `WF_MAX_PROFILES=8`. |
| File output | PASS | Model CSV and generated `.set` files use `FILE_COMMON`, so they write under `Terminal\Common\Files`. |
| Optimization frames | PASS | `OnTester()` returns the custom score and sends optimization-segment frames with `FrameAdd`. Forward frames are intentionally excluded from best-preset selection. |
| Demo trading safety | CAUTION | Trading defaults to disabled, but the EA does not enforce demo-account-only execution. Live/demo safety depends on account selection, Algo Trading controls, and `InpEnableDemoTrading`. |

## Patch Notes

No MQL5 code patch was required for compile or serious safety issues.

Documentation was updated to clarify install paths, final-training overrides, candidate-vs-forward-validated presets, model mutation during online learning, filename scope, and demo-account risk.

## Recommended Next Validation

1. Run a short Strategy Tester smoke test before launching a five-year optimization.
2. For the five-year run, set Strategy Tester `Forward` manually to `1/3`.
3. Reject optimization presets unless the forward segment remains acceptable.
4. Preserve a frozen CSV model for evaluation by disabling indicator saves or using a separate `InpModelTag`.
