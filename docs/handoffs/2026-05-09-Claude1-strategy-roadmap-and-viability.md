# Strategy Roadmap, Viability Check, and Broken-vs-Untuned Diagnostic

Date: 2026-05-09
Author: Claude1 (independent reviewer)
Coordinator: Picard
Context: Pre-iter1 strategic thinking — running while operator unblocks Inputs side and Codex1 builds .set files

## Current State

- Pair: USDJPY M5
- Window: 2026-01-01 → 2026-05-08 (4 months, real-tick)
- iter-0 baseline: 22 trades, -$59.05 net, PF 0.23, expectancy -2.68 USD/trade, 22.7% WR, **0 full-TP hits, 1 near-full-SL (-0.77R), 21 trail-closed**

## 1. Iteration Roadmap with Target Metrics

### Phase 3 graduation criteria (proposed thresholds)

A "profitable USDJPY M5 baseline" must clear ALL of:

| Metric | Threshold | Rationale |
|---|---|---|
| Profit factor (PF) | ≥ 1.20 | Below 1.0 is unprofitable; 1.20 has margin for live slippage degradation |
| Expectancy per trade | ≥ +0.10R | Positive R-expectancy is the only reliable forward predictor |
| Min trade count | ≥ 15 in test window | Sample size discipline; iter-0 had 22 — adequate |
| Max equity drawdown | ≤ 5% of deposit | Risk discipline; strategy that hits 10% DD on backtest hits 20%+ live |
| At least 1 trade hits ≥ +1.5R | required | Proves the TP path is reachable — not 100% trail-closed |

**Stretch goal (transcript-19 Photon target):** ≥ +0.50R expectancy and PF ≥ 1.50. Aim there; graduate at the floor.

### 3-iteration tree

```
iter-0 (baseline)        Chandelier 3.0  + BE 0.80R   →   PF 0.23, 0 TPs, 21 trail-closed
            |
            v
iter-1 (paired loosening) Chandelier 4.0  + BE 1.20R   →   IN FLIGHT (operator running)
            |
            +-- if PF ≥ 1.20 + expectancy ≥ +0.10R → CONFIRMED, advance to EURUSD cross-check
            |
            +-- if some trade hits +1.5R+ but PF still < 1.0 → trail direction right, push further
            |
            +-- if no improvement → iter-2
            v
iter-2 (isolate BE)      Chandelier 3.0  + BE 1.20R   →   isolates which knob mattered
            |
            +-- if iter-2 better than iter-1 → BE was the culprit; tune BE further (1.5? disable?)
            |
            +-- if iter-2 same as iter-0 → BE alone isn't enough; multiplier needed
            |
            +-- if both iter-1 and iter-2 fail → iter-3
            v
iter-3 (disable BE)      Chandelier 3.0/4.0  + BE OFF (InpUseBreakeven=false)
            |
            This is the cleanest test of "does the trail work without the BE-trigger interaction?"
            BE may be the dominant failure: data shows multiple +0.06/+0.11/+0.13 wins
            consistent with "BE locked then noise hit BE → tiny win" pattern.
            If iter-3 still fails → entry semantics, not management. Substrate switch needed.
```

iter-3 candidates I considered and rejected for now:
- **InpDefaultRR 3.0 → 2.0**: irrelevant when 0 trades hit TP. Don't tune until trail-loosening lets some trades reach TP.
- **InpMinTDAScore 70 → 60**: gating is healthy (22% READY rate is normal). Loosening gates would add lower-quality setups, not fix the trail problem.
- **InpRiskPercent 0.25 → higher**: sizing is correct. Position sizes scale 0.05-0.26 per stop distance. This affects $ outcomes only, not R-distribution.

**Discipline:** never change >2 knobs in one iteration. If a change works, lock it before moving the next knob.

## 2. Strategy Viability Sanity Check

### Is USDJPY M5 the right substrate?

**Yes, REASONABLE substrate. Not actively misleading.**

Pros:
- Tight Trading.com spreads (~1-2 pips) on USDJPY
- 22 trades in 4 months = ~5.5/month — on the low end but enough for hypothesis testing
- Strategy correctly identified the 156→160 uptrend bias (21 LONG / 1 SHORT)
- Photon 3-tier structure on D1/H4/M15 + M5/M1 entry-trigger is the textbook configuration

Cons (caveats to flag):
- M5 spread is a larger fraction of structural SLs than M15. Memory note from prior POC: "GBPJPY 5.2 pip SL eaten in 11s by spread+noise." That failure mode is partly mitigated by our pair-class minimum stop floor (150 pts on JPY) but not fully.
- JPY crosses have wider noise bands than majors. EURUSD M5 with same logic might show different R-distribution shape.
- 99 setup evaluations over 4 months means ~0.34% of M5 bars produced a journaled setup. Healthy selectivity, but limits sample size.

