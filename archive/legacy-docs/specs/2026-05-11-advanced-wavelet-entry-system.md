# Advanced Wavelet Entry System Spec

Date: 2026-05-11
Owner: Codex

## Purpose

Build a next-generation MT5/MQL5 entry-signal research system that improves on Hybrid WPVS by scoring transparent wavelet confluence instead of loosening thresholds on the existing signal.

This is a research and live-demo validation package only. It must not claim profitability without MT5 Strategy Tester reports, real-tick parity, and forward validation.

## Current Architecture Summary

The current playground architecture separates signal generation, diagnostics, and execution:

- `Hybrid_Wavelet_Pivot_Volume_Spike.mq5` is the existing non-trading closed-bar indicator.
- `Hybrid_WPVS_DiagnosticEA.mq5` exports CSV diagnostics and forward-return labels.
- `Hybrid_WPVS_Top3_ExecutionEA.mq5` is the current proof-of-concept execution harness for GBPUSD, AUDUSD, and USDJPY M5.
- `docs/playgrounds/hybrid-wpvs-execution-playground.html` captures the latest WPVS research state: high-confidence `0.80` signals, time exits, no ATR stop for current leaders, and real-tick/forward validation as the next gate.

The Advanced Wavelet system reuses this architecture pattern, but it does not inherit WPVS results or replace the live-demo files.

## New Components

- `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/MQL5/Indicators/Advanced_Wavelet_Entry_Signal.mq5`
- `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/MQL5/Experts/Advanced_Wavelet_Entry_ResearchEA.mq5`

Existing Hybrid WPVS files must remain untouched.

## Indicator Contract

The indicator must:

- expose current bar shift `0` as blank;
- calculate closed historical bars from the candidate bar and older bars only;
- avoid future-bar pivots/fractals;
- avoid tick retraining or adaptive model fitting;
- expose buffers for signal direction, score, wavelet energy, noise ratio, volume ratio, pivot/structure context, debug reason code, ATR, spread, pivot distance, structure class, ATR/range quality, rejection quality, and trend bias.

Missing historical spread values are treated as unknown instead of falling back to current market spread, preventing old signals from changing as live spread changes.

## EA Contract

The EA must:

- read the indicator through `iCustom` and `CopyBuffer`;
- make decisions from shift `1` only;
- default to observe-only with `InpAllowTrading=false`;
- write signal CSV rows separately from trade/event CSV rows;
- delay forward-return labels until the future bars have closed;
- support optional tiny demo trades only when explicitly enabled;
- enforce one position per symbol/magic and optional one position per symbol;
- use demo-account guard, spread guard, daily max-trade guard, daily loss guard, FOK preference, exact-ticket close, and a hard research lot cap;
- use `OnTester()` as a bounded ranking heuristic, not as profitability evidence.

## Reuse vs Replace

Reuse:

- WPVS closed-bar `iCustom`/`CopyBuffer` pattern.
- CSV-first diagnostics.
- Observe-only defaults and tiny `0.01` demo trade sizing.
- Trading.com no-hedging, FIFO-aware, spread-aware operating assumptions.
- Per-symbol presets and validation discipline.

Replace:

- The WPVS signal logic itself.
- Broad low-threshold discovery as a promotion path.
- Any assumption that 1-minute OHLC proof-of-concept results imply tradability.

## Validation Requirements

1. Compile the indicator first, then the EA.
2. Run Phase 1 diagnostic CSV discovery with optimization off and forward off.
3. Analyze signal count, forward returns, spread burden, active months, year stability, symbol stability, and single-trade dependency.
4. Run execution smoke tests only after signal CSV evidence.
5. Promote settings only after real-tick and Forward = 1/3 validation.
