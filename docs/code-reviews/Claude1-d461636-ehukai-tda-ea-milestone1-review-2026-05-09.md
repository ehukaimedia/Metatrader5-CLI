# Claude1 Independent Review — Ehukai/Photon SMC EA Milestone 1

Date: 2026-05-09
Reviewer: Claude1 (independent, on bus)
Author: Codex1
Baseline: HEAD `d461636` + uncommitted milestone tree
Verdict: **[REVIEW-OK with 1 MEDIUM + 2 LOW findings]** — environmental smoke blocker is not an EA bug

## Artifacts Under Review

- Spec: `docs/specs/2026-05-09-ehukai-tda-ea-backtesting.md` (176 lines)
- Plan: `docs/plans/2026-05-09-ehukai-tda-ea-backtesting-plan.md` (111 lines)
- EA: `metatrader5_cli/mt5/mql5/Experts/EhukaiTDAEA.mq5` (1485 lines, +/- after patches)
- Tester wrapper: `metatrader5_cli/mt5/core/tester.py` (392 lines)
- CLI delta: `metatrader5_cli/mt5/mt5_cli.py` (no changes vs HEAD; tester command lives via tester.py)
- Test delta: `metatrader5_cli/mt5/tests/test_core.py` (+~120 lines: TestTesterHelpers + VP confluence guide tests)
- Playground delta: `docs/playgrounds/mt5-codebase.html` (uncommitted)

## Evidence Reviewed

- MetaEditor compile: 0 errors / 0 warnings (post-patch)
- Full pytest: 368 passed, 1 skipped (post-patch); focused tester tests: 226 passed
- Smoke command: `python -m metatrader5_cli.mt5 --json tester run --symbol USDJPY --timeframe M5 --from 2026-04-01 --to 2026-04-30 --data-dir <D0E...> --timeout-seconds 300 --entry-mode limit`
- Smoke result: `TESTER_NO_ARTIFACTS`, elapsed 0.63s — environmental, not EA

## Contract Surfaces Verified (PASS)

| # | Surface | Where | Status |
|---|---------|-------|--------|
| 1 | Standalone — no overlay/iCustom dependency | only `<Trade/Trade.mqh>`; `CopyRates`/`SymbolInfo*`/`iATR` | ✓ |
| 2 | EHKEA_ prefix reserved (no chart objects drawn, none touch ETDA_) | grep negative for `ETDA_` and `ObjectCreate`/`ObjectsDeleteAll` | ✓ |
| 3 | PRIMARY post-sweep gate — sweep + LTF event required for READY | EvaluateSetup blockers @ line 332-334; sweep_ok required | ✓ |
| 4 | FVG-only entries are SKIP not lower-quality | `BuildRiskPlan` refuses without sweep @ line 917 | ✓ |
| 5 | SL anchor = swept extreme (not generic POI/strong-low) | line 934/943 — `swept_level - anchor_buffer` | ✓ |
| 6 | ATR/spread/pair-class floors layered (widening only, not tightening) | lines 935-948 use `MathMin`/`MathMax` correctly toward wider stops | ✓ (with one exception, see MEDIUM-2) |
| 7 | Hierarchical D1=H4=M15 alignment (post-patch) | `ResolveDirection` lines 391-400 — strict equality | ✓ |
| 8 | LTF entry-confirmation requires real BOS/CHOCH/iBOS event (post-patch) | `EntryConfirmed` lines 402-411 — no stage fallback | ✓ |
| 9 | Wick-through + close-back sweep semantics | `PoolSwept` lines 751-778 — correct close-vs-mid check | ✓ |
| 10 | Deeper-pool gate within ATR-distance | `LiquidityScanTF` lines 715-719 / 738-742 | ✓ |
| 11 | Full BE + Chandelier ownership; no AdaptiveTrailEA peer | `ManageOpenPosition` 1077-1121, `ComputeChandelier` 1123-1156 | ✓ |
| 12 | sha256-derived magic in [100000,180000); 11-pair table verified | `ResolveMagic` lines 1351-1368; test `test_pair_magic_matches_strategy_id_contract` confirms USDJPY=176879, USDCAD=128461, range check | ✓ |
| 13 | Single position per (symbol,magic) — FIFO/no-hedging | `HasActiveStrategy` 1050-1072 + `InpOneActiveTrade` gate | ✓ |
| 14 | FOK on market entries; ORDER_FILLING_RETURN on limits | line 1033 / 1040 — broker-correct | ✓ |
| 15 | 21:00–22:59 GMT rollover guard | `IsFxRolloverWindow` 1370-1375 | ✓ |
| 16 | News guard fail-closed when enabled without calendar source | `NewsWindowOk` 1377-1384 | ✓ |
| 17 | Journal: setups + entries + exits + failures with realized R | `InitJournals`/`Journal*` 1202-1323; realized_r via tick_value/tick_size | ✓ |
| 18 | Tester wrapper truthful — `TESTER_NO_ARTIFACTS` not silent success | `run_backtest` lines 329-334 | ✓ |
| 19 | Tester sniper_poc parity contract honored — Python source-of-truth not bypassed | spec §"Source Of Truth" + tester `pair_magic` matches `strategy_magic` | ✓ |
| 20 | Photon framework refresh from 5th transcript ("How I Trade Everyday") | reinforces existing rules; no new mechanical rule introduces drift | ✓ |

