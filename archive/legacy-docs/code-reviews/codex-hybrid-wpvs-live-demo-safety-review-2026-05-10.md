# Hybrid WPVS Live-Demo Safety Review

Date: 2026-05-10
Reviewer: code-reviewer agent plus Codex integration pass
Target: `metatrader5_cli/mt5/mql5/Hybrid_WPVS_MT5_Bundle/Hybrid_WPVS_Top3_ExecutionEA.mq5`

## Findings

### P1 - Observe-only mode must not mutate the account

The first patch only blocked new entries, but `ManageOpenPosition()` could still close positions while `InpAllowTrading=false`. That would make observe-only unsafe if a matching position already existed.

Status: Fixed. Added `InpAllowPositionManagement`, defaulting to `false`, and `ManageOpenPosition()` now returns immediately unless that input is enabled. Observe-only presets set both trading and position management to false.

### P2 - One raw magic number was shared across symbols

The prior EA used `InpMagicNumber` directly for every pair. That is workable in isolated tester runs, but live-demo chart deployment is cleaner with symbol-specific magic IDs.

Status: Fixed. Added `InpUseAutoSymbolMagic` and `g_effective_magic`, derived once in `OnInit()` and used for trade setup, position filters, history filters, and logs.

### P2 - Signal learning would stop when order gates block trades

Only executed trades were visible in logs. For daily analysis, blocked and research signals need to be recorded too.

Status: Fixed. Added `InpLogSignals`, `InpUseCommonFiles`, and `InpSignalLogFileName`. Closed-bar signals now write CSV rows with direction, score, spread, volume ratio, wavelet regime, structure class, debug reason, trade status, and block reason.

### P2 - Trading.com live-demo constraints need explicit defaults

The Trading.com skill calls out no hedging, FIFO, 1:50 leverage, spread-only costs, market execution, and common FOK filling issues.

Status: Fixed for this proof-of-concept. The EA still uses one net position per symbol/effective magic, live presets use fixed 0.01 lots, FOK filling, 10-point deviation, spread gates, max trades/day, daily loss cutoff, and demo-account-only mode.

## Verification

- MetaEditor compile succeeded after patching: 0 errors, 0 warnings.
- Patched EA was copied to the MT5 terminal `MQL5\Experts` folder.
- Live-demo presets were copied to `MQL5\Profiles\Tester`.

## Residual Risk

This is still a proof-of-concept signal system with low validated trade cadence. The observe-only preset should run first on GBPUSD, AUDUSD, and USDJPY M5 before enabling tiny-trade presets. Lower-threshold signals are for research only until they are separately tested.
