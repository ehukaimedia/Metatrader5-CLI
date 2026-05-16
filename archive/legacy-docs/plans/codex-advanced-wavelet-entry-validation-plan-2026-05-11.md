# Advanced Wavelet Entry Validation Plan

Date: 2026-05-11
Owner: Codex

## Minimal Implementation Plan

1. Preserve all existing Hybrid WPVS files.
2. Keep the downloaded Advanced Wavelet files under a new package path.
3. Patch safety/workflow defects found during review:
   - close exact owned tickets;
   - block unsafe lot auto-scaling;
   - create CSV folders;
   - reconstruct daily trade counts from history;
   - keep historical spread handling deterministic;
   - make CSV forward headers match configured horizons;
   - bound `OnTester()` components.
4. Compile indicator and EA with MetaEditor.
5. Add workspace-level spec, plan, safety review, and architecture playground docs.

## Validation Workflow

### Phase 1: Diagnostic CSV discovery

- Timeframe: M5.
- Modeling: 1-minute OHLC first.
- Trading: disabled.
- Optimization: disabled.
- Initial symbols: GBPUSD, AUDUSD, USDJPY.
- Candidate JPY crosses: EURJPY, GBPJPY, AUDJPY.
- Additional majors: NZDUSD, USDCAD, USDCHF.

Rank by signal count, 12/24/48-bar returns, spread burden, active months, year stability, symbol stability, and one-trade dependency.

### Phase 2: Execution smoke tests

- Use `0.01` lots.
- Keep `InpMaxSafetyLots=0.01`.
- Compare score thresholds `0.70` and `0.80`.
- Compare 24-bar and 48-bar time exits.
- Start without ATR SL/TP, then test ATR variants only after time-exit behavior is understood.

### Phase 3: Optimization

Use fast genetic optimization only after CSV discovery shows enough signal quality. Keep the optimized parameter set small:

- wavelet window;
- wavelet levels;
- minimum wavelet energy;
- maximum noise ratio;
- volume multiplier;
- pivot lookback;
- score threshold;
- time exit bars;
- spread limit.

Forward = 1/3 remains a Strategy Tester setting, not an EA input.

### Phase 4: Live Demo Observation

Attach observe-only presets first. Tiny-trade mode is demo-only and should be enabled only after CSV and tester evidence justify it.

## Current Verification

MetaEditor compile was run from `metatrader5_cli/mt5/mql5/Advanced_Wavelet_Entry_System/compile_with_metaeditor.bat` after safety patches:

- `Advanced_Wavelet_Entry_Signal.mq5`: 0 errors, 0 warnings.
- `Advanced_Wavelet_Entry_ResearchEA.mq5`: 0 errors, 0 warnings.
