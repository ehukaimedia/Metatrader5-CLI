# Track A + Track B Implementation Spec for Codex1

Date: 2026-05-09
Author: Claude1
Implementer: Codex1
Coordinator: Picard
Purpose: Precise field/variable mappings so Codex1 doesn't rebuild after a wrong guess

## Track A — Skip-Friday + Max-Initial-Risk Filters

### A1. `InpSkipFriday` — new bool input

```mql5
input bool InpSkipFriday = false;   // Skip entries on Friday (UTC)
```

Add to EvaluateSetup, alongside existing `IsFxRolloverWindow()` check:
```mql5
bool fx_day_ok = !InpSkipFriday || !IsFridayUTC();
```

Helper:
```mql5
bool IsFridayUTC()
{
    MqlDateTime dt;
    TimeToStruct(TimeGMT(), dt);
    return dt.day_of_week == 5;   // 0=Sun, 1=Mon, ..., 5=Fri
}
```

Wire `fx_day_ok` into the `blockers` chain (line 332 of EA) and add a "friday" reason to `FirstFailure(...)`. Treat as a NO_TRADE blocker (not WATCH) — operator policy decision; we don't need to defer to a watch state if this filter fires.

### A2. `InpMaxInitialRiskPips` — new int input, value in PIPS

```mql5
input int InpMaxInitialRiskPips = 50;   // Skip when entry-to-SL distance exceeds this many pips. 0 = disabled.
```

**Critical unit clarification:** The CSV `initial_risk` column is in **PRICE UNITS** (not pips, not R). For USDJPY (3-digit), 1 pip = 0.01, so `initial_risk = 0.50` is **50 pips**. For 5-digit majors (EURUSD), 1 pip = 0.0001, so 50 pips = 0.0050. The EA's `PipSize()` helper at line 1394 already abstracts this.

Add the gate INSIDE `BuildRiskPlan`, AFTER all the SL widening (lines 935-948) but BEFORE the final `risk_ok` boolean:

```mql5
const double risk_pips = setup.risk / PipSize();
const bool initial_risk_ok = InpMaxInitialRiskPips <= 0 || risk_pips <= InpMaxInitialRiskPips;
if (!initial_risk_ok)
    return false;
```

Default 50 matches the iter-0 analysis threshold that removed 2 noise (positions 8 with 74 pips, 22 with 70 pips) and zero strong (max strong was position 18 at ~45 pips).

Backward compat: 0 disables the cap. Add to journal `gates` string for visibility:
```
... ;risk_pips=15.7/50;...
```

### Iter-2 .set values

```
InpSkipFriday=true
InpMaxInitialRiskPips=50
InpUseBreakeven=true
InpBETriggerR=1.20      # iter-2's BE-isolation test
InpChandelierATRMultiplier=3.0   # back to baseline so BE is the only changed knob from iter-0
```

This single iter-2 run tests filter-A + BE-isolation simultaneously. Cheap parallel hypothesis test.

## Track B — Five Richer Journal Columns

Add to `EhukaiTDAEA_<symbol>_entries.csv` schema (new columns at end; preserves backward compat for older readers that just skip extras).

New columns:
```
htf_momentum_d1, time_since_sweep_pivot_bars, time_since_sweep_event_bars, room_to_swing_high_pips, spread_to_atr_ratio, m5_m1_event_lag_bars
```

(Six columns; I split sweep age into TWO because both are diagnostically valuable — the pivot age vs the wick-puncture age tell different stories.)

### B1. `htf_momentum_d1` — D1 directional efficiency ratio

**Photon concept:** "is D1 in a strong directional trend or a choppy range?"

**Formula:**
```
htf_momentum_d1 = (close[1] - close[N]) / sum(|high[i] - low[i]|, i=1..N)
```
N=10 D1 bars. Range: -1.0 (strong down) to +1.0 (strong up). Near 0 = choppy.

