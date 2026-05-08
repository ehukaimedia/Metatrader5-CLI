# Codex1 Phase 1 Trade Manager Final Audit - 2026-05-08

Review target: `4c2eb04` (`adaptive-forex-mt5` Phase 1 trade manager + reviewer pipeline).

## Findings

### Production-Risk

1. `adaptive-forex-mt5/trade_manager.py:435` + `metatrader5_cli/mt5/core/position.py:29`

   `_favorable_price()` expects `bid`, `ask`, or `price_current` on each position, but `mt5 position list` currently returns only `open_price`, `sl`, `tp`, `profit`, `swap`, `magic`, and `comment`. In live runtime, favorable price therefore falls back to `open_price`, so fresh positions never satisfy the BE trigger. The spread guard has the same problem: `attempt_modify()` reads `pos.get("spread")`, but position rows do not include spread, so it silently treats spread as `0`.

   What should change: either enrich `position._pos_to_dict()` with current bid/ask/price_current/spread from symbol tick/info, or have `trade_manager.list_positions()` enrich each position before management. Add an integration test using the real `position.list` shape, without injected `bid/ask/spread`, that proves BE can still trigger from current quote and spread caps are enforced.

   Confidence: High.

2. `adaptive-forex-mt5/trade_manager.py:131` + `adaptive-forex-mt5/trade_manager.py:159` + `adaptive-forex-mt5/dashboard.py:38`

   The unmanaged POC warning rate-limit still cannot work for no-match positions. `_should_warn_unmanaged()` returns `True` when no state row exists, and the fail-closed branch logs `unmanaged_poc_position` but never writes a suppression row or cursor. Result: the same orphaned bot-magic position can log every loop. Also, the dashboard reads unmanaged warnings from active `managed_position` rows, so no-match positions that never get a row will not appear in the banner.

   What should change: add a dedicated unmanaged/suppression table or create a minimal non-managed warning row that does not collide with active management. The table should track `ticket`, `symbol`, `magic`, `last_unmanaged_warning_ts`, and reason. Dashboard should read from that source. Add a test that two bootstrap attempts within 60s produce one journal warning and one dashboard-visible warning.

   Confidence: High.

3. `adaptive-forex-mt5/trade_manager.py:374`

   Pending modify handling only applies when the existing `requested_sl` equals the newly proposed `new_sl_rounded`. If a pending Chandelier request is unconfirmed and the next loop computes a different trail level, the function bypasses the pending branch, stages a new request, generates a new idempotency key, and calls `position move-sl` again. That breaks the single-flight contract and can hammer the broker during moving ATR/chandelier targets.

   What should change: any `pending_action == "modify_sl"` should be resolved first, regardless of the newly computed target. Confirm existing request, honor cooldown, and retry the same `requested_sl`/`idempotency_key`; only consider a fresh target after the pending request is confirmed, cancelled, or explicitly marked failed. Add a test where existing `requested_sl=156.400`, fresh proposal is `156.450`, cooldown not elapsed, and no broker call occurs.

   Confidence: High.

### Strategy-Validation Gaps

4. `adaptive-forex-mt5/test_e2e.py:222` + `adaptive-forex-mt5/test_e2e.py:240`

   The new managed lifecycle e2e path is not runnable as written. `order market` requires `--volume`, `--sl`, and optionally `--tp`, but the managed test passes `0.001` as a positional argument and supplies no SL. The cleanup also calls `position close --ticket <id>`, while the CLI expects `position close <ticket>`. A quick Click smoke check confirms both command shapes fail before broker logic.

   What should change: place the managed test order with `--volume 0.001 --sl <valid stop> --tp <optional> --magic <magic>`, close with positional `position close <ticket>`, and ensure the journal placement shape is compatible with bootstrap. If using `order market` directly, do not call `journal.log_placement()` unless it is extended to understand the direct order response; current `log_placement()` expects the `ready-limit` wrapper shape.

   Confidence: High.

### Operational Fragility

5. `adaptive-forex-mt5/trade_manager.py:206`

   Stage inference still treats `sl=0` as a valid sell-side breakeven SL. For a sell, `0 <= entry - buffer` promotes the row to `be_armed` and sets `last_sl_set=0`. Bot placements should normally have an SL, but a broker/read glitch or manual repair can produce `0`, and the manager should fail closed rather than infer protection.

   What should change: if `sl <= 0`, leave stage as `init` and optionally log a manage skip/warning. Add a test for a sell position with `sl=0` staying `init`.

   Confidence: Medium.

## Open Questions

- Should `position list` become the canonical source for quote/spread enrichment, or should the trade manager call a lighter quote endpoint per symbol? I lean toward enriching `position list` because other runtime agents will benefit from the same fields.
- Should unmanaged POC warnings be stored in `state.db` as a separate table rather than overloading `managed_position`? I lean separate table to avoid partial unique-index side effects and to keep fail-closed positions visibly unmanaged rather than half-managed.

## Verification

- `python -m pytest adaptive-forex-mt5/tests -q` -> 59 passed.
- `python -m pytest metatrader5_cli/mt5/tests/test_core.py metatrader5_cli/mt5/tests/test_decoupling.py -q` -> 217 passed.
- Click smoke checks confirmed `position close --ticket <id>` and positional `order market ... 0.001` are invalid CLI forms.

## Summary

Phase 1 is close, and the review/dispatch foundation plus the `position move-sl` confirm-before-promote path are much stronger than the first plan. I would not declare it ready for supervised live manager testing yet. The current manager will not move a fresh position to BE from real `position list` data, unmanaged POC warnings are still not durable/visible, and the pending modify single-flight guarantee has a dynamic-target hole.
