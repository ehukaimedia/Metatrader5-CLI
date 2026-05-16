# Advanced Wavelet Entry Safety Review

Date: 2026-05-11
Reviewer: Codex plus advisor, feature-dev, and code-reviewer agents

## Findings

### P1 - Hedging accounts could close the wrong same-symbol position

Status: Fixed.

The EA found an owned ticket but closed by symbol. It now closes by exact ticket, which is safer for hedging-capable terminals and manual same-symbol exposure.

### P1 - Lot normalization could silently increase risk

Status: Fixed.

The EA no longer clamps a smaller configured size up to the broker minimum. It blocks the trade when configured lots are below the symbol minimum, above the symbol maximum, or above `InpMaxSafetyLots`. Presets set `InpMaxSafetyLots=0.01`.

### P2 - CSV export could fail when `WaveletResearch` did not exist

Status: Fixed.

The EA creates the parent folder before opening CSV files.

### P2 - Daily trade-count guard reset on EA restart

Status: Fixed.

The EA reconstructs today's opened deal count from history on initialization and when a new trading day starts.

### P2 - Missing historical spread could make old indicator gates depend on current spread

Status: Fixed.

The indicator treats missing historical spread as unknown/pass-through rather than using current `SYMBOL_SPREAD` for old bars.

### P3 - Forward-return CSV headers were fixed to defaults

Status: Fixed.

Signal CSV headers now include the configured `InpForwardBars*` horizons.

### P3 - `OnTester()` used unbounded raw terms

Status: Fixed.

The custom tester score now uses bounded profit, expected-payoff, and recovery components plus trade count, drawdown, and profit factor terms. It remains only a ranking heuristic.

## Verification

- MetaEditor compile after fixes: indicator `0 errors, 0 warnings`.
- MetaEditor compile after fixes: EA `0 errors, 0 warnings`.
- Existing Hybrid WPVS live-demo files were not edited.

## Residual Risk

No MT5 Strategy Tester backtest was run in this pass. The system is compile-ready research infrastructure, not evidence of profitability. Real-tick and Forward = 1/3 validation remain required before any live-demo tiny-trade promotion.
