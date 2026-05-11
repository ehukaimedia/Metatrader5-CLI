# Backtest Tuning Playground — Design Spec v1

Date: 2026-05-09
Designer: Claude1
Implementer: Codex1
Coordinator: Picard
Constraint: Must accept any `docs/backtests/*-USDJPY-M5-manual/` directory as input

## Purpose

A self-contained HTML playground that teaches the team **where the leverage is** in tuning EhukaiTDAEA from PF 0.23 (iter-0 baseline) to a profitable configuration (PF ≥ 1.20 graduation target). Built on REPLAY of recorded trades, not full re-simulation.

The user is a teammate (or operator) who wants to **internalize** what iter-0 evidence is telling us — not just read a number, but feel why the trail is too tight, see the wins capped, watch the equity curve change shape when BE is disabled. The playground turns abstract metrics into visceral pattern recognition.

## Compute Model: REPLAY ONLY (with caveats)

**Decision:** Replay recorded trades against re-applied exit logic. NOT full mechanical re-simulation.

Reasoning:
- Ships in hours, not days
- Captures 80% of v1 teaching value (lessons 1-4 below all only need replay)
- Honest about limits: only models exit-logic changes (Chandelier mult, BE trigger, BE on/off, RR multiplier), NOT entry-logic changes (gates, score, sweep semantics)
- Pure JS in the browser; no MT5 dependency at runtime

**Required input data per trade** (exit-logic replay needs more than current exits.csv has):
- Entry time, direction, entry price
- Original SL price, original TP price (planned)
- **MFE (Maximum Favorable Excursion) — peak unrealized profit during trade**
- **MAE (Maximum Adverse Excursion) — peak unrealized loss during trade**
- Exit time, exit price, realized R
- Tick value, tick size (for $-to-R conversion)

The MFE/MAE are NOT in current CSVs. Two paths:
1. **Parse MT5's detailed `.tst` HTML report** — MT5 already records MFE max / MAE max per trade. Codex1 builds an HTML parser. (Recommended for iter-0 data we already have.)
2. **Patch EA to journal MFE/MAE** — track per-position high/low in `ManageOpenPosition`, write to exits.csv on close. (Recommended for iter-1+ — every future run has this.)

Codex1 should do BOTH: parse MT5 HTML for iter-0 backward compat AND patch EA for forward-compat. The playground reads from a unified `trade_summary.json` that the data-prep step produces from either source.

## Lessons (3-5 highest-leverage)

Pick from iter-0 evidence; ordered by build complexity ascending:

### Lesson 1 — Trail closes 95% of trades (visceral; no compute beyond classification)
Show the 22 iter-0 trades as a horizontal strip, one dot per trade. Color by exit type:
- Red (filled): closed at near-original-SL (|realized_R| > 0.85 × planned_SL_R) — 1 trade
- Yellow (filled): closed at trailed-SL (|realized_R| ≤ 0.85 × planned_SL_R, exit_reason = "sl") — 21 trades
- Green (filled): closed at TP — 0 trades
- Gray hollow: BE-closed (|realized_R| < 0.05) — subset of yellow

When the user sees that 21 of 22 dots are yellow, the lesson "trail dominates" lands instantly.

### Lesson 2 — Every win is capped vs planned TP (no compute beyond planned-vs-realized)
For each WIN, render two stacked bars:
- Solid green = realized R
- Dashed outline = planned R (TP distance / SL distance ratio = InpDefaultRR)

Iter-0: best win is +0.37R inside a +3.0R outline. The visual gap IS the lesson.

### Lesson 3 — BE-trigger sits inside the noise band (replay needed)
Histogram of realized R bucketed in 0.05R bins, with a vertical line at `+InpBETriggerR` (0.80 in iter-0, 1.20 in iter-1).

Show two histograms side-by-side:
- "BE on" (current behavior): cluster around 0.0R from BE-locked-then-trailed-out trades
- "BE off" (replay): for each trade, recompute exit assuming BE never fires. Use MFE to determine when Chandelier alone would have closed.

The shape change between histograms is the lesson. Iter-0 hypothesis: "BE off" shrinks the 0.0R cluster and fattens the right tail.

### Lesson 4 — Direction is correct (counterfactual; no compute)
Show a "what if every trade just held until the next daily close" counterfactual:
- For each trade, compute what would have happened if exit was at "next D1 close" instead of trailed SL
- Plot equity curve: original (gray dashed) vs counterfactual hold (green if positive, red if negative)

Iter-0 hypothesis: counterfactual hold IS profitable on USDJPY's uptrend. The lesson: entry direction is right; only the exit kills it.