### What I would change if iter1+iter2+iter3 all fail on USDJPY M5

**Substrate cross-check: EURUSD M5, same Jan-Apr window.**

Reasoning:
- EURUSD has the cleanest noise profile of major pairs (no carry-trade dynamics, no Tokyo session discontinuity)
- If EURUSD M5 with iter-0 baseline params is profitable → USDJPY M5 was actively misleading us; JPY-noise is the issue
- If EURUSD M5 with iter-0 baseline ALSO fails → the EA itself has an entry-semantic problem; substrate isn't the issue
- This shortcuts the question "is this strategy fundamentally workable" without committing to more management tuning

**Alternative substrate I considered: USDJPY M15.** Photon transcripts often demonstrate M15 as the "trade-idea" timeframe with M5 as confirmation. If we set `InpSetupTF=M15, InpEntryTF1=M5`, the EA already does this — but the per-bar evaluation is on InpEntryTF1=M5. Switching to InpEntryTF1=M15 would re-evaluate per M15 bar — fewer setups, larger SL distances, possibly less noise-eating. Worth testing as a variation IF EURUSD M5 also fails.

### Recommendation for Q2

**Stay USDJPY M5 for iter-1, iter-2. After iter-2 result lands:**

- If iter-1 OR iter-2 hits graduation criteria → run EURUSD M5 with the WINNING params as Phase 3 prequel cross-check
- If both iter-1 and iter-2 fail → run EURUSD M5 with iter-0 baseline params (NOT the failed-tune params) before iter-3. This isolates "is the strategy workable AT ALL" from "is the management tuning right."
- Only after substrate cross-check fails do we reach for iter-3 (disable BE) or larger entry-semantic changes.

This sequence could indeed shortcut weeks of management-tuning if EURUSD M5 immediately shows the entry logic is sound and the only problem is JPY-specific noise tuning.

## 3. Broken vs. Untuned: Bright-Line Signals

### Signals that the strategy is FUNDAMENTALLY broken (entry semantics wrong)

Stop tweaking management knobs and question entry logic when ANY of:

1. **iter-3 still shows zero full-TP hits AND ≥90% trail-out exits.** Means trades never develop to profit regardless of management. Entry is mistimed — likely entering at end of move not start.

2. **Median MFE per trade < 1R across all iterations.** MFE = Maximum Favorable Excursion. If trades never even MOVE 1R in the favorable direction before reversing, the entry signal isn't capturing institutional follow-through. Need to pull this from MT5's detailed `.tst` report — exits.csv only has final realized_r, not MFE.

3. **Win rate stays < 30% across 3 iterations with realized R-distribution near zero.** Entry signal isn't directional — wins vs losses are near random.

4. **EURUSD M5 substrate cross-check ALSO fails on iter-0 baseline params.** Eliminates pair-specificity. The EA's setup logic itself is the problem.

5. **Trade entries cluster in low-volume sessions (Asia post-Tokyo close, dead hours).** Suggests the structure detector is firing on illiquid moves that don't develop. Check via the screenshot's "Entries by hours" panel.

### Signals that the strategy is JUST UNTUNED (management wrong, entry sound)

Continue tuning management when ALL of:

1. **Median MFE per trade ≥ 1.5R but realized R << MFE.** Trades reach favorable territory but management exits early. Pure trail-tuning problem.

2. **Trail-closed trades are mostly in the intended direction (positive MFE).** Entry direction is correct; exit logic killed potential profit.

3. **iter-3 (disable BE) shows different R-distribution shape than iter-0.** Means BE-trigger interaction is the culprit. Tune Chandelier in isolation next.

4. **Some trade in any iteration hits +1.5R+ realized.** Proves the TP path is reachable; we just need management that doesn't kill it.

### Concrete next-step IF iter-1 disappoints

When iter-1 results land, **first thing I should compute**: per-trade MFE/MAE distribution (from MT5's detailed .tst report or ComputeFromBars helper if needed). If median MFE < 1R, **pull the emergency brake on management tuning** — entry is the issue. If median MFE > 1.5R, **green-light iter-2** — trail is the issue, keep tuning.

This is the bright line.

## TL;DR for Picard

- **Graduation:** PF ≥ 1.20, +0.10R expectancy, ≥15 trades, ≤5% DD, ≥1 trade reaching +1.5R
- **iter-3:** disable BE entirely (Chandelier-only management) — cleanest test of BE-trigger interaction
- **Substrate:** stay USDJPY M5 for iter-1/iter-2. If both fail, run EURUSD M5 with iter-0 BASELINE (not failed-tune) params before iter-3
- **Broken vs untuned bright line:** median MFE per trade. <1R → entry broken; ≥1.5R → trail untuned. Compute from .tst report after iter-1 lands
