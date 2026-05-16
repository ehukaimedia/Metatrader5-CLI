# Picard Coordinator Orientation — 2026-05-09

Welcome, Picard. You are the workspace coordinator as of operator directive at 13:35-ish today. This file gives you everything you need to take the handoff cold.

## Read Order

1. Your personal skill: `.ehukaiconnect/skills/Picard/SKILL.md`
2. Teamwork protocol (universal): `.ehukaiconnect/skills/teamwork/SKILL.md`
3. **Coordinator role template:** `.ehukaiconnect/skills/roles/coordinator/SKILL.md`
4. This file (operator just told you to read it)

## Team

| Agent | Role | What they own |
|-------|------|---------------|
| Picard (you) | Coordinator | Operator-facing summaries, task manager status rollup, route work between Codex1/Claude1, drive the iteration loop |
| Codex1 (PID 30620) | Task-agent / implementer | EA source, tester wrapper, CLI commands, .set parameter files, bug fixes, commits |
| Claude1 (PID 28140, me) | Independent reviewer | Contract drift watch, evidence interpretation (journal crunching, R-distribution analysis), tuning proposals from data, framework reference custodian |

Operator wanted to stop double-messaging — you are now the single contact point. Operator messages YOU; you delegate; you roll up status to operator. Both Codex1 and I report to you.

## Project Context

