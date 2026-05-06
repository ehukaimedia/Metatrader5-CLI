# Ehukai TDA Sniper Review

Date: 2026-05-06
Reviewer: code-reviewer subagent
Scope:

- `metatrader5_cli/mt5/mql5/Indicators/EhukaiTDAOverlay.mq5`
- `metatrader5_cli/mt5/core/tda_manifest.py`
- `docs/plans/2026-05-06-ehukai-tda-sniper-integration.md`
- `docs/playgrounds/mt5-codebase.html`

## Initial Findings

- Alert de-duplication included score, which could allow repeat alerts on the same closed signal bar.
- Sniper FVG rendering selected both nearest bullish and bearish FVGs instead of bias-relevant actionable zones.
- Sniper liquidity rendering selected both buy-side and sell-side liquidity instead of the side relevant to setup direction.
- Visual manifest sniper state pattern omitted `_BUY` and `_SELL` suffixes emitted by the indicator.
- Visual manifest liquidity sweep wording still described old close-through semantics instead of wick-through plus close-back.

## Fixes Applied

- Alert de-duplication now keys by symbol, timeframe, state, and signal bar time, excluding score.
- Sniper FVG rendering is bias-gated:
  - bullish/neutral bias can show bullish FVGs;
  - bearish/neutral bias can show bearish FVGs.
- Sniper liquidity rendering is bias-gated toward the opposing/invalidation side:
  - bullish/neutral bias can show sell-side liquidity;
  - bearish/neutral bias can show buy-side liquidity.
- Manifest sniper label pattern now includes `WATCH_BUY`, `WATCH_SELL`, `ARMED_BUY`, `ARMED_SELL`, `TRIGGER_BUY`, and `TRIGGER_SELL`.
- Manifest sweep description now matches wick-through plus close-back semantics.

## Second Pass

No blocking findings.

Residual risks:

- MT5 visual replay should still validate state transitions across real bullish and bearish examples.
- Alert payload does not yet include nearest POI/invalidation details from the ideal acceptance criteria.
- Neutral bias intentionally allows both directions in v1 and should be watched for visual noise.

## Verification

- MetaEditor compile: `EhukaiTDAOverlay.mq5` compiled with 0 errors and 0 warnings.
- Focused pytest: `pytest -q metatrader5_cli\mt5\tests\test_core.py -k "visual_manifest or screenshot_tda"` passed.

