# Claude1 Independent Review — USDJPY M5 Iteration-0 Baseline

Date: 2026-05-09
Reviewer: Claude1 (independent)
Coordinator: Picard
Artifact: `docs/backtests/20260509-135019-USDJPY-M5-manual/`
Verdict: **[REVIEW-OK]** — confirms prior tuning recommendation, no contract drift

## Artifact Cleanliness

Dedupe fix verified at source:
- entries.csv: 22 rows + header = 22 unique entries (was 44 in pre-dedupe smoke)
- exits.csv: 22 rows + header = 22 unique exits
- failures.csv: 0 rows (no order_send failures)
- setups.csv: 99 rows + header = 99 setup evaluations

## Trade Outcomes (USDJPY M5, 2026-01-01 → 2026-05-08)

| Metric | Value |
|---|---|
| Trades | 22 |
| Net P/L | -$59.05 (-0.59% on $10k) |
| Wins | 5 / Losses | 17 |
| Win rate | 22.7% |
| Profit factor | 0.23 |
| Largest win | +$9.60 (+0.37R) |
| Largest loss | -$18.96 (-0.77R) |
| LONG / SHORT | 21 / 1 |
| Trades hitting full TP (≥+3R) | **0** |
| Trades hitting near full SL (≤-0.85R) | 1 |
| Trades closed via trailed SL (|R| < 0.50) | 21 |

## R-Distribution (sorted, with bucketing)

```
|R| ≤ 0.10:  +0.00, +0.06, +0.11, +0.13, -0.00, -0.04, -0.06, -0.07, -0.07, -0.07  → 10 trades (45%)
0.10 < |R| ≤ 0.30:  +0.37 (only positive in bucket), -0.12, -0.15, -0.16, -0.17, -0.17, -0.21, -0.21, -0.24, -0.27, -0.31  → 11 trades (50%)
0.30 < |R| ≤ 0.50:  none
|R| > 0.50:  -0.77  → 1 trade (5%)
```

## Q1: Is Chandelier-pulled-SL still the dominant exit failure mode?

**YES — confirmed and stronger than prior smoke.**

Evidence: 21/22 trades (95%) closed at trailed SL with |R| < 0.50. Only 1 trade approached the original SL anchor (-0.77R). **Zero trades hit full TP.** The pattern is unmistakable:
- Trail closes most trades before they can develop
- Wins are capped at small fractional R (best win +0.37R, never near +3R TP)
- Losses are mostly partial-R because BE+Chandelier protected before full SL

Strategy correctly identified the long bias on USDJPY (21 LONG vs 1 SHORT, on a 156→160 uptrend), but the trail management ate the moves before TP.

## Q2: Tuning recommendation — confirm or adjust?

**Prior recommendation stands**: InpChandelierATRMultiplier 3.0 → 4.0, InpBETriggerR 0.80 → 1.20 (paired change, dispatched by Picard).

Reasoning re: paired vs single-knob:
- The two knobs are coupled: BE moves SL to break-even at 0.80R; Chandelier (multiplier 3.0) then trails ATR×3 below recent high. Both contribute to the "trail too tight" failure.
- Paired change tests the directional hypothesis fastest. If expectancy improves materially, we know "loosen the trail" is correct.
- If iteration-1 fails to improve, **isolate BE next** (BE 1.20R alone with Chandelier back at 3.0). The R-distribution shows clusters of +0.06/+0.11/+0.13 (BE-locked then trailed-out) — BE timing looks more impactful than Chandelier multiplier.
- Iteration discipline: never change >2 knobs in one iteration.

Other knobs to stay AWAY from in iteration 1:
- InpDefaultRR 3.0 — irrelevant when 0 trades hit TP. Don't tune until trail-loosening lets some trades reach TP.
- InpMinTDAScore 70 — gating is fine (22 READY of 99 logged is healthy ratio).
- InpRiskPercent 0.25 — sizing is correct, position sizes vary 0.05-0.26 per stop distance.

## Q3: Single-pair iteration vs cross-check now?

**Single-pair this iteration. Cross-check after iteration-1 result.**

Argument for staying single-pair right now:
- We're testing one hypothesis (trail too tight). Adding a second pair before iteration-1 result confounds the test.
- Operator already manually re-running USDJPY M5 with the new params; that result IS the next data point we need.

Argument for cross-checking AFTER iteration-1:
- Once we see whether Chandelier 4.0 + BE 1.20R improves USDJPY, run the SAME params on EURUSD M5 same date range. Tells us:
  - If both pairs improve → the trail-loosening is universal. Phase 3 11-pair likely benefits.
  - If only USDJPY improves → JPY-cross-specific (the spread/noise issue from project memory). Phase 3 needs per-pair Chandelier multipliers.
  - If neither improves → revisit assumption; isolate BE first.

Recommend Picard queue the EURUSD M5 cross-check as iteration 1.5 (after iteration-1 USDJPY rerun lands).

## Q4: Contract / Photon-SMC drift?

**No drift. Gates firing as designed.**

Setup distribution from setups.csv:
| Status | Count | % |
|---|---|---|
| READY | 22 | 22.2% |
| WATCH (entry) — sweep+structure aligned, waiting LTF BOS/CHOCH/iBOS | 49 | 49.5% |
| WATCH (spread) — spread > 30 points | 10 | 10.1% |
| WATCH (score) — score < 70 threshold | 10 | 10.1% |
| WATCH (quote_side_or_structure) | 6 | 6.1% |
| WATCH (rollover) — 21:00-22:59 GMT window | 2 | 2.0% |

This is exactly the expected distribution:
- 22% READY → 22 trades placed
- 50% of WATCH in "entry" state means structure + sweep aligned, waiting on LTF trigger close — that's the Photon mechanical "armed but not triggered" state. Working as designed.
- Spread + score + rollover gates firing correctly.
- All 22 trades use magic 176879 (USDJPY pair magic), 0 order_send failures.
- Exit reasons: all 22 are "sl <price>" — that's MT5's broker-side deal comment for "stop triggered" which includes both original-SL and Chandelier-trailed-SL hits. Matches contract.

Per Photon framework, post-sweep entries with SL behind swept extreme should not be stopped out by noise. The R-distribution shows that's HOLDING — only 1 trade hit a "real" SL (-0.77R). The other 21 were closed by the EA's own trail logic, not by adverse moves. **Contract intent is preserved**; the issue is in the trail tuning, not in the entry/SL semantics.

## Verdict

**[REVIEW-OK]** — Prior tuning recommendation stands (paired Chandelier 4.0 + BE 1.20R dispatched). After iteration-1 lands, recommend EURUSD M5 cross-check on the winning params before broader Phase 3 11-pair.

If iteration-1 doesn't improve expectancy materially, next iteration isolates BE trigger (1.20R alone, Chandelier back to 3.0).
