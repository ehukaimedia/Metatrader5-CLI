# Codex1 Final Audit: Phase 1 Trade Manager Fixes (`11cb714`)

Date: 2026-05-08
Scope: `11cb714 Fix Codex1 phase-1 final-audit findings 1-5`

## Verdict

No blocking findings. Phase 1 is green for supervised demo testing after this fix commit.

## Verified Fixes

- `adaptive-forex-mt5/trade_manager.py:75` now enriches `position list` rows with per-symbol `market info` bid, ask, and spread. This closes the BE/trailing blind spot where runtime positions fell back to `open_price` and spread was treated as zero.
- `adaptive-forex-mt5/state_db.py:193`, `:215`, and `:229` add a dedicated `unmanaged_warning` table with rate-limit/read helpers. `adaptive-forex-mt5/dashboard.py:29` now reads that table, so fail-closed unmanaged POC positions can surface even when no `managed_position` row exists.
- `adaptive-forex-mt5/trade_manager.py:378` resolves any existing pending SL modify before considering a fresh target. Retry uses the stored `requested_sl` and `idempotency_key`, closing the dynamic Chandelier target double-submit hole.
- `adaptive-forex-mt5/test_e2e.py:209` now uses the real CLI surface for managed lifecycle smoke testing: `order market ... --volume ... --sl ...` and `position close <ticket>`. It also synthesizes a placement-shaped journal row so bootstrap can ticket-match.
- `adaptive-forex-mt5/trade_manager.py:217` guards `sl <= 0`, so a sell with no protective stop no longer promotes to `be_armed`.

## Regression Coverage

- `adaptive-forex-mt5/tests/test_audit_fixes.py:37` checks quote enrichment.
- `adaptive-forex-mt5/tests/test_audit_fixes.py:90` and `:109` check unmanaged warning rate-limit and dashboard-visible storage.
- `adaptive-forex-mt5/tests/test_audit_fixes.py:133` and `:185` check pending modify single-flight and same-request retry behavior.
- `adaptive-forex-mt5/tests/test_audit_fixes.py:235` and `:259` check buy/sell `sl=0` stage inference.

## Verification

- `python -m pytest adaptive-forex-mt5/tests/test_audit_fixes.py -q` -> 8 passed
- `python -m pytest adaptive-forex-mt5/tests -q` -> 67 passed
- `python -m pytest metatrader5_cli/mt5/tests/test_core.py metatrader5_cli/mt5/tests/test_decoupling.py -q` -> 217 passed

Total focused coverage: 284 passed.

## Residual Risk

The manager still falls back to `open_price` if quote enrichment fails. That is acceptable for this green pass because `market info` is a valid CLI command and now tested through the manager wrapper, but a future hardening pass could fail closed with a `manage_skip` reason such as `quote_unavailable` instead of silently falling back.
