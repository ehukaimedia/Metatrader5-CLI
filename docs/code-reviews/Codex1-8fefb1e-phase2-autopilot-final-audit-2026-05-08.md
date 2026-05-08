# Codex1 Audit — Phase 2 Autopilot Consensus Final Review — 2026-05-08

Reviewed HEAD `8fefb1e` for the phase-2 autonomous consensus lane.

## Findings

### CRITICAL — `autopilot_placement` is invisible to outcome resolution, stats, and the trade manager

Files:
- `adaptive-forex-mt5/journal.py:213`
- `adaptive-forex-mt5/journal.py:252`
- `adaptive-forex-mt5/agent.py:193`
- `adaptive-forex-mt5/trade_manager.py:131`

`journal.log_autopilot_placement()` writes `kind="autopilot_placement"`, but the rest of the runtime still treats only `kind="placement"` as a real managed/open trade:

- `journal.folded_trades()` only folds `kind == "placement"`, so dashboard totals/open/closed stats ignore autopilot trades.
- `agent.open_journal_records()` uses `folded_trades()`, so `resolve_outcomes()` never resolves autopilot trade closes.
- `trade_manager._open_journal_placements()` only scans `kind == "placement"`, so Python-side BE/trailing bootstrap cannot match an autopilot-filled position to its journal record. That position becomes an unmanaged POC-magic position, exactly the failure mode phase 1 was designed to prevent.
- `log_autopilot_placement()` also lacks `entry`, `sl`, `tp`, `direction`, `volume`, `rr`, and reasoning/alert reference fields needed for manager bootstrap and post-hoc strategy analysis.

Impact: autopilot can place a trade that is not trailed, not resolved, and not counted in evidence. This can lose money and corrupt the strategy validation dataset.

Required fix: either make `autopilot_placement` a first-class placement everywhere or write a normal `placement` record with an `autopilot=true` marker. At minimum, update `folded_trades()`, `open_journal_records()`, `trade_manager._open_journal_placements()`, stats, and outcome resolution to include autopilot placements, and include the full setup fields on the autopilot placement record. Add regression tests that an autopilot placement is managed, resolved, and counted.

Confidence: high.

### HIGH — Bus abort kill switch is implemented but not wired into the running agent loop

Files:
- `adaptive-forex-mt5/autopilot.py:67`
- `adaptive-forex-mt5/agent.py:580`

`autopilot.poll_bus_for_abort()` exists and tests prove the helper flips the kill switch when an operator sends `AUTOPILOT ABORT`, but `agent.scan_once()` / `run()` never calls it. The agent will therefore not observe the operator's one-tap bus abort unless some other process calls the helper.

Impact: the advertised emergency control path is inert in the live runtime. If autopilot is enabled, an operator bus abort may not stop subsequent autonomous placements.

Required fix: call `autopilot.poll_bus_for_abort(_state_db_path())` at the top of each scan loop before `evaluate_pending_consensus()` or any placement-capable logic, and add an integration test proving a simulated operator abort prevents a later `attempt_autopilot_place()` call in the same scan cycle.

Confidence: high.

## Verified Good

- The two pre-T9 blockers are closed: placement uses `mt5 order limit` with exact alert setup levels, and consensus joins by `alert_id` only.
- `test_all_pass_places_at_alert_setup_levels_exactly` pins exact alert levels even when current `sniper_poc` returns different levels.
- `test_executor_never_reads_reviewer_adjusted_fields` pins that reviewer adjusted levels are ignored.
- Live-intent gate blocks before any `order limit` call.
- News null-source fails closed.
- Daily caps are scoped to autopilot placements.

## Verification

- `python -m pytest adaptive-forex-mt5/tests/test_autopilot_gates.py adaptive-forex-mt5/tests/test_autopilot_pipeline.py adaptive-forex-mt5/tests/test_consensus_join.py adaptive-forex-mt5/tests/test_bus_listener.py adaptive-forex-mt5/tests/test_kill_switch.py adaptive-forex-mt5/tests/test_news_blackout.py -q` → `33 passed`
- `python -m pytest -q` → `331 passed, 1 skipped`

## Verdict

NO-GO for phase-2 live/autopilot readiness until the two runtime integration blockers are fixed. The consensus and 12-gate executor are materially improved, but the placed-trade lifecycle is not integrated end-to-end yet: an autopilot trade would bypass the manager/outcome/statistics evidence path, and the bus abort surface is not active in the running agent loop.