### Lesson 5 — Knob coupling (defer to v2 — needs heatmap matrix)
2D heatmap of expectancy with x = Chandelier multiplier (2.0-6.0), y = BE trigger R (0.0-2.0 plus "off"). Computed by replaying all 22 trades against the (mult, BE) cell. Color shows expectancy. Hover shows (PF, WR, trades).

This is THE money chart for finding the profitability ridge — but requires running replay 100×100 cells. Cheap in JS but UI complexity is higher. **Defer to v2.**

## Controls (v1)

Pane on the left side of the playground:

1. **Backtest dataset dropdown** — auto-discovers folders matching `docs/backtests/*-USDJPY-M5-manual/`. Defaults to most-recently-modified. Reload re-runs the data-prep + replay.

2. **Chandelier ATR multiplier slider** — 2.0 → 6.0, step 0.1. Default = current InpChandelierATRMultiplier from EA-source-default constant (3.0 for iter-0, 4.0 for iter-1).

3. **BE trigger R slider** — 0.0 → 2.0, step 0.05. Default = current InpBETriggerR (0.80 / 1.20).

4. **BE on/off toggle** — when off, BE step is skipped in replay. Tests iter-3 hypothesis directly.

5. **Default RR slider** — 1.0 → 5.0, step 0.5. Default 3.0. Affects TP placement → affects which trades hit TP in replay.

6. **Time-of-day filter (advanced, collapsible)** — checkbox grid of 24 hours. Unchecked = drop trades whose entry hour is in that hour. Tests "session clustering" hypothesis.

7. **"Reset to baseline" button** — snaps all sliders back to the dataset's recorded EA defaults.

8. **"Compare to baseline" button** — splits the views into 2 columns: baseline (left) vs current-knobs (right).

## Views (v1)

Right side of playground, four panels stacked or tabbed:

### Panel A — Trade Strip
Horizontal strip of 22 dots (or however many trades the dataset has). Sorted by entry date. Color-coded by exit type. Hover shows full trade details (time, direction, entry, SL, TP, MFE, MAE, realized R, exit reason). When sliders move, dots may change color (a trail-closed trade might become TP-closed if Chandelier mult is high enough).

### Panel B — R Distribution Histogram
Realized R bucketed in 0.05R bins. Two overlays:
- Baseline (gray, semi-transparent)
- Current-knobs (solid color)

When sliders move, the colored histogram redraws.

### Panel C — Equity Curve
X-axis: trade index. Y-axis: cumulative $ profit. Two lines:
- Baseline (gray dashed)
- Current-knobs (solid blue)

Final value annotated. PF, expectancy, WR, max DD shown as a chip cluster above.

### Panel D — MFE vs Realized R Scatter
**THE diagnostic chart.** X-axis: MFE in R-multiples (max favorable). Y-axis: realized R. 22 points. Diagonal line at y=x represents "captured all of MFE." Points below diagonal = "left R on the table."

Iter-0 hypothesis: most points cluster well below diagonal. The visual gap from diagonal is the leverage. KEY for broken-vs-untuned diagnosis (per my prior handoff): if median MFE < 1R, entry is broken; if median MFE > 1.5R, trail is just untuned.

Color points by exit type (matches Panel A).

### Header strip — Headline metrics
Always visible: Trades / Win Rate / Profit Factor / Expectancy / Max DD / Net P&L. Two columns: baseline vs current-knobs. Highlight when current-knobs crosses graduation thresholds (PF 1.20, expectancy +0.10R, ≥1 trade ≥+1.5R).

## Replay Algorithm (sketch — for Codex1)

For each trade in the dataset:
```
input: entry_time, direction, entry_price, original_SL, original_TP, MFE_R, MAE_R, planned_TP_R
input: chandelier_mult, be_trigger_R, be_on, default_RR

# Re-derive TP based on knob
new_TP_R = default_RR
new_TP_price = entry + direction * (original_SL_distance * new_TP_R)

# Replay exit:
if MFE_R >= new_TP_R:
    exit_R = new_TP_R    # TP would have been hit before any trail kicked in
elif be_on and MFE_R >= be_trigger_R:
    # BE armed at some point
    if MAE_R_after_be < 0.05:    # we don't have MAE_after_BE precisely, approximate
        exit_R = ~ 0     # closed at BE
    else:
        exit_R = approximate_chandelier_exit_R(MFE_R, MAE_R, chandelier_mult)
elif MAE_R >= 1.0:
    exit_R = -1.0        # original SL hit
else:
    exit_R = approximate_chandelier_exit_R(MFE_R, MAE_R, chandelier_mult)
```

