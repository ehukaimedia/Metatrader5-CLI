# Code Review - Advanced OFProxy Production Hardening

Date: 2026-05-11
Reviewer: Codex
Scope: CSV-only production hardening for `Advanced_Wavelet_Entry_ResearchEA.mq5`

## Findings

No blocking issues found after the v2 hardening pass.

## Changes Reviewed

- Invalid base-indicator `SignalState` values are ignored instead of being treated as buy/sell by sign.
- When `InpUseOrderFlowProxy=true`, a missing proxy companion indicator now fails `OnInit` instead of producing blank proxy diagnostics.
- Proxy-not-ready states are exported as `of_proxy_profile_state=-3` and `of_proxy_decision_class=proxy_not_ready`.
- `InpPreferFOK` is reset before every order attempt, so the broker-filling fallback from one rejected order does not silently change future order behavior.
- Daily guards are still per-symbol/magic by default, but can be widened to account-wide with `InpDailyGuardsAccountWide=true`.
- `of_data_mode` must now be positive before proxy data is treated as available.
- `of_proxy_decision_class` separates the stable enum from signal direction.
- `of_proxy_signal_direction` explicitly carries wavelet direction.
- `of_proxy_alignment_score`, `of_proxy_evidence_score`, and `of_proxy_conflict_score` are exported for bucket analysis.
- `of_proxy_profile_state` separates proceed evidence, mixed/investigate, no-evidence, and conflict.
- Trade CSV rows now include proxy state/score/reason at entry, and closed rows also attempt to record exit proxy state.
- Proxy CSV filenames moved to `ofproxy_v2` to avoid schema mixing.
- All `.set` files now include the new decision-threshold inputs.

## Validation

- Full package MetaEditor compile after production hardening: 0 errors, 0 warnings.
- Terminal-data EA compile after production hardening: 0 errors, 0 warnings.
- Preset input parity check: 95 EA inputs, 95 values in each `.set`, no missing or unknown names.

## Residual Risk

The USDJPY M5 HC80 proxy evidence bucket looked promising in the prior `ofproxy_v1` run, but this remains a diagnostic segmentation result. Production-demo promotion still requires rerunning `ofproxy_v2`, validating by year and symbol, and comparing against the no-proxy baseline before enabling score adjustment or hard filtering.
