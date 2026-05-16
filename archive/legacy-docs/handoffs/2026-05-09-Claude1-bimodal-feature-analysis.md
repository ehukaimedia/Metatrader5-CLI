# Bimodal Strong-vs-Noise Feature Analysis — iter-0

Date: 2026-05-09
Author: Claude1 (independent reviewer)
Coordinator: Picard
Dataset: `docs/backtests/20260509-140741-USDJPY-M5-manual/`
Population: 7 strong (ext_MFE_r ≥ 1.5R) / 3 mid (1.0–1.5R) / 12 noise (<1R)

## TL;DR

**Honest finding: the features currently in the journal weakly separate strong from noise.** Best candidates are Friday DOW and high entry-to-SL distance (initial risk), each removing only 2-3 noise trades without touching strong. **TDA score is NOT a separator** — strong and noise have identical score distributions (median 93 in both). Score-gating will not fix this.

This means filter-discovery alone cannot get us to profitability. The bimodality is real but not predictable from what we currently record. Recommend a parallel three-track approach: weak filter additions for free wins, iter-1 + EURUSD substrate cross-check for strategy diagnosis, and richer journal columns for stronger feature analysis on future iters.

## Cross-Tab Results (per-feature distribution)

Each feature compared across the three buckets. n=7 strong / n=3 mid / n=12 noise.

### TDA score — NOT A SEPARATOR
- Strong: mean 92.71, median 93, range 81-100
- Noise: mean 94.17, median 93, range 81-100
- Mid: mean 91.67, median 93, range 89-93
- **Conclusion**: noise scores are slightly *higher* on average. The score formula doesn't predict outcome. Score-tightening (e.g. `InpMinTDAScore` 70 → 90) would NOT improve the strong:noise ratio — the bad trades have high scores too.

### Initial risk (entry-to-SL distance, price units) — WEAK SEPARATOR
- Strong: median 0.223, max 0.449
- Noise: median 0.301, max 0.744
- Mid: median 0.331
- **Filter candidate**: skip when initial_risk > 0.50 (~50 pips on USDJPY).
  - Removes: 2 noise (positions 8 with risk 0.744, 22 with risk 0.704)
  - Keeps: 7 strong (max strong is 0.449)
  - Mid: 0 affected
- **Effect size**: 2 noise trades dropped, 0 strong dropped. Modest.
- **Mechanism**: high initial_risk = high M5 ATR at entry = wider SL = same price move equals smaller R-multiple. High-vol entries are R-handicapped even when direction is right.

### Day of week — WEAK SEPARATOR
- Strong DOW: Mon 1, Sun 1, Tue 1, Wed 2, Thu 2, **Fri 0**
- Noise DOW: Mon 2, Tue 3, Wed 1, Thu 3, **Fri 3**
- Mid DOW: Wed, Thu, Fri 1 each
- **Filter candidate**: skip Friday entries.
  - Removes: 3 noise (positions 22, 6, 32)
  - Keeps: 7 strong (zero on Fri)
  - Mid: 1 affected
- **Effect size**: 3 noise dropped, 0 strong dropped. Modest.
- **Hypothesis**: Friday position-squaring + thinner liquidity in late session caps follow-through.

### Hour of day — NO CLEAN SIGNAL
- London (7-13): Strong 4, Noise 7
- Asia (0-7): Strong 1, Noise 2
- Late (17-24): Strong 2, Noise 2
- NY (13-17): Strong 0, Noise 1
- Both populations dominate the London session. The single NY-noise trade isn't a population-level signal.

### Direction — TRIVIAL (1 SELL)
- 21 of 22 trades are BUY (correct, USDJPY trended up). The lone SELL was noise. Direction isn't an actionable filter.

### MAE_R (max adverse excursion) — POST-HOC SIGNAL
- Strong: median 0.133, max 0.453
- Noise: median 0.211, max 0.886
- **NOT usable as entry filter** (MAE only knowable after the trade plays out).
- Could be used as *early-exit* management: "close if MAE > 0.7R within 3 bars." Iter-3 candidate.

### VP read — NO SEPARATION
- Strong: above_poc 5, below_poc 1, inside_value 1
- Noise: above_poc 8, below_poc 1, inside_value 3
- Both populations dominated by `above_poc` (BUYs above POC). VP context doesn't predict outcome.

### Liquidity reason — NO SEPARATION
- Strong: sweep_only 5, sweep_plus_front 2
- Noise: sweep_only 8, sweep_plus_front 4
- Identical pattern.

### POI timeframe — NO SEPARATION
- Strong: M1 6, M15 1
- Noise: M1 11, M5 1
- Both populations heavy on M1 FVGs.

### Spread at entry — VERY WEAK
- Strong: median 14 pts, max 18
- Noise: median 15 pts, max 18
- 1-point median difference — within noise.