**MQL5 implementation** (helper, called from PlaceSetup right before journaling):
```mql5
double D1MomentumRatio(const int bars = 10)
{
    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    const int copied = CopyRates(_Symbol, PERIOD_D1, 1, bars, rates);
    if (copied < bars) return 0.0;
    const double net = rates[0].close - rates[copied - 1].close;
    double range_sum = 0.0;
    for (int i = 0; i < copied; i++) range_sum += MathAbs(rates[i].high - rates[i].low);
    return range_sum > 0.0 ? net / range_sum : 0.0;
}
```

Format in CSV: `%.4f`.

### B2. `time_since_sweep_pivot_bars` — bars from the swept extreme to entry

**Photon concept:** "how recently was the liquidity pool that just got run formed?"

**Existing code touchpoint:** `LiquidityScanTF` at lines 685-749. The pivot index `i` IS the bar position of the swept extreme in the rates array (with `ArraySetAsSeries(rates, true)` so index 0 = newest).

**Implementation:** Add `swept_pivot_age_bars` field to `LiquidityRead` struct. In `LiquidityScanTF`, when `swept` is true and we update `read.swept_level`, also record `read.swept_pivot_age_bars = i`. Default initialization: -1 (no sweep).

```mql5
struct LiquidityRead
{
    bool sweep;
    bool front;
    bool behind;
    bool trap;
    bool deeper_pool_too_close;
    double swept_level;
    double deeper_pool_level;
    int swept_pivot_age_bars;        // NEW: i-position of swept pivot in M5 rates
    int swept_event_age_bars;        // NEW: bars since sweep wick-puncture
    string reason;
};
```

