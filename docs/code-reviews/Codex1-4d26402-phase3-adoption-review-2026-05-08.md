# Codex1 Phase-3 Adoption Review — 4d26402

Review target: `f9c20f8..4d26402` (`adaptive-forex-mt5` manual-trade adoption).

Verification:
- `python -m pytest adaptive-forex-mt5/tests/test_adopt.py adaptive-forex-mt5/tests/test_adoption_bootstrap.py -q` → 14 passed
- `python -m pytest adaptive-forex-mt5/tests -q` → 134 passed
- `python -m pytest -q` → 351 passed, 1 skipped

Verdict: NO-GO for live adoption until the allowlist gate enforces the full claim identity and the adoption-specific management fields stop being metadata-only.

## Findings

### 🔴 P1 — Allowlist is keyed by ticket only, despite the ticket+symbol+account contract

Files:
- `adaptive-forex-mt5/trade_manager.py:574-586`
- `adaptive-forex-mt5/adopt.py:38-81`
- `docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md:194-196`

The Phase-3 spec says adoption is keyed by `ticket+symbol+account`, but `loop_once()` only checks:

```python
is_adopted = pos.get("ticket") in adopted
```

Then `_ensure_adopted_placement()` synthesizes a placement from the live position without validating that the allowlist entry's `account` equals `_account_login(cfg)` or that `entry["symbol"] == pos["symbol"]`.

Impact: a stale or mis-copied allowlist ticket can authorize the wrong live position if the terminal is on a different account, or if the ticket entry was intended for another symbol. This is exactly the class of bug the allowlist is supposed to prevent: manual adoption must be explicit and narrow.

What should change:
- Replace `adopted_tickets()` use in `loop_once()` with a lookup that verifies `ticket`, `symbol`, and `account`.
- If `_account_login()` returns `0`/unknown, fail closed for manual adoption.
- Add tests:
  - allowlisted ticket but wrong symbol → untouched
  - allowlisted ticket but wrong account → untouched
  - account lookup failure → untouched

Confidence: High.

### 🔴 P1 — Manual adoption can proceed with no protective SL / no initial-risk contract

Files:
- `adaptive-forex-mt5/trade_manager.py:191-195`
- `adaptive-forex-mt5/trade_manager.py:535-537`
- `docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md:194-196`

The forward spec includes `initial_risk`, but the implemented allowlist schema omits it and the synthesized placement blindly uses `pos["sl"]`. If the manual position has `sl == 0` or missing SL, `bootstrap_position()` seeds:

```python
initial_sl = float(placement.get("sl") or pos["sl"])
initial_risk_price = abs(entry_price - initial_sl)
```

For manual adoption, this should fail closed. Without a protective SL or explicit operator-provided initial risk, the manager does not know the true R model. It will fall back to points-based BE behavior and can still later move SL, but the trade is unmanaged during the highest-risk period and journaled with misleading risk.

What should change:
- Require adopted positions to have `pos.sl > 0`, or implement the spec's `initial_risk` field and use that explicitly.
- If missing, journal an `adoption_skip` / unmanaged warning with `reason=no_protective_sl_or_initial_risk`.
- Add a regression test: allowlisted magic-0 position with `sl=0` does not synthesize placement and does not create a managed row.

Confidence: High.

### 🟠 P2 — `mode`, `be_r`, and `trail_model` are recorded but not enforced

Files:
- `adaptive-forex-mt5/adopt.py:17-19`
- `adaptive-forex-mt5/trade_manager.py:252-286`
- `adaptive-forex-mt5/trade_manager.py:485-510`
- `adaptive-forex-mt5/trade_manager.py:540-547`
- `adaptive-forex-mt5/README.md:410-414`

The allowlist schema exposes `mode`, `be_r`, and `trail_model`, and the README tells the operator the adopted trade uses the configured `be_r` and `trail_model`. The implementation only copies those fields into `reasoning`; `manage_one()` and `compute_be_target()` still use global `cfg["manager"]`.

Impact: the operator can set `"mode": "trail_only"` and `"be_r": 1.0`, but the bot will still run the normal BE move at global `be_trigger_r` (currently 0.80) and the normal global chandelier. That is surprising behavior in a live exit manager.

What should change:
- Either remove these fields from the schema/docs until they are real, or store adoption options in state and enforce them.
- At minimum, tests should pin:
  - `trail_only` does not perform a BE move unless that is explicitly intended
  - allowlist `be_r` overrides global `manager.be_trigger_r` for adopted trades
  - unsupported `trail_model` fails closed

Confidence: High.

### 🟡 P3 — `bootstrap_position()` now relies entirely on callers for scope

File:
- `adaptive-forex-mt5/trade_manager.py:165-176`

Dropping the poc-magic precondition is reasonable if `loop_once()` remains the only production caller. I verified runtime code only calls it from `loop_once()`. The remaining direct calls are tests.

Residual risk: the function name and docstring still make it look like a safe bootstrap primitive. A future caller could pass any position with any matching `kind=placement` row and create a managed row outside the poc/adoption gates.

What should change:
- Keep this as a non-blocking hardening item if P1 is fixed in `loop_once()`.
- Prefer adding an explicit `eligible: bool` / `source: "poc" | "adopted"` parameter or renaming to `_bootstrap_position_after_gate()` to make misuse harder.

Confidence: Medium.

## Notes

The `.ehukaiconnect` relationship remains integration-only. The committed Phase-3 diff touches `adaptive-forex-mt5` files and docs/examples, not an EhukaiConnect app repository. Runtime `.ehukaiconnect/` state should stay untracked and machine-local.
