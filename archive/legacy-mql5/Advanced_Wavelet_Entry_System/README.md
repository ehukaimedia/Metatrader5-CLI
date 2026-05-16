# Advanced Wavelet Entry System for MT5/MQL5

Research package for a closed-bar, non-repainting, wavelet-confluence entry signal and a diagnostic/execution EA.

This is a proof-of-concept research system. It is not a profitability claim, not a finished trading product, and not intended for real-money deployment without independent MT5 Strategy Tester reports, forward-validation evidence, and live-demo observation.

## Package contents

```text
MQL5/Indicators/Advanced_Wavelet_Entry_Signal.mq5
MQL5/Indicators/Advanced_OrderFlow_Proxy_Confluence.mq5
MQL5/Experts/Advanced_Wavelet_Entry_ResearchEA.mq5
Sets/Advanced_Wavelet_ObserveOnly.set
Sets/Advanced_Wavelet_DiagnosticCSV.set
Sets/Advanced_Wavelet_ActiveDemoTinyTrade.set
Sets/Advanced_Wavelet_HighConfidence_080.set
Sets/Advanced_Wavelet_GBPUSD_M5.set
Sets/Advanced_Wavelet_AUDUSD_M5.set
Sets/Advanced_Wavelet_USDJPY_M5.set
Sets/Advanced_Wavelet_USDJPY_M5_HC80_OFProxy_Diagnostic.set
Sets/Advanced_Wavelet_EURJPY_M5.set
Sets/Advanced_Wavelet_GBPJPY_M5.set
Sets/Advanced_Wavelet_AUDJPY_M5.set
SAFETY_REVIEW.md
OPTIMIZATION_PLAN.md
CSV_SCHEMA.md
compile_with_metaeditor.bat
```

## Install paths

Copy the files into the MT5 data folder, not the application install folder.

1. MT5: `File > Open Data Folder`.
2. Copy `MQL5/Indicators/Advanced_Wavelet_Entry_Signal.mq5` to:
   `MQL5\Indicators\Advanced_Wavelet_Entry_Signal.mq5`
3. Copy `MQL5/Indicators/Advanced_OrderFlow_Proxy_Confluence.mq5` to:
   `MQL5\Indicators\Advanced_OrderFlow_Proxy_Confluence.mq5`
4. Copy `MQL5/Experts/Advanced_Wavelet_Entry_ResearchEA.mq5` to:
   `MQL5\Experts\Advanced_Wavelet_Entry_ResearchEA.mq5`
5. Open MetaEditor and compile the indicators first, then the EA.
6. The `.set` files can be loaded from Strategy Tester > Inputs > Load.

The EA calls the indicator through `iCustom(_Symbol, _Period, "Advanced_Wavelet_Entry_Signal", ...)`, so the indicator must be compiled to `MQL5\Indicators\Advanced_Wavelet_Entry_Signal.ex5` before the EA is run.

## Component 1: indicator

`Advanced_Wavelet_Entry_Signal.mq5` is a chart-window indicator. It exposes the requested buffers plus extra diagnostic buffers for CSV analysis.

### Buffer map

| Buffer | Name | Meaning |
|---:|---|---|
| 0 | `BuySignalPrice` | Buy arrow price, `EMPTY_VALUE` if no buy signal |
| 1 | `SellSignalPrice` | Sell arrow price, `EMPTY_VALUE` if no sell signal |
| 2 | `DirectionState` | `+1` buy, `-1` sell, `0` no exposed signal |
| 3 | `SignalScore` | Final normalized candidate score, 0.0 to 1.0 |
| 4 | `WaveletEnergyScore` | Normalized multi-scale wavelet energy/regime score |
| 5 | `NoiseRatio` | High-frequency energy divided by total wavelet energy; lower is better |
| 6 | `VolumeAnomalyRatio` | Current closed-bar tick volume divided by prior baseline |
| 7 | `PivotStructureContext` | Signed pivot-quality context; positive buy, negative sell |
| 8 | `DebugReasonMask` | Bitmask showing passed/blocked features |
| 9 | `ATR` | Closed-bar ATR used for normalization |
| 10 | `SpreadPoints` | Historical/current spread points used by the indicator filter |
| 11 | `PivotDistanceATR` | Distance to relevant prior support/resistance in ATR units |
| 12 | `StructureClass` | `+2` HH/HL, `+1` upside breakout, `0` neutral, `-1` downside breakout, `-2` LH/LL |
| 13 | `ATRRangeQuality` | Candle range quality normalized by ATR |
| 14 | `RejectionQuality` | Directional rejection/impulse candle quality |
| 15 | `TrendBiasClass` | `+1`, `0`, or `-1` simplified structure bias |

