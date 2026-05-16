# Codex1 Audit — d50ed23 Phase 2 Blocker Fix Review — 2026-05-08

Reviewed HEAD `d50ed23` after Claude1's fixes for the phase-2 final-audit blockers.

## Findings

### CRITICAL — Real `order limit` responses are flat, but `log_autopilot_placement()` only reads nested `data.placement`

Files:
- `adaptive-forex-mt5/journal.py:227`
- `adaptive-forex-mt5/autopilot.py:343`
- `metatrader5_cli/mt5/core/order.py:203`
- `adaptive-forex-mt5/tests/test_phase2_audit_fixes.py:35`
- `adaptive-forex-mt5/tests/test_autopilot_gates.py:292`

The lifecycle fix makes `log_autopilot_placement()` write `kind="placement"`, which is the right architectural direction. But it extracts broker fields from:

```python
data = placement.get("data") or {}
placement_data = data.get("placement") or {}
```

That nested shape is produced by the phase-1 `ready-limit` wrapper, not by `mt5 order limit`. Phase 2 intentionally calls raw `mt5 order limit`, and `metatrader5_cli/mt5/core/order.py:_finalize_order()` returns:

```json
{"ok": true, "data": {"ticket": ..., "symbol": ..., "volume": ..., "magic": ...}}
```

There is no `data.placement`. So a real autopilot placement would journal as `kind="placement"` but with `ticket=None`, `magic=None`, and `volume=None`. That still breaks exactly the lifecycle that this patch was meant to restore:

- `journal.folded_trades()` ignores ticketless placements for outcome folding.
- `agent.resolve_outcomes()` cannot resolve a ticketless placement.
- `trade_manager._open_journal_placements()` cannot ticket-match or magic-match the filled position.
- Dashboard/stats/evidence remain corrupted for real autopilot orders.

The new tests miss this because every mocked order-limit success uses the old nested shape:

```python
{"ok": True, "data": {"placement": {"ticket": 1234, "magic": 128461}}}
```

Required fix: teach `log_autopilot_placement()` to accept both shapes, e.g.:

```python
data = placement.get("data") or {}
placement_data = data.get("placement") or data
```

Then update the autopilot tests to mock the actual `order limit` shape:

```python
{"ok": True, "data": {"ticket": 1234, "magic": 128461, "volume": 0.001}}
```

Add one regression test that calls `attempt_autopilot_place()` with that flat response and asserts the journaled placement has `ticket`, `magic`, `volume`, `entry`, `sl`, and `tp`.

Confidence: high.

## Verified Good

- `agent.scan_once()` now calls `autopilot.poll_bus_for_abort(_state_db_path())` before `resolve_outcomes()`, `place_new_orders()`, `poll_verdicts()`, and `evaluate_pending_consensus()`.
- The abort helper writes the kill switch to state DB and journals `autopilot_kill`; the code path is now active in the running agent loop.
- Writing autopilot trades as `kind="placement"` with `autopilot=true` is the right model once the response-shape bug above is fixed.

## Verification

- `python -m pytest adaptive-forex-mt5/tests/test_phase2_audit_fixes.py adaptive-forex-mt5/tests/test_journal_kinds_phase2.py adaptive-forex-mt5/tests/test_autopilot_gates.py adaptive-forex-mt5/tests/test_autopilot_pipeline.py -q` → `22 passed`
- `python -m pytest -q` → `336 passed, 1 skipped`

## Verdict

NO-GO remains. The bus-abort blocker is closed, but the autopilot placement lifecycle blocker is only partially fixed. With the real `mt5 order limit` response shape, autopilot placements still become untracked ticketless records.