## Findings

### MEDIUM-2 — `skip-not-tighten` not enforced when ATR/pair floors push beyond structural anchor
**Where:** `BuildRiskPlan` lines 937-938 (long) / 946-947 (short)
**Issue:** When `swept_level - anchor_buffer` (structural SL) is tighter than `entry - atr*1.5` (ATR floor) or `entry - pair_floor` (pair-class floor), the code unconditionally widens via `MathMin`/`MathMax`. Spec §Risk Model line 97 explicitly says: *"ATR or pair-class floor would require moving the SL beyond the swept-structure invalidation: skip."*
**Impact:** Trades with structural SL too tight result in widened SL (and proportionally smaller lots via risk-money sizing), not skipped. Capital risk per trade is preserved, but the trade thesis weakens — original "post-sweep, stop behind structure" premise drifts. RR is preserved by scaling TP, so this is conservative widening rather than catastrophic, but spec/code diverge.
**Fix:** After computing widened SL, compare to structural anchor. If `|widened_sl - entry| > X * |swept_level - entry|` (X configurable, default ~1.5), skip the trade rather than placing it at a wider stop. Alternative: amend spec to say "widen, then check RR floor" if the team prefers the current behavior — but pick one and commit.

### LOW-1 — `InpEntryBufferPoints` quote-side check uses `point` not `pip`
**Where:** lines 296-297
**Issue:** `tick.bid - InpEntryBufferPoints * point` uses raw point, so `InpEntryBufferPoints=5` on a 5-digit symbol means 0.5 pip buffer (probably intended; on 3-digit JPY pairs, 5 points = 0.5 pip too). Logic is consistent across pair classes but the input description doesn't make the unit explicit.
**Fix:** Either rename to `InpEntryBufferSubpoints` or document in the input comment that this is in raw points (not pips). Cosmetic.

### LOW-2 — Test file mixes EA helpers from AdaptiveTrailEA and EhukaiTDAEA
**Where:** `tests/test_core.py` `TestEAHelpers` block (legacy AdaptiveTrailEA `Manual_Magic_0_Symbols=...` test) sits next to new `TestTesterHelpers`.
**Issue:** Cosmetic-only — tests still validate independent surfaces and pass. With AdaptiveTrailEA now retired (operator confirmed 2026-05-09), `TestEAHelpers` could be moved to a `legacy_` block or removed once tests targeting EhukaiTDAEA configuration are added.
**Fix:** Defer to a future cleanup pass; not blocking.

## Environmental Blocker (NOT an EA bug)

**Smoke run yields `TESTER_NO_ARTIFACTS`, terminal exits in 0.63s.**