**Goal (operator's brief, 2026-05-09):** "Codex + Claude collaborate to create and backtest a full MQL5 Expert Advisor for the Ehukai / Photon SMC strategy across the current 11 FX pairs, using MetaTrader 5's built-in Strategy Tester."

**Current phase:** Phase 4 evidence-driven parameter iteration (we're past Phase 1-2 implementation + review, past first one-pair smoke).

## State Right Now

### Commits (master branch, all clean)
- `d461636` Harden VP confluence scoring coverage (pre-milestone baseline)
- `b05329e` Add Ehukai TDA strategy tester EA milestone (Phase 1+2 deliverable: spec/plan/EA/tester wrapper/tests + my REVIEW-OK review file + Codex1's review note)
- `87a856e` Add volume profile iteration backlog (Phase 4 lanes: 5 VP rules from how-to-master-volume-profile transcript)
- `77c39d7` Add manual tester artifact collection (`mt5 tester collect` standalone CLI)

### Active task
- `751047cb` (Codex1 owner) — "Resolve MT5 Strategy Tester smoke path." Was blocked on operator GUI smoke; smoke completed at 13:30 today. Task should be closed/transitioned now that evidence is in hand. **Your call on whether to mark it done or split into follow-up tasks.**

### Smoke run evidence (just completed — first real backtest)
- Pair: USDJPY M5, range 2026-01-01 → 2026-05-08, real-tick model
- 22 trades, -$59.05 net, 22.7% win rate, profit factor 0.23
- 21 LONG + 1 SHORT (correctly biased long during USDJPY's 156→160 uptrend)
- Wins capped at +0.37R, losses mostly -0.10 to -0.30R → Chandelier-trail-too-tight signature
- Setup gating verified: 198 setups → 44 READY → 22 filled, 0 order_send failures
- Journals at: `C:\Users\arsen\AppData\Roaming\MetaQuotes\Tester\D0E8209F77C8CF37AD8BF550E51FF075\Agent-127.0.0.1-3000\MQL5\Files\EhukaiTDAEA\`

### In-flight (Codex1 patching, not yet committed)
- `tester collect` adds Tester sandbox path search (was looking in wrong dir)
- EA OnTradeTransaction journaling: reset-on-init + deal-ticket dedupe (current bug: each trade written 2× during Strategy Tester history replay)

### Pending operator-facing recommendation (mine, awaiting your dispatch to Codex1)
First tuning iteration based on smoke evidence:
- `InpChandelierATRMultiplier` 3.0 → 4.0
- `InpBETriggerR` 0.80 → 1.20
- Re-run same Jan-Apr USDJPY M5 window. If expectancy improves, that's the right knob.
- This can be done via Strategy Tester Inputs tab (no recompile, runtime override) or via a `.set` file Codex1 writes.

### Phase 4 backlog (committed in 87a856e, queued for evidence-driven iteration)
1. VP high-volume zone detection around POC
2. VP zone-boundary entries (long upper boundary / short lower boundary)
3. POC + S/R confluence bonus
4. TP scaled to nearest VP barrier (vs current fixed RR=3)
5. SL behind heavy-volume barrier check

### Phase 3 (11-pair backtest) — gated on:
- Either a portable secondary MT5 install (sidesteps single-instance) for CLI automation
- Or a Python-native backtest CLI (proposed, awaiting operator greenlight) — replays `core/ehukai.py` setup planner over `copy_rates_range()` history, no MT5 single-instance issue
- Operator hasn't decided which yet

## Contract Anchors (what Claude1 holds you to)

These came from the design-check exchange and are LOCKED before code:

1. **Standalone EA** — no overlay/iCustom dependency, internal recompute via CopyRates/SymbolInfo/iATR only
2. **EHKEA_ object prefix** reserved for EA visuals (never ETDA_ which is overlay's namespace)
3. **PRIMARY post-sweep gate** — sweep + LTF BOS/CHOCH/iBOS required for READY; FVG-only is SKIP
4. **Hierarchical D1=H4=M15 alignment** (no majority-voting, strict equality)
5. **SL anchor = swept extreme** (not generic POI/strong-low) + ATR/spread/pair-class floors LAYERED outward (widen never tighten; skip if widened plan fails downstream gates)
6. **Per-pair magic** sha256-derived in [100000,180000); 11-pair table verified by `test_pair_magic_matches_strategy_id_contract`
7. **AdaptiveTrailEA = legacy** (operator confirmed, never reattached); new EA owns full BE+Chandelier alone
8. **Trading.com constraints**: FOK on market entries, FIFO/no-hedging single-position-per-symbol-magic, 21:00-22:59 GMT rollover guard, news guard fail-closed

Operator's directional preference (locked): "if directional bias is correct AND we get in after liquidity is swept, we should not get stopped out." This is what the post-sweep gate + swept-extreme SL anchor implements mechanically.

## Memory References

Three memory files in `C:\Users\arsen\.claude\projects\C--Users-arsen-OneDrive-Desktop-AI-Applications-Metatrader5-CLI\memory\`:

1. `project_mt5_cli_spec.md` — MT5 CLI spec v0.5 non-negotiables (core-layer risk, strategy-id isolation, library API contract)
2. `reference_photon_smc_framework.md` — Mechanical SMC rules from 6 Photon transcripts; review checklist for Ehukai indicators + EhukaiTDAEA
3. `project_adaptive_forex_mt5.md` — Live state of legacy adaptive-forex-mt5 POC (alerts-only; AdaptiveTrailEA marked retired 2026-05-09)

## Key Documents

- Spec: `docs/specs/2026-05-09-ehukai-tda-ea-backtesting.md`
- Plan: `docs/plans/2026-05-09-ehukai-tda-ea-backtesting-plan.md` (includes Phase 4 backlog)
- My review: `docs/code-reviews/Claude1-d461636-ehukai-tda-ea-milestone1-review-2026-05-09.md`
- Codex1 review note: `docs/code-reviews/Codex1-ehukai-tda-ea-milestone1-2026-05-09.md`

## Iteration Loop (the actual work cadence)

```
Operator runs Strategy Tester (manually, GUI)
  → CSV journals land in Tester sandbox
  → Claude1 crunches journals → tuning proposal
  → Picard dispatches change (.set or code) to Codex1
  → Codex1 ships
  → Picard rolls up to operator: "ready to re-run, here's what changed"
  → Operator re-runs
  → Repeat
```

## What I Recommend You Do First

1. Read your role template at `.ehukaiconnect/skills/roles/coordinator/SKILL.md`
2. Send a `[ROLE-ASSIGNED ACK]` to operator with your understanding of the split
3. Optionally: close out task `751047cb` (smoke evidence in hand) and open a fresh task for the Chandelier/BE-trigger tuning iteration
4. Dispatch Codex1's in-flight patch (Tester sandbox path search + dedupe) to commit
5. Once Codex1's patch lands, propose the first tuning iteration to operator: "Codex1 will write `.set` with Chandelier 4.0 + BE 1.20R; you re-run; Claude1 compares R-distribution against baseline."

## Bus Conventions (quick reference)

- Operator address: `0`
- Codex1 PID: `30620`
- Claude1 PID: `28140` (me)
- Picard PID: yours, in your runtime header
- Use `send-to <pid> --from Picard` for DMs
- Use `[TAGS]` per teamwork.md (CLAIM, ACK, DONE, BLOCKED, REVIEW, REVIEW-OK, REVIEW-ISSUE, DESIGN, DESIGN-CHECK, etc.)
- Long content (>500 chars) → save to file, post summary + path on bus

Welcome aboard. I'm staying as independent reviewer. Ping me when you need contract drift checks, evidence analysis from journals, or tuning recommendations — and I'll route my output to you for operator rollup.

— Claude1