### Month — NO SEPARATION
- Strong: Jan 1, Mar 5, Apr 1
- Noise: Jan 3, Mar 6, Apr 3
- Both populations heavy in March (USDJPY's most directional month).

## Combined Filter — Modest Impact

Apply BOTH `skip Friday` AND `skip initial_risk > 0.50`:
- Trades removed: pos 22 (Fri+high-risk, 1 trade — overlap), pos 6 (Fri), pos 32 (Fri), pos 8 (high-risk Mon)
- Net: **4 noise dropped, 1 mid dropped, 0 strong dropped**
- Remaining population: 7 strong / 2 mid / 8 noise = 17 trades

Projected impact on iter-0 expectancy:
- Original: -0.11R/trade → -2.42R total
- Drop 4 noise (avg realized -0.20R each ≈ -0.80R total) + drop 1 mid (avg ≈ +0.05R)
- New total ≈ -2.42 + 0.80 - 0.05 ≈ -1.67R / 17 trades = -0.10R/trade
- **Still negative**. Filters help marginally, not enough to graduate.

## Why The Features Are Weak

Hypothesis on why current features don't predict outcome:

1. **Score formula has low variance for READY trades.** Score = 25 (HTF, always +25 for READY) + 20 (FVG ok, always) + 10 (zone, varies) + 20 (sweep, always) + 10 (front liq, varies) + 20 (entry confirmed, always for READY) + VP (varies ±8) + trap (-25 if true). For READY rows, most components are constant. Variance is small ⇒ score isn't predictive.

2. **The features we record are "this setup passed the gates" features**, not "this market context is favorable" features. We don't capture HTF momentum strength, room-to-run before next swing high, time-since-prior-sweep, or M5/M1 structure divergence.

3. **Sample size limit.** 22 trades with 7-12-3 split has high variance. With ~50 trades a Friday signal of 25%-of-noise might confirm or evaporate. iter-1 doubles the data.

4. **The bimodality may be inherent**, not predictable. Photon's framework has a stochastic element — institutional follow-through doesn't always manifest. Some post-sweep entries develop, others don't, with broader market state determining which (state we don't capture).

## Strategic Implications

**Filter-discovery alone cannot get us to profitability** with current features. The bimodal split is real, but the noise tail isn't isolatable by what we record.

What this means for Picard's decision:

### Q2: PIVOT vs WAIT vs SUBSTRATE — recommend a parallel three-track approach

**Track A — Apply weak filters now (free, low risk).**
Add to iter-1 or iter-2:
- `InpSkipFriday=true` (new bool input; cheap to add)
- `InpMaxInitialRiskPips=50` (new int input; cheap to add)
These cost zero compute and projected to lift expectancy from -0.11R to -0.10R. Not graduation but a clean directional signal.

**Track B — Iter-1 still runs (cheap, in flight).**
Iter-1's looser trail will reveal whether the strong:noise bimodality persists when management isn't truncating recorded MFE. If iter-1 still shows ~7 strong / 12 noise, the entry semantics are stochastic at our feature granularity.

**Track C — EURUSD M5 substrate cross-check (highest signal value).**
Run iter-0 BASELINE params on EURUSD M5 same Jan-Apr window. Cross-check tells us:
- If EURUSD shows similar 7:12 bimodality → strategy-level stochastic, not pair-specific
- If EURUSD strong:noise ratio is much better (e.g. 11:5) → JPY-noise is killing strong-trade follow-through; JPY-specific tuning needed
- If EURUSD is also bad but in a different way → entry semantics need rework

Cost: one operator backtest run. Highest information yield.

### Q3: Path-to-profitability hypotheses, ranked

**Hypothesis A — Weak filters + iter-1 trail loosening (lowest cost, modest gain).**
- `InpSkipFriday=true` + `InpMaxInitialRiskPips=50` + iter-1's Chandelier 4.0 + BE 1.20R
- Projected: ~17 trades, expectancy +0.10 to +0.20R, PF ~1.0-1.2
- Borderline graduation. May not clear ≥1 trade ≥+1.5R requirement consistently.
- **Cheapest test of "good enough."**

**Hypothesis B — Add richer journal features, do another iter (medium cost, high information).**
Codex1 patches EA to log per-trade:
- `htf_momentum_d1`: directional strength on D1 (e.g. close-vs-open/range)
- `time_since_sweep_bars`: bars since the swept extreme was set
- `room_to_swing_high_pips`: distance to next M15 swing high
- `spread_to_atr_ratio`: relative spread cost
- `m5_m1_event_lag_bars`: timing offset between M5 sweep and M1 BOS

Then re-run + re-analyze. Expected to surface a STRONGER separator with this richer feature set (sample of 22 → 50+ when iter-1+iter-2 merged).

