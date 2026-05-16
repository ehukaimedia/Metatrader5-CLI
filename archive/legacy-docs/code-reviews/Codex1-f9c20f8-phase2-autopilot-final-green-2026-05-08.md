# Codex1 Audit — f9c20f8 Phase 2 Autopilot Final Green Review — 2026-05-08

Reviewed HEAD `f9c20f8` after the flat `mt5 order limit` response-shape fix.

## Findings

No findings.

## Verified

- `journal.log_autopilot_placement()` now supports both shapes:
  - real `mt5 order limit` flat response: `data.ticket`, `data.magic`, `data.volume`
  - legacy nested response: `data.placement`
- Autopilot placements are written as `kind="placement"` with `autopilot=true`, full setup fields, `strategy_id`, `consensus_alert_id`, and reviewer confidences.
- The new end-to-end regression `test_attempt_autopilot_place_journals_with_flat_response_shape` exercises `attempt_autopilot_place()` using the real flat response shape and verifies:
  - `ticket=5555`
  - `magic=128461`
  - `volume=0.001`
  - `direction`, `entry`, `sl`, `tp`
  - visibility in `journal.folded_trades()`
  - visibility in `trade_manager._open_journal_placements()`
- The previous bus-abort blocker remains closed: `agent.scan_once()` polls `autopilot.poll_bus_for_abort()` before outcome resolution, order scanning, verdict polling, or consensus/autopilot execution.
- The pre-T9 executor invariants remain covered:
  - exact alert-level `mt5 order limit`
  - no reviewer `adjusted_*` levels used
  - alert-id-only consensus join
  - live gate before order-limit broker call
  - news null source fails closed
  - autopilot-only daily caps

## Verification Commands

- `python -m pytest adaptive-forex-mt5/tests/test_phase2_audit_fixes.py adaptive-forex-mt5/tests/test_journal_kinds_phase2.py adaptive-forex-mt5/tests/test_autopilot_gates.py adaptive-forex-mt5/tests/test_autopilot_pipeline.py -q` → `23 passed`
- `python -m pytest -q` → `337 passed, 1 skipped`

## Residual Risk

- This review did not run a real broker autopilot placement. The code path is still protected by `autopilot.enabled=false` and `mt5_cli.live=false` in the checked config. Before enabling live autopilot, run the existing supervised/demo pre-flight with `autopilot.enabled=true`, `news_source` configured, and micro-lot sizing.

## Verdict

GO for phase-2 shadow-mode / supervised-demo readiness. The prior lifecycle and bus-abort blockers are closed, and the autopilot placement path now produces records that the existing manager, outcome resolver, dashboard, and stats pipeline can consume.