## Component 1b: order-flow proxy companion indicator

`Advanced_OrderFlow_Proxy_Confluence.mq5` is a closed-bar diagnostic companion indicator. It does not replace the Advanced Wavelet signal, does not trade, and does not claim true footprint data. It exports spot-FX-safe proxy buffers that can later be joined to wavelet signals by the research EA.

The research EA can optionally read this indicator with `InpUseOrderFlowProxy=true`. In that mode, trade decisions remain unchanged; the EA writes schema-versioned `*_ofproxy_v2.csv` diagnostics for bucket analysis.

### Buffer map

| Buffer | Name | Meaning |
|---:|---|---|
| 0 | `OFProxyDelta` | Signed bar pressure proxy from body efficiency, close location, and tick-volume surprise |
| 1 | `OFProxyDivergence` | Rolling closed-bar price-vs-proxy divergence |
| 2 | `OFProxyAggression` | Candle-level aggression proxy |
| 3 | `OFProxyStackedPressure` | Consecutive same-side proxy pressure near prior structure |
| 4 | `OFProxyAbsorption` | High-effort, poor-progress proxy near structure |
| 5 | `OFProxyConfluenceScore` | Signed proxy bias, `[-1,+1]` |
| 6 | `OFProxyRawState` | `+1` bullish, `-1` bearish, `0` neutral, `2` mixed, `-2` invalid |
| 7 | `OFProxyReasonCode` | Debug bitmask for data availability and proxy logic |
| 8 | `OFProxyDataMode` | `1` bar proxy, `-1` invalid/not ready in EA CSV; tick enrichment is not enabled in v1 |

### Debug bitmask

| Bit | Value | Meaning |
|---:|---:|---|
| 0 | 1 | Proxy data available |
| 1 | 2 | Bar-proxy mode |
| 4 | 16 | Buy-side delta proxy |
| 5 | 32 | Sell-side delta proxy |
| 6 | 64 | Price body and delta proxy agree |
| 7 | 128 | Bullish divergence proxy |
| 8 | 256 | Bearish divergence proxy |
| 9 | 512 | Buy aggression proxy |
| 10 | 1024 | Sell aggression proxy |
| 11 | 2048 | Buy stacked-pressure proxy |
| 12 | 4096 | Sell stacked-pressure proxy |
| 13 | 8192 | Selling absorbed / bullish absorption proxy |
| 14 | 16384 | Buying absorbed / bearish absorption proxy |
| 15 | 32768 | Prior structure present |

## Component 2: Research/Execution EA

`Advanced_Wavelet_Entry_ResearchEA.mq5` reads buffer shift `1` only. It supports:

- observe-only diagnostic mode by default;
- optional demo-only tiny-trade mode when `InpAllowTrading=true`;
- one position per symbol/magic;
- current-spread filtering;
- daily max-trade guard;
- daily realized-loss guard;
- optional account-wide daily guard scope via `InpDailyGuardsAccountWide`;
- hard research lot cap via `InpMaxSafetyLots`;
- tiny-demo presets set `InpDailyGuardsAccountWide=true` so the daily guard can see other same-account activity;
- optional ATR SL/TP;
- no-SL/no-TP time-exit research;
- delayed, non-leaking forward-return CSV labels;
- `OnTester()` custom optimization score;
- optional `FrameAdd()` optimization-pass metadata.

## Signal logic summary

The indicator scores a setup from confluence rather than firing on every volume spike. The score combines:

- Haar-like multi-scale wavelet energy using the signal bar and older bars only;
- high-frequency noise ratio;
- tick-volume anomaly versus older baseline;
- ATR-normalized candle impulse/range quality;
- rejection candle quality;
- prior support/resistance distance using older bars only;
- structure class from older HH/HL or LH/LL context;
- spread and optional session filter;
- optional trend-bias alignment.

