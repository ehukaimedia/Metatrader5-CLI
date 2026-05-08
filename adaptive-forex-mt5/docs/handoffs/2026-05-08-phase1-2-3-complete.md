# Handoff — adaptive-forex-mt5 phases 1-3 complete (2026-05-08)

## Quick orient (60 seconds)

- All three structural phases are implemented and Codex1-GREEN. Phase 4 is
  speculative future work, not scheduled.
- Local HEAD is several commits ahead of `origin/master`; **NOT pushed yet.**
  The push is gated on Codex1's re-sweep (post-PII-scrub) being GREEN.
- Working tree is clean. Tests: 358 passed / 1 skipped repo-wide.
- Memory: `~/.claude/projects/.../memory/project_adaptive_forex_mt5.md`
  also still loads. The original alerts-only POC handoff there is now
  **historic** — read this handoff first.

## What got built this session

### Phase 1 — foundation (commits up to roughly `4c2eb04`)

- Python `trade_manager.py` replaces the AdaptiveTrailEA for poc-magic
  positions: bootstrap → infer-stage → BE move → Chandelier trail.
- Confirm-before-promote modify state machine. `last_sl_set` is only set
  after MT5 confirms `position.sl == requested_sl`; pending modifies
  retry on cooldown with the same idempotency key.
- LLM review pipeline (advisory only): every READY emits `setup_fingerprint`,
  writes payload to `.ehukaiconnect/shared/files/alerts/`, dispatches a
  `trade_review-*` task, polls closures, journals `kind=llm_verdict`,
  pushes enriched ntfy.
- New: `state_db.py` (SQLite WAL, three tables + active_pos_uniq partial
  index), `fingerprint.py`, `dispatch.py`, `news.py` deferred to phase 2.

### Phase 2 — autopilot consensus (commits up to roughly `f9c20f8`)

- Strict 2-of-2 consensus from `ClaudeReviewer` + `CodexReviewer`. Both
  must vote `take` on the same direction with both
  `accepted_levels=true` and `min(confidence) >= threshold`. Different
  model families is an invariant.
- 12-gate fail-fast executor (`autopilot.attempt_autopilot_place`):
  `enabled`, `kill_switch`, `consensus`, `pair_allowlist`, `alert_age`,
  `fingerprint or bounded drift`, `live`, `spread_cap`, `news_blackout`
  (fails closed when `news_source` is null), `lot_size`, `daily_caps`,
  `active_strategy`. On all-pass: `mt5 order limit` with the ORIGINAL
  `alert.setup` levels — never re-evaluated, never reviewer-adjusted.
- `kind=placement` with `autopilot=true` so the existing trade lifecycle
  (folded_trades / resolve_outcomes / trade_manager bootstrap) handles
  autopilot trades natively.
- `AUTOPILOT ABORT` bus message → kill-switch (handled by
  `autopilot.poll_bus_for_abort` which `agent.scan_once` runs FIRST each
  cycle).
- Master flag `autopilot.enabled` defaults `false`. Shadow mode runs
  unconditionally — every alert journals `kind=consensus_verdict` so the
  operator can calibrate before flipping the master flag.

### Phase 3 — manual-trade adoption (commits up to `1edfce1`)

- `adopt.py` reads `managed_positions.json` (gitignored) and validates by
  ticket+symbol+account. Missing required fields, malformed JSON, or
  expired entries fail closed.
- `trade_manager.loop_once` accepts a position if EITHER its magic is in
  the poc-set OR its ticket is in the allowlist AND symbol+account match
  AND there's a real protective SL.
- Adopted positions get a synthesized `kind=placement` (with
  `adopted=true`); idempotent across loops.
- `mode=trail_only` skips the BE step (post-bootstrap promotes stage to
  `be_armed` with current SL); `mode=be_and_trail` keeps phase-1 behavior.

### Architecture playground (commits `9f60733` → `0c52b2f`)

- Single-file HTML at `adaptive-forex-mt5/docs/playgrounds/architecture.html`.
- 6 phase presets, layer + connection-type toggles, click-to-comment per
  node, copy-able prompt aggregating notes for handing back to Claude.
- No external dependencies. XSS-safe (textContent everywhere).

### Portability + main README (recent commits)

- Confirmed `adaptive-forex-mt5/` has zero Python imports of
  `metatrader5_cli/` — every interaction is `subprocess.run(["mt5", ...])`
  or `subprocess.run(["ehukaiconnect", ...])`.
- Main repo `README.md` now has a "Bundled portable app" section linking
  to the per-app README + the architecture playground.
- `.ehukaiconnect/` is repo-gitignored (workspace state, not source).
  Reviewer skill templates live in `docs/skills/` and copy out into the
  workspace at install time.

## Pre-push status — DO THIS FIRST NEXT SESSION

Codex1's pre-push sweep at HEAD `cea4e6b` flagged two NO-GO items, both
addressed in this session's final commits:

1. Local Windows paths (`C:\Users\arsen\...`) and a real-looking MT5
   terminal id appeared in three audit/plan docs. **Replaced with
   `<workspace>` and `%APPDATA%\MetaQuotes\Terminal\<TERMINAL_ID>\`
   placeholders.**
2. Real-looking MT5 login `105112007` appeared in `README.md` and
   `metatrader5_cli/mt5/tests/test_core.py` (15 occurrences). **Replaced
   with the placeholder `12345678` in all tracked files.**

**Next session resume checklist:**

```bash
# 1. Verify the scrub stuck
grep -rn "105112007\|C:.Users.arsen" --include="*.md" --include="*.py" --include="*.json" .

# (Anything in .claude/worktrees/* is stale Claude Code state, gitignored, fine.)

# 2. Run full test suite
python -m pytest -q
# Expect: 358 passed, 1 skipped

# 3. Ask Codex1 for a re-sweep on bus
ehukaiconnect send-to Codex1 --from Claude1 "[RE-SWEEP] PII scrubbed at HEAD <new-head>. Please verify and GREEN for push to main."

# 4. On Codex1 GREEN: push to origin/master.
git push origin master
```

## Deferred / future work

- **Phase 4** (LLM-driven gate-param tuning). Speculative — only worth
  building if shadow `kind=consensus_verdict` data over weeks shows the
  deterministic gates miss real opportunities. Not scheduled.
- **News source for autopilot.** `news.is_blackout_active` fails closed
  when `cfg.autopilot.news_source` is null. Until the operator wires a
  real source (e.g. ForexFactory calendar fetcher), autopilot CANNOT
  place trades even with the master flag on. This is by design.
- **Supervised live pre-flight.** Per Codex1's residual note, a real
  broker autopilot placement has not been exercised end-to-end on demo.
  Before flipping `autopilot.enabled=true` for the first time:
  1. Wire a news source.
  2. Set `pair_allowlist` to one pair (probably USDJPY).
  3. Verify `mt5_cli.live=true` points at a DEMO account.
  4. Confirm `lot_size=0.001`.
  5. Open one consensus_verdict, watch the executor go through the 12
     gates with `--allow-live`-style supervision.
- **Reviewer model selection.** Reviewers are currently named
  `ClaudeReviewer` + `CodexReviewer`. The Claude model id (Opus 4.7 vs
  Sonnet) and the Codex model id are workspace-config decisions; not
  pinned in the spec.
- **`min_stop_points` for JPY crosses.** From the original alerts-only
  POC handoff: today's GBPJPY noise-eats-tight-SL failure was at 8 pips
  (80 points). Consider raising to 15 pips (150) for JPY crosses
  specifically. Not implemented — it's one config edit.

## Where the artifacts live

| Artifact | Path |
|---|---|
| Per-phase spec | `docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md` |
| Phase 1 plan | `docs/superpowers/plans/2026-05-08-trade-manager-and-llm-review.md` |
| Phase 2 plan | `docs/superpowers/plans/2026-05-08-autopilot-consensus.md` |
| Architecture playground | `adaptive-forex-mt5/docs/playgrounds/architecture.html` |
| Per-app README | `adaptive-forex-mt5/README.md` |
| Codex1 audit trail (8 docs) | `docs/code-reviews/Codex1-*.md` |
| Earlier alerts-only POC audit trail (6 docs) | `docs/code-reviews/codex-adaptive-forex-mt5-*.md` |
| Reviewer skill templates | `docs/skills/{Claude,Codex}Reviewer-SKILL.md` |
| Manual-trade allowlist example | `adaptive-forex-mt5/managed_positions.example.json` |
| Per-app config example | `adaptive-forex-mt5/config.example.json` |
| Trading.com broker constraints | `adaptive-forex-mt5/skills/trading.com/SKILL.md` |

## Process learnings (for next-session etiquette)

- Don't `git add -A`. Stage specific files. Lost 30 minutes earlier this
  session to an over-commit (312 unrelated files) that needed a
  soft-reset and re-stage.
- Codex1's truncated-bullets pattern: when a `[REVIEW]` message lands
  with a colon and no list, nudge once asking for the stdin re-send.
  System notice this session updated the messaging skill to forbid
  ACK-and-stop on review/blocker directives.
- The `feature-dev:code-reviewer` agent is good at architecture-accuracy
  and security checks; pair it with Codex1 for safety/integration. Both
  run independently and both find real issues.
- The `.ehukaiconnect/` directory is workspace state, NOT a code artifact.
  Skill templates that need to ship with the repo go in `docs/skills/`
  and get copied into `.ehukaiconnect/skills/` at install time.

## Operator's open positions at handoff

(Manual, magic=0 — bot does NOT manage these unless added to
`managed_positions.json`.)

Resume with `mt5 --json position list` to get the current state. The
original handoff memory's GBPJPY/USDJPY positions may have closed by now.
