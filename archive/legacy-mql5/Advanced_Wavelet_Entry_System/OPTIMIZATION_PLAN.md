# Optimization Plan

## Principle

Optimize only after Phase 1 diagnostic CSV analysis shows enough closed-bar signal count and stable forward-return behavior. Keep the parameter set small to avoid curve-fitting.

## Stage 0: fixed baseline

Run observe-only diagnostics first:

- M5
- five years where data exists
- 1-minute OHLC discovery
- initial symbols: GBPUSD, AUDUSD, USDJPY
- candidate symbols: EURJPY, GBPJPY, AUDJPY, NZDUSD, USDCAD, USDCHF

## Stage 1: coarse signal settings

Optimize a limited set:

| Input | Start | Step | Stop |
|---|---:|---:|---:|
| `InpIndWaveletWindow` | 32 | 16 | 96 |
| `InpIndWaveletLevels` | 3 | 1 | 5 |
| `InpIndMinWaveletEnergyScore` | 0.25 | 0.05 | 0.55 |
| `InpIndMaxNoiseRatio` | 0.48 | 0.04 | 0.72 |
| `InpIndMinVolumeAnomaly` | 1.00 | 0.10 | 1.50 |
| `InpIndPivotLookback` | 24 | 12 | 72 |
| `InpSignalThreshold` | 0.65 | 0.05 | 0.85 |
| `InpTimeExitBars` | 12 | 12 | 48 |
| `InpEntryMaxSpreadPoints` | symbol-specific | 5 | symbol-specific + 20 |

Keep `InpUseATRStops=false` for the first execution smoke tests.

## Stage 2: structure and trend filters

Only after Stage 1 finds stable regions:

- test `InpIndUseTrendBiasFilter=false/true`;
- test `InpIndRequireRejectionQuality=false/true`;
- test `InpIndRequirePivotProximity=false/true`.

Reject filter combinations that reduce signal count too aggressively or only work on one symbol.

## Stage 3: ATR stops

After time-exit variants are understood:

| Input | Start | Step | Stop |
|---|---:|---:|---:|
| `InpUseATRStops` | false | boolean | true |
| `InpATRStopLossMult` | 1.0 | 0.25 | 2.5 |
| `InpATRTakeProfitMult` | 1.0 | 0.25 | 3.5 |

Compare against no-SL/no-TP time-exit runs.

## Custom optimization score

`OnTester()` combines bounded net-profit, expected-payoff, profit-factor, and recovery components with trade-count and equity-drawdown penalties. It intentionally penalizes:

- low trade count;
- negative profit;
- high equity drawdown percentage;
- weak recovery;
- weak profit factor.

This score is a ranking heuristic only. It does not replace forward testing.

## Pass/fail criteria

Reject settings when any of the following is true:

- forward period collapses badly versus optimization period;
- trade count is too low for the tested period;
- profit depends on one oversized trade;
- drawdown is too high for demo research tolerance;
- only one symbol works;
- real ticks disagree materially with 1-minute OHLC discovery;
- live-demo behavior differs sharply from tester behavior;
- active months are too sparse.

## Suggested acceptance target for next research round

A setting deserves deeper real-tick validation only if it shows:

- enough trades to analyze by year;
- similar behavior across at least two or three symbols;
- stable 12/24/48-bar forward labels;
- acceptable spread burden;
- no obvious single-trade dependency.
