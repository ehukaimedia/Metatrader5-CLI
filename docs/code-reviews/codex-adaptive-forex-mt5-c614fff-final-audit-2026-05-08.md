# Codex Review: adaptive-forex-mt5 c614fff/c2b9559

Review target: `c614fff` plus `c2b9559` on `master`

## Findings

### 🔴 Production-risk: E2E tests can place unrelated live orders while verifying guard/outcome behavior

File: `adaptive-forex-mt5/test_e2e.py:99`, `adaptive-forex-mt5/test_e2e.py:183`

Both broker e2e tests call `agent.scan_once(cfg)` with `cfg["mt5_cli"]["live"] = True`. `scan_once()` does not have a reconciliation-only mode; after it handles active-strategy or outcome checks it continues through all configured pairs and calls `place_ready_limit()` for any pair whose `sniper_poc` returns `ready`. That means running the "active strategy guard" test can place unrelated real limit orders on other pairs, and running the "outcome attribution" test can do the same after closing the synthetic EURUSD position. This is especially risky because the test suite is meant to be a safety proof, but the proof harness itself can mutate the account beyond the scenario under test.

What should change: add a scan mode such as `scan_once(cfg, allow_placements=False)` or split reconciliation/guard verification from placement execution, and use that mode in e2e tests. Alternatively, make the e2e config pair-scoped and cap-scoped so no pair except the test pair can reach `place_ready_limit()`.

Confidence: High.

### 🔴 Production-risk: E2E test forces live execution without an explicit external confirmation

File: `adaptive-forex-mt5/test_e2e.py:249-252`

If `config.json` has `mt5_cli.live=false`, the e2e test prints a warning and flips it to `True`. The test then places a pending USDJPY limit and a market EURUSD position. The file comments say "Run only on demo", but the code does not require an environment confirmation, does not verify account identity, and does not stop on an unintended account. This makes accidental real-money mutation too easy, especially because the project now has live-capable runtime paths.

What should change: require an explicit environment variable such as `ADAPTIVE_E2E_LIVE_CONFIRM=USDJPY_EURUSD_MICRO_ORDERS`, print account/server/login before execution, and fail closed unless the confirmation is present. This does not block the live demo runtime; it only prevents accidental e2e execution.

Confidence: High.

### 🟠 Strategy-validation gap: `drift_points` is journaled but never returned by the placement command

File: `adaptive-forex-mt5/journal.py:76`, `metatrader5_cli/mt5/core/analyze.py:1025-1089`

`journal.log_placement()` stores `data["drift_points"]`, but `place_ready_limit()` computes `drift_points` and omits it from the success payload. As a result placement records silently get `drift_points: null`. This weakens the evidence stream: later review cannot quantify how stable entry price was between initial READY detection, dry-run, final refresh, and actual placement.

What should change: include `drift_points` and `max_entry_drift_points` in the success data, and ideally in drift-rejection failure data too.

Confidence: High.

### 🟠 Strategy-validation gap: Dashboard stats still score gross `profit`, not net or R

File: `adaptive-forex-mt5/journal.py:144-165`

Outcomes now store `profit`, `swap`, `commission`, `net`, and `realized_r`, which is good. But `journal.stats()` still computes wins/losses and total P/L from gross `profit`. If swap or commission later matter, the dashboard can report a winning strategy while net economics are flat or negative. The raw journal is good enough for manual analysis, but the dashboard summary can mislead the strategy proof.

What should change: report both gross and net totals, and add `avg_realized_r` / `expectancy_r`. Use net for the primary P/L summary while preserving gross direction-correctness separately.

Confidence: Medium.

### 🟡 Operational fragility: Current-cycle placement cap double-counts new placements

File: `adaptive-forex-mt5/agent.py:266`, `adaptive-forex-mt5/agent.py:300-301`

After a successful placement, the code both adds `(pair, magic)` to `active` and increments `placed_this_cycle`. The loop guard then checks `len(active) + placed_this_cycle`, which double-counts placements made during the current scan. With `max_concurrent_positions=2`, the agent can place only one order even though the cap allows two. With the current default of 50 this is not urgent, but it will matter during tighter supervised demo caps.

What should change: either mutate `active` and remove `placed_this_cycle`, or leave `active` as the pre-scan snapshot and use `placed_this_cycle` separately.

Confidence: High.

### 🟡 Operational fragility: Active-strategy set is not scoped to configured strategy magics

File: `adaptive-forex-mt5/agent.py:102-115`, `adaptive-forex-mt5/agent.py:271-274`

`active_strategies()` includes every open position or pending order with any integer `magic`, not just the POC's configured strategy magics. That can cause unrelated EAs to consume the global concurrency cap. The per-pair skip check also derives `ehukai-poc-{PAIR}` locally, so if strategy IDs become configurable per pair later, the active check can drift from the actual placement magic.

What should change: compute an allowlist of configured strategy magics and have `active_strategies()` return only those. Reuse the same resolver for placement and active checks.

Confidence: Medium.

## Open Questions / Assumptions

- I did not run `adaptive-forex-mt5/test_e2e.py` because it can place real broker orders.
- `find_close_deal()` is much improved and now anchors on the opening deal. I am assuming Trading.com reports filled pending-limit opening deals with `deal.order == placement_ticket`; the new e2e validates market orders, not a filled pending-limit close lifecycle.
- The runtime is currently safer than the test harness. The most urgent fix is to make broker e2e side effects explicit and constrained.

## Summary

The latest runtime changes materially improve evidence collection: magic is stored at placement, outcome matching is better, full skip reasoning is present, and pending orders now count toward active strategy state. But I would not call the POC fully green until the e2e harness is made non-surprising. The runtime can support supervised demo collection; the current e2e test can accidentally place extra trades while trying to prove safety, which is the one part that must be tightened before this becomes a reliable live-demo validation workflow.