Hypothesis (Codex1's, confirmed plausible): MT5 same-installation single-instance behavior. The operator's live terminal at `C:\Program Files\MetaTrader 5\` is already running. `terminal64.exe /config:<ini>` either focuses the existing window or exits without launching tester, because Windows MT5 enforces one process per installation directory.

Codex1 correctly refused to close operator's live terminal without explicit approval — that's the right call.

**Recommended workaround (operator decision required):**

1. **Portable secondary installation (preferred — zero impact on live terminal).** Install a second MT5 to `C:\Tools\MT5-Tester\` (most brokers' installer accepts a custom path; or copy the live install dir manually and run `terminal64.exe /portable` once). Point the tester wrapper at that installation via `--data-dir C:\Tools\MT5-Tester` (or by setting up `terminal_candidates()` to prefer it). Live terminal stays connected to the broker; tester runs in the parallel install.
2. **Stop live terminal during smoke (not recommended for routine use).** Operator manually closes live terminal → run smoke → reopen live terminal. High-friction; disconnects from broker; only acceptable for one-off smoke if portable install is unavailable.
3. **Alternative tester path (out of scope for milestone 1):** Use `MetaEditor64.exe /strategy:` automation if available, or the on-tester custom-data folder via `/portable` flag on the live terminal. Both add complexity not warranted here.

The milestone acceptance criteria explicitly allow "Smoke artifacts are collected OR the blocker is documented with the command that failed." Blocker is documented; criteria are met.

## Photon Framework Refresh Integration

Reviewed `master-liquidity-concepts-mechanical-strategy_c9b095b6/archive.json` (already in baseline) and `how-i-trade-everyday-for-maximum-profit_17d617af/archive.json` (24 chapters, new for this review).

Key NEW points from "How I Trade Everyday" — none introduce drift, all reinforce existing implementation:

- **Workflow step 1: identify swing range first** (chapters 1, 5) — EA's `ReadStructure` already does this via pivot detection.
- **Old mitigated supplies in bullish flow = reaction points only** (chapter 3) — EA filters FVGs by direction AND by filled/partial state at `FindFVGOnTF` lines 593-625. ✓
- **M15 idea + LTF confirmation discipline** (chapter 14) — EA evaluates per closed M5 bar with M15 bias gate. ✓
- **Liquidity-requirements gate non-negotiable** (chapter 16) — EA's `sweep_ok` is a hard READY blocker. ✓
- **Fixed-R targeting (chapter 19, "5R works for me")** — EA's `InpDefaultRR=3.0` is configurable; operator may want to test 5.0 in Phase 4 iteration.
- **News awareness during NY open / high-impact** (chapter 20) — `InpUseNewsWindowGuard` structural stub already in place; calendar source TBD.
- **Pre-session preparation discipline** (chapter 10) — EA recomputes per closed bar, naturally pre-session.

## Recommendations Summary

1. **Resolve MEDIUM-2 before Phase 3 (11-pair backtest)** — pick whether SL widening or skip is the policy and align spec/code. Document in spec.
2. **Operator decision on environmental blocker** — recommend portable secondary MT5 installation so smoke runs without touching live terminal.
3. **Phase 2 commit can proceed** with current code: acceptance criteria met, contract surfaces clean, test suite green.
4. **Defer LOW-1 / LOW-2** to a later cleanup pass.
5. **Phase 4 iteration parameter to surface in tuning notes:** `InpDefaultRR` 3.0 → 5.0 comparison given Photon transcript-19 preference.

## Closing

The implementation faithfully captures the contract anchored during the design-check exchange. The two refinement crossings (post-sweep primary gate, swept-extreme SL anchor, hierarchical alignment, real-event entry confirmation) all landed in the EA. Codex1's self-patch on the direction resolution before the verdict is exactly the verification-before-completion discipline the workflow asks for.

Verdict: **[REVIEW-OK]** with 1 MEDIUM (skip-not-tighten policy reconciliation) and 2 LOW findings to address before Phase 3, plus the environmental blocker which needs an operator decision on portable-installation strategy.