The current forming bar, shift `0`, is deliberately blank. Live and tester decisions use shift `1` only.

## Non-repaint and future-leak design

The indicator computes each closed-bar candidate from the candidate bar and older bars only. It does not use fractal confirmation, future pivots, or any newer bars relative to the candidate. The EA reads `CopyBuffer(..., start_pos=1, count=1, ...)` for decisions.

Forward returns in the signal CSV are delayed. A signal is stored in memory, and the EA writes the row only after the configured forward horizons have actually closed. At tester end, incomplete rows may be written as `partial` if `InpWriteIncompleteForwardRowsOnDeinit=true`.

## CSV output location

CSV files are written through MQL5 file functions into the MT5 file sandbox:

- normal terminal: `MQL5\Files\WaveletResearch\...`
- Strategy Tester agent: tester agent `MQL5\Files\WaveletResearch\...`

Default filenames are:

```text
<symbol>_<timeframe>_<run_tag>_signals.csv
<symbol>_<timeframe>_<run_tag>_trades.csv
```

Use `InpSignalCSVFile` and `InpTradeCSVFile` to override names.

## Recommended first test sequence

### Phase 1: Diagnostic CSV discovery

1. Use `Advanced_Wavelet_DiagnosticCSV.set`.
2. `InpAllowTrading=false`.
3. Timeframe: M5.
4. Symbols: first GBPUSD, AUDUSD, USDJPY; then EURJPY, GBPJPY, AUDJPY, NZDUSD, USDCAD, USDCHF.
5. Model: start with 1-minute OHLC for signal discovery.
6. Period: five years where broker history exists.
7. Export and compare signal CSVs.

### Phase 2: Signal analysis

Rank symbol/threshold combinations by:

- signal count;
- average forward return after 12/24/48 bars;
- win rate by forward horizon;
- spread burden;
- stability across years;
- stability across symbols;
- avoidance of one-trade dependency.

### Phase 3: Execution smoke test

1. Use `Advanced_Wavelet_ActiveDemoTinyTrade.set` only on a demo account.
2. Fixed lot: `0.01`.
3. Compare:
   - threshold 0.70, time exit 24;
   - threshold 0.70, time exit 48;
   - threshold 0.80, time exit 24;
   - threshold 0.80, time exit 48.
4. Start with no ATR SL/TP. Then compare ATR variants.

### Phase 4: Optimization

Only optimize after diagnostic CSV evidence. Start with fast genetic optimization and forward = 1/3. Use a small parameter set. Do not optimize every scoring weight at once.

### Phase 5: Forward validation

Reject settings if forward performance collapses, trade count is too low, results depend on one large trade, drawdown is excessive, only one symbol works, or live-demo behavior diverges sharply from tester behavior.

## Suggested optimization ranges

See `OPTIMIZATION_PLAN.md` for staged ranges and pass/fail criteria.

## OFProxy CSV analysis helper

After observe-only `*_ofproxy_v2.csv` runs, use the local analyzer to compare direction-aware proxy buckets:

```powershell
python metatrader5_cli\mt5\mql5\Advanced_Wavelet_Entry_System\tools\analyze_ofproxy_csv.py --symbols GBPUSD,AUDUSD
```

The default report is written to:

```text
metatrader5_cli\mt5\mql5\Advanced_Wavelet_Entry_System\reports\ofproxy_direction_comparison_2026-05-11.md
```

## Safety review

See `SAFETY_REVIEW.md`. Important defaults:

- `InpAllowTrading=false`.
- `InpDemoAccountsOnly=true`.
- `InpLots=0.01`.
- `InpMaxSafetyLots=0.01`.
- one position per symbol/magic.
- per-symbol magic hashing enabled.
- daily trade and daily loss guards enabled.
- spread filters enabled.

## Compile note

This workspace has MetaEditor installed at `C:\Program Files\MetaTrader 5\MetaEditor64.exe`. `compile_with_metaeditor.bat` was run after the safety patch and both the indicator and EA compiled with `0 errors, 0 warnings`. Treat the terminal-side compile after installation as the authoritative runtime check.
