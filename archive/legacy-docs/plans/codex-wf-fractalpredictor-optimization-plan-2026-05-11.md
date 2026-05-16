# WF Fractal Predictor Optimization Plan - 2026-05-11

## Status

- Package installed into the active MT5 data folder.
- Indicator and trainer EA compile with 0 errors and 0 warnings.
- A command-line smoke-test config was prepared in `tmp/wf_fractal_smoke.ini`, but the terminal launch exited immediately without producing WF artifacts. Use the MT5 Strategy Tester UI for the first validation run.

## Tester Setup

Use Strategy Tester:

- Expert: `WF_FractalTrainerEA`
- Symbol: start with `EURUSD` or `USDJPY`
- Period: `M5`
- Date: last five fully available broker-history years
- Forward: `1/3` in the Strategy Tester UI
- Optimization: Fast genetic first
- Modeling: Every tick based on real ticks if available; otherwise 1 minute OHLC for initial proof-of-concept speed
- Deposit: `10000`
- Demo trading input: `InpEnableDemoTrading=false`

## Stage A - Broad Sanity

Optimize a small set first:

| Input | Start | Step | Stop |
| --- | ---: | ---: | ---: |
| `InpFractalLeftBars` | 2 | 1 | 5 |
| `InpFractalRightBars` | 2 | 1 | 5 |
| `InpATRPeriod` | 10 | 2 | 20 |
| `InpWaveletWindow` | 32 | 16 | 128 |
| `InpLearningRate` | 0.005 | 0.005 | 0.050 |
| `InpConfidenceThreshold` | 0.30 | 0.05 | 0.60 |
| `InpMaxAdaptiveProfiles` | 3 | 1 | 8 |

Keep fixed initially:

- `InpAdaptiveWavelets=WF_ADAPT_BALANCED`
- `InpATRLongPeriod=100`
- `InpMaxWaveletLevel=3`
- `InpMomentumFast=8`
- `InpMomentumSlow=34`
- `InpRangeLookback=80`
- `InpL2Shrink=0.00001`
- `InpSoftmaxTemperature=1.0`

## Stage B - Narrow

Choose a stable Stage A region, then narrow the ranges around the best cluster. Do not optimize every input at once.

## Stage C - Forward Validation

Reject candidates when:

- Forward profit factor or custom score collapses versus the optimization segment.
- Drawdown is excessive.
- Trade/sample count is too low.
- Results depend on one unusually large trade.
- The setup works on one symbol but fails broadly on other major pairs.

Record training and forward values before the final full-history pass.

## Stage D - Final Artifact Run

Run a normal non-optimization test over the full five-year range using the chosen inputs:

- Forward: No
- `InpLoadWeights=false`
- `InpResetWeights=true`
- `InpSaveWeightsOnDeinit=true`
- `InpExportSetFiles=true`
- `InpExportIndicatorLiveSet=true`
- `InpExportEALiveSet=true`
- `InpSetFileTag=LIVE`
- `InpEnableDemoTrading=false`

Expected artifacts in `C:\Users\arsen\AppData\Roaming\MetaQuotes\Terminal\Common\Files`:

- `WF_FractalPredictor_<tag>_<symbol>_<timeframe>.csv`
- `WF_FractalPredictor_<tag>_<symbol>_<timeframe>_LIVE_INDICATOR.set`
- `WF_FractalTrainerEA_<tag>_<symbol>_<timeframe>_LIVE_EA.set`

## Demo Preset Guidance

For frozen paper evaluation, set the indicator to avoid mutating the trained CSV:

- `InpOnlineLearning=false`

Or, if observing online adaptation:

- copy the trained CSV first, or use a unique `InpModelTag`
- keep the original final-training CSV as the validation baseline

Do not attach the demo EA to a live account. The EA does not enforce account type.
