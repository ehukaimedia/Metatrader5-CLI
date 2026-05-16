# Codex Review: adaptive-forex-mt5 ff73a59

Review target: `ff73a59` on `master`

## Findings

No blocking findings.

The four issues from the prior `c614fff` audit are closed:

- The broker e2e tests no longer call the full `scan_once()` placement loop. `agent.resolve_outcomes()` is now split out and used by the outcome test, so the e2e harness no longer scans every pair and accidentally places unrelated READY orders.
- `adaptive-forex-mt5/test_e2e.py` no longer flips `mt5_cli.live` internally. The script refuses without an explicit `--allow-live` flag.
- `metatrader5_cli/mt5/core/analyze.py` now returns `drift_points` in the successful `place_ready_limit()` payload, so `journal.log_placement()` can persist it.
- `journal.stats()` now uses net P/L and exposes R metrics; the dashboard renders `net P/L`, `total R`, and `avg R`.
- The current-cycle concurrency double-count is gone. `place_new_orders()` mutates `active` in place and uses `len(active)` as the single source of truth.

## Residual Risk / Carry-Forward

- `adaptive-forex-mt5/agent.py:102-115` still treats any integer-magic position/order as active for the global cap, rather than scoping to the configured POC magic set. This can make unrelated EAs consume capacity. It is not a safety regression, but it is still worth tightening before running multiple strategies on the same terminal.
- `adaptive-forex-mt5/agent.py:118` still queries only three days of deal history. That is probably fine for M1/M5 sniper trades, but a held-over position older than three days could fail outcome replay after a crash.
- `adaptive-forex-mt5/test_e2e.py` still relies on the operator to verify the account is the intended demo account before passing `--allow-live`. The explicit flag and countdown are enough for this supervised POC, but a future unattended CI path should require an account-login/server allowlist.

## Verification

- `python -m py_compile adaptive-forex-mt5\agent.py adaptive-forex-mt5\journal.py adaptive-forex-mt5\dashboard.py adaptive-forex-mt5\test_e2e.py` passed.
- `python adaptive-forex-mt5\test_e2e.py` refused without `--allow-live` before broker actions.
- `python -m pytest metatrader5_cli\mt5\tests\test_core.py metatrader5_cli\mt5\tests\test_decoupling.py` passed: `217 passed`.
- I did not run `python adaptive-forex-mt5\test_e2e.py --allow-live` during this review because it intentionally places live broker orders; Claude's reported demo run covers that path.

## Verdict

`ff73a59` is green for supervised live-demo evidence collection. The runtime now has the right separation between outcome reconciliation and order placement, the e2e harness is no longer surprising, and the journal/dashboard data is strong enough to support the two intended proofs: whether the strategy has edge and whether the live-capable agent can operate safely under supervision. The remaining items are operational hardening, not blockers.
