# Hybrid WPVS Top-3 Execution Plan

Date: 2026-05-10

## Context

The Hybrid WPVS diagnostic exporter showed the cleanest high-confidence M5 signal behavior on:

- GBPUSD
- AUDUSD
- USDJPY

The current working filter is `InpMinSignalScore=0.80` with closed-bar signals only and the strict structure filter:

- Buy HL enabled
- Buy LL disabled
- Sell HH enabled
- Sell LH disabled

Rejected or watchlist symbols should not be included in the first execution basket.

## Next Artifact

Create a separate execution EA rather than modifying the diagnostic exporter.

The execution EA should:

- Read `Hybrid_Wavelet_Pivot_Volume_Spike` through `iCustom`.
- Enter only on closed bar shift `1`.
- Trade only `GBPUSD`, `AUDUSD`, and `USDJPY` by default.
- Use fixed conservative lots for first validation.
- Exit after a configurable number of M5 bars.
- Include optional ATR stop and optional ATR take profit.
- Avoid diagnostic future-return logic completely.

## First Validation Preset

Use:

- Fixed lot: `0.01`
- Signal score: `0.80`
- Exit after: `24` M5 bars
- ATR stop: enabled at `2.50` ATR
- ATR take profit: disabled
- Optimization: disabled

## Current Snapshot

The first execution sweep found that the no-ATR-stop time-exit variants were cleaner than the ATR-stop variants in the initial 1 minute OHLC tests:

- GBPUSD: `Hybrid_WPVS_Top3_GBPUSD_M5_TimeExit48_NoATRStop.set`
  - 48-bar time exit
  - First-sweep net result: `+28.44`
- AUDUSD: `Hybrid_WPVS_Top3_AUDUSD_M5_TimeExit24_NoATRStop.set`
  - 24-bar time exit
  - First-sweep net result: `+31.75`
- USDJPY: `Hybrid_WPVS_Top3_USDJPY_M5_TimeExit24_NoATRStop.set`
  - 24-bar time exit
  - First-sweep net result: `+22.34`

These results are a research checkpoint only. They were captured from M5 tests over `2021.05.09` to `2026.05.09` using 1 minute OHLC modeling, fixed `0.01` lots, and a `10000` deposit.

## Tester Sequence

Run individual 5-year M5 backtests for:

1. GBPUSD
2. AUDUSD
3. USDJPY

Reject the EA configuration if actual trade P/L diverges materially from the diagnostic edge because of spread, stop behavior, or trade timing.

Only after the first execution pass should we compare `InpExitAfterBars=48` against `24`.

## Next Validation

Run the same three pair-specific presets with:

- Modeling: Every tick based on real ticks
- Optimization: disabled
- Forward: no for the first real-tick parity check

If the real-tick pass remains stable, repeat with `Forward = 1/3`. Reject any pair/preset where the forward segment collapses or depends on too few trades.

The dashboard memory for this decision path lives in:

`docs/playgrounds/hybrid-wpvs-execution-playground.html`
