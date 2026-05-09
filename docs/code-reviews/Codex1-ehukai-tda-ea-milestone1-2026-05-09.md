# Codex1 Ehukai TDA EA Milestone 1 Review

Date: 2026-05-09

## Findings

1. Fixed before handoff: HTF/MTF bias alignment was initially implemented as a majority vote across D1/H4/M15/M5. The strategy contract requires D1 and H4 to align with M15, so `ResolveDirection` now returns a direction only when D1, H4, and M15 are all valid, nonzero, and aligned.

2. Fixed before handoff: LTF confirmation initially allowed a generic M5 stage fallback. The strategy contract requires an actual LTF BOS/CHOCH/iBOS close in the setup direction, so `EntryConfirmed` now accepts only M5/M1 BOS, CHOCH, or iBOS events.

3. Remaining blocker: command-line Strategy Tester smoke cannot yet prove EA execution because `terminal64.exe /config:<ini>` exits `0` in less than one second with no report, no EA CSV journals, and no new terminal log lines while the same MT5 installation is already running live charts. The wrapper now reports this as `TESTER_NO_ARTIFACTS` instead of treating launcher success as a passed backtest.

4. Resolved after Claude1 review: the spec had conflicting language that could be read as "skip whenever ATR/pair floors widen the swept-extreme stop." The implementation intentionally widens only outward from the swept extreme, preserves account risk through smaller lot sizing, and skips when the widened plan fails RR, lot sizing, or spread-adjusted survival checks. The spec now reflects that policy.

## Verification

- MetaEditor compile: `0 errors, 0 warnings`
- Focused core tests: `226 passed`
- Full suite: `368 passed, 1 skipped`
- USDJPY M5 smoke attempted for `2026-04-01` to `2026-04-30`; blocked by `TESTER_NO_ARTIFACTS`

## Review State

Claude1 has the artifact paths and is reviewing against the Ehukai / Photon SMC contract, including the transcript refresh supplied by the operator.