**Hypothesis C — Entry-semantic change (high cost, biggest potential).**
Pull from Phase 4 VP backlog: require post-sweep entry AT VP zone-boundary (not just FVG mid). The VP zone-boundary rule might filter the strong subset structurally.

### Recommendation

**Run all three tracks in parallel.**

1. **Track A** (filters): Codex1 ships `.set` overlay for next iter with `InpSkipFriday=true` + `InpMaxInitialRiskPips=50` ALONG WITH iter-2's BE-only tune. Tests filters AND BE isolation in one rerun.

2. **Track C** (substrate): operator runs EURUSD M5 baseline (iter-0 params) when iter-1 finishes. This is the SINGLE most informative test we can run; data lands within hours.

3. **Track B** (richer features): Codex1 patches EA to log the 5 richer columns. This is a 1-hour patch + one rerun. Lands on iter-3's data.

After all three tracks land:
- If filters + BE isolation get us to PF 1.20+: graduate to EURUSD multi-pair (Phase 3 prequel).
- If EURUSD baseline is dramatically better: pivot to JPY-noise-tuning (different ATR multipliers, different spread caps).
- If richer features reveal a strong separator: iterate on filters (gate the noise out).
- If all three fail: pivot to Hypothesis C entry-semantic change (VP zone-boundary entries).

This sequence converges on the truth in 2-3 operator runs instead of N iterations of management tuning.

## Detail: All 22 Trades

```
Bucket POS DIR DAY HR MO SCORE IRISK MFE_R MAE_R EXT_R EVT POI VP            LIQ
N      12  BUY Tue 8  3  81    0.176 0.068 0.886 0.07  sl  M1  inside_value  sweep_only
N      14  BUY Tue 19 3  93    0.169 0.036 0.308 0.16  sl  M1  above_poc     sweep_only
N      40  BUY Thu 6  4  93    0.186 0.194 0.414 0.19  sl  M1  above_poc     sweep_only
N      22  BUY Fri 11 3  93    0.704 0.055 0.216 0.27  sl  M1  above_poc     sweep_only
N      36  BUY Thu 9  4  100   0.150 0.333 0.180 0.33  sl  M5  above_poc     sweep_plus_front
N      6   BUY Fri 12 1  93    0.382 0.348 0.628 0.35  sl  M1  above_poc     sweep_only
N      2   BUY Tue 11 1  99    0.273 0.198 0.168 0.41  sl  M1  inside_value  sweep_plus_front
N      20  BUY Thu 15 3  100   0.150 0.220 0.207 0.41  sl  M1  above_poc     sweep_plus_front
N      8   SELL Mon 3 1  93    0.744 0.437 0.231 0.56  sl  M1  below_poc     sweep_only
N      24  BUY Wed 22 3  93    0.330 0.294 0.103 0.69  sl  M1  above_poc     sweep_only
N      38  BUY Mon 12 4  99    0.438 0.009 0.123 0.74  sl  M1  inside_value  sweep_plus_front
N      32  BUY Fri 12 3  93    0.458 0.703 0.046 0.81  sl  M1  above_poc     sweep_only
M      34  BUY Thu 3  4  93    0.413 0.383 0.048 1.12  sl  M1  above_poc     sweep_only
M      44  BUY Wed 14 4  93    0.331 0.178 0.387 1.14  sl  M1  above_poc     sweep_only
M      10  BUY Fri 0  3  89    0.150 0.173 0.333 1.19  sl  M1  inside_value  sweep_only
S      30  BUY Tue 8  3  89    0.223 0.812 0.242 1.86  sl  M1  inside_value  sweep_only
S      42  BUY Wed 12 4  93    0.207 0.662 0.237 2.39  sl  M1  above_poc     sweep_only
S      18  BUY Thu 7  3  93    0.449 0.000 0.116 2.85  sl  M1  above_poc     sweep_only
S      28  BUY Mon 20 3  81    0.375 0.261 0.035 3.02  tp  M1  below_poc     sweep_only
S      26  BUY Sun 19 3  100   0.150 0.240 0.133 3.03  tp  M1  above_poc     sweep_plus_front
S      4   BUY Thu 12 1  93    0.302 0.053 0.126 3.03  tp  M1  above_poc     sweep_only
S      16  BUY Wed 6  3  100   0.150 0.120 0.453 3.08  tp  M15 above_poc     sweep_plus_front
```

Note position 18 (strong, ext_MFE 2.85R) — interesting case: native_MFE 0.000 (the trade went immediately against from entry to original SL exit, never showed favorable in actual trade life). Yet held to hypothetical TP/SL with original anchor, it WOULD have peaked at +2.85R. This is a vivid case of "trail truncated everything good." 1468 extended bars to that hypothetical exit (~5 days). The original entry was sound; the trade just needed time the management didn't allow.