In ReadLiquidity / LiquidityScanTF: store `i` (the pivot index) on the chosen sweep, and store sweep_age (already computed via `PoolSwept`'s out-param) into the new event_age field.

Journal at PlaceSetup: write both ages. Format: integer.

### B3. `time_since_sweep_event_bars` — bars from sweep wick-puncture

(See B2 — same struct, separate value.) The existing `PoolSwept` function already returns this via the `age_bars` reference parameter. Just propagate it into the LiquidityRead struct and journal it.

Format: integer.

### B4. `room_to_swing_high_pips` — distance to next significant M15 swing extreme in trade direction

**Photon concept:** "trade with room to run."

**Implementation:** Helper that scans M15 pivots in trade direction:

```mql5
double RoomToSwingExtremePips(const int direction, const double entry_price)
{
    if (direction == 0) return 0.0;
    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    const int copied = CopyRates(_Symbol, PERIOD_M15, 0, InpLookbackBars, rates);
    if (copied < InpSwingPivotBars * 4) return 0.0;
    
    const int pivot = InpSwingPivotBars;
    double nearest = 0.0;
    for (int i = pivot; i < copied - pivot; i++)
    {
        if (direction > 0 && PivotHighAt(rates, copied, i, pivot))
        {
            const double level = rates[i].high;
            if (level > entry_price && (nearest == 0.0 || level < nearest))
                nearest = level;
        }
        else if (direction < 0 && PivotLowAt(rates, copied, i, pivot))
        {
            const double level = rates[i].low;
            if (level < entry_price && (nearest == 0.0 || level > nearest))
                nearest = level;
        }
    }
    if (nearest == 0.0) return 0.0;
    return MathAbs(nearest - entry_price) / PipSize();
}
```

Reuses existing `PivotHighAt`/`PivotLowAt` (lines 518-542) and `InpSwingPivotBars`/`InpLookbackBars`. Returns 0 if no pivot found in direction (edge case; flag separately as `room_to_swing_high_pips=0` meaning "unbounded / no resistance level above").

Journal at PlaceSetup. Format: `%.1f`.

### B5. `spread_to_atr_ratio` — relative spread cost at entry

**Trivial:** at PlaceSetup time, compute:
```mql5
const double spread_price = tick.ask - tick.bid;
const double atr = ATRPrice(InpEntryTF1, 14);   // already exists at line 999
const double spread_to_atr = atr > 0.0 ? spread_price / atr : 0.0;
```

Journal: format `%.4f`. Range typically 0.05-0.40 (5-40% of ATR is spread).

### B6. `m5_m1_event_lag_bars` — bars between sweep event and LTF entry confirmation

**Photon concept:** "how quickly did the LTF confirm the sweep? — fast = institutional follow-through."

**Implementation:** Need both the sweep event time and the M1 (or M5) BOS/CHOCH/iBOS time.

- Sweep event time: when the wick-puncture closed-back bar occurred. The rates index is `(pivot_index - 1 - age_bars)` from PoolSwept's age_bars. Or: track `sweep_event_time` in LiquidityRead struct directly using `rates[pivot_index - 1 - age_bars].time`.
- LTF event time: m1.signal_time or m5.signal_time (whichever fired the entry confirmation in EntryConfirmed).

In EvaluateSetup, after EntryConfirmed determines whether m5 or m1 confirmed:
```mql5
datetime confirm_time = 0;
if (m1.event_dir == direction && (m1.event_type == "BOS" || m1.event_type == "CHOCH" || m1.event_type == "iBOS"))
    confirm_time = m1.signal_time;
else if (m5.event_dir == direction && (m5.event_type == "BOS" || m5.event_type == "CHOCH" || m5.event_type == "iBOS"))
    confirm_time = m5.signal_time;

const int lag_bars = (confirm_time > 0 && liq.sweep_event_time > 0)
    ? (int)((confirm_time - liq.sweep_event_time) / 60)   // M1 bars
    : -1;
```

Add `sweep_event_time` field to LiquidityRead struct (set in LiquidityScanTF when sweep detected).

Journal: integer. Negative = unknown (no sweep or no confirmation), 0 = same bar, positive = lag.

## Sample Size Note

iter-1 (looser trail) + iter-2 (filter A + BE-only) + iter-3 (richer features active from iter-2 onward) gives ~60-80 trades pooled by iter-3 if trade count holds. Feature analysis on 60+ trades will surface stronger separators than 22 did. Plan to re-run the strong-vs-noise cross-tab once iter-3 lands.

## Schema Migration

Older runs (iter-0 through iter-2) have entries.csv WITHOUT the new columns. Codex1's `playground_data.py` and `summarize_run` should:
- Tolerate missing columns (default to None / -1 / NaN)
- Mark trade_summary.json `feature_set_version`: 1 = pre-Track-B, 2 = with-Track-B columns

This preserves backward compat for the playground reading mixed-version data.

## Tests Codex1 Should Add

- Unit test: `D1MomentumRatio` returns 0 when fewer than N D1 bars copied
- Unit test: `RoomToSwingExtremePips` returns 0 when no pivot above (long) / below (short)
- Unit test: `IsFridayUTC` returns true on a Friday GMT, false otherwise
- Unit test: `InpMaxInitialRiskPips=0` disables the cap (backward compat)
- Integration test: parse iter-0 entries.csv (pre-Track-B) without crashing in playground_data
- Integration test: parse a Track-B entries.csv with the new columns; verify all six new fields surface in trade_summary.json

## Iter-2 .set Bundle Summary

Codex1 ships ONE .set file for iter-2 that contains:
```
InpSkipFriday=true                 # Track A1
InpMaxInitialRiskPips=50           # Track A2
InpBETriggerR=1.20                 # iter-2 BE-isolation test
InpChandelierATRMultiplier=3.0     # back to iter-0 baseline so BE is the only changed knob
InpUseBreakeven=true                # explicit (default true; included for clarity)
```

That's the iter-2 spec. Operator runs once Codex1 ships the EA patch.

## Done Criteria

Codex1's patch is "done" when:
- [x] EhukaiTDAEA.mq5 compiles 0 errors / 0 warnings with both new inputs and six new journal columns
- [x] Full pytest passes
- [x] Iter-0 backward-compat playground_data.py test passes (reads pre-Track-B entries.csv without errors)
- [x] Track-B journal forward-compat test passes (writes + reads new columns)
- [x] iter-2 .set file written to MetaQuotes/.../Tester/USDJPY_M5_iter2.set (or equivalent path operator can load via Strategy Tester Inputs tab)

Once shipped, Picard pings me for a brief design-OK before operator runs iter-2.