The `approximate_chandelier_exit_R` is the trickiest part. Without bar-level price history, we approximate:
- Chandelier closes when price retraces (chandelier_mult × ATR) from peak
- We don't have ATR per trade, but we can approximate: ATR_estimate ≈ MFE_R × 0.3 (rough heuristic) or use the EA's logged ATR snapshot
- Better: have Codex1 patch the EA to ALSO journal the trade's avg-ATR-during-life, so replay has accurate ATR
- v1 acceptable: use a constant ATR_R ≈ 0.4 (point estimate) and document the simplification visibly

If approximation causes too much divergence between replay and ground truth, the playground annotates "approximation — exact replay requires bar-level history." Better to be honest than precise-looking.

## Ship Criterion (v1)

V1 ships when:
- ✓ Loads `docs/backtests/20260509-135019-USDJPY-M5-manual/` (iter-0) cold and renders all four panels
- ✓ "Backtest dataset" dropdown picks up iter-1 once it lands without code change
- ✓ Chandelier slider visibly changes Panels B + C + D when moved
- ✓ "BE off" toggle visibly changes Panels B + C
- ✓ Headline metrics update on every knob change
- ✓ Visual baseline-vs-current comparison toggle works
- ✓ Single-file HTML (data inlined or fetched from a sibling JSON), self-contained
- ✓ Approximation caveat visible in UI when replay extrapolates

Deliberately deferred to v2:
- Knob heatmap (Lesson 5)
- Multi-pair comparison
- Full mechanical re-sim with entry-logic knobs
- Live tick replay against MT5 history
- Saving / sharing tuned configurations

## File Layout (proposed for Codex1)

```
docs/playgrounds/
  ehukai-tda-tuning-playground.html   # the playground (single file)
metatrader5_cli/mt5/core/
  playground_data.py                   # data prep: backtests/<run>/ → trade_summary.json
  playground_data_test.py              # unit tests
metatrader5_cli/mt5/cli/                # or wherever
  playground command                   # `mt5 playground build --run <run-id>` produces the JSON
```

The `mt5 playground build` CLI command takes a backtest run ID, reads its CSVs + (optionally) the .tst file, computes trade_summary.json with MFE/MAE/etc., and either writes it next to the playground OR inlines it into the HTML for self-containedness.

## EA Journal Patch (parallel work)

For iter-1+ to have native MFE/MAE without parsing MT5's HTML report, Codex1 also patches the EA:

In `ManageOpenPosition` (or a new `TrackPositionExtremes` helper called per tick):
- For each open position: track running max(profit_distance) and min(profit_distance) since entry
- On exit (in JournalExitDeal), write MFE_R = max_profit / initial_risk and MAE_R = min_profit / initial_risk into the exits.csv schema
- Add columns: `mfe_r`, `mae_r`, `bars_held`, `atr_at_entry`

This is a small EA patch; pure additive. No compile risk. Update the existing test `test_summarize_run_counts_journal_rows` to verify new columns.

## Handoff to Codex1

Codex1 implements with these phases:

**Phase 1** — Data prep:
- `playground_data.py`: read CSVs from `docs/backtests/<run>/`, parse MT5 HTML report for MFE/MAE if present, fall back to "MFE = realized_R for wins, MAE = realized_R for losses" approximation if not. Output `trade_summary.json` schema'd as documented above.
- CLI: `mt5 playground build --run <run-folder> [--inline]`
- Tests: load fixture iter-0 directory, verify trade_summary.json has 22 trades with required fields.

**Phase 2** — EA journal patch:
- Add `mfe_r`, `mae_r`, `bars_held`, `atr_at_entry` columns to exits.csv
- Track in ManageOpenPosition; emit in JournalExitDeal
- Update test_summarize_run

**Phase 3** — Playground HTML:
- Single file at `docs/playgrounds/ehukai-tda-tuning-playground.html`
- Vanilla JS + d3 or Chart.js for charts (no build step)
- Loads trade_summary.json from sibling path or inline
- Implement controls + 4 panels + replay algorithm
- Document the approximation caveat in the UI

Phase 1 ships first (unblocks playground data); Phase 2 ships in parallel (no dependency on playground); Phase 3 builds on Phase 1.

V1 graduation: playground renders iter-0 + iter-1 datasets correctly; "Disable BE" toggle changes equity curve visibly; MFE-vs-realized-R scatter shows the strategy diagnosis clearly. That's enough to teach the team where the leverage is. v2 (heatmap, full re-sim, multi-pair) follows after v1 ships and proves the model.
