# Elite v1 Structure Alignment Review

Date: 2026-05-07

## Scope

- `metatrader5_cli/mt5/core/ehukai.py`
- `metatrader5_cli/mt5/core/analyze.py`
- `metatrader5_cli/mt5/pine/EhukaiStructure.pine`
- `metatrader5_cli/mt5/mql5/Indicators/EhukaiTDAOverlay.mq5`
- `metatrader5_cli/mt5/mql5/Indicators/EhukaiMarketStructure.mq5`

## Result

The TDA stack now has one canonical structure contract: `elite-v1`.

- Swing structure uses the video/Pine `8 / 3 / 1` model: swing pivot `8`, internal pivot `3`, fractal early signal `1`.
- BOS/CHOCH decisions use the last closed bar, not the currently forming candle.
- `analyze topdown` now consumes `ehukai.market_structure()` instead of the old generic classifier, so CLI/agent JSON and visual TDA context share the same structure read.
- Pine is renamed to `Ehukai Structure v1.0 elite-v1`; noisy strong/weak, failure, and premium/discount rails are off by default.
- MT5 overlay is `v1.23`; primitive market-structure indicator is `v1.12`.

## Verification

- `python -m pytest metatrader5_cli\mt5\tests\test_core.py -k "topdown or ehukai"`: 10 passed.
- MetaEditor compile `EhukaiTDAOverlay.mq5`: 0 errors, 0 warnings.
- MetaEditor compile `EhukaiMarketStructure.mq5`: 0 errors, 0 warnings.
- Captured USDJPY D1/H4/M15/M5/M1 screenshots to `docs/code-reviews/tda-usdjpy-elite-v1-20260507/`.

## USDJPY Read

Structured read after the alignment:

- D1: bearish CHOCH, transition state; watch, not immediate permission by itself.
- H4: bearish LH/LL, aligned sell permission.
- M15: bullish HH/HL, pullback/setup conflict against H4.
- M5: bearish LH/LL, aligned sell permission.
- M1: neutral/range; no entry trigger yet.

Conclusion: no clean immediate high-confidence snipe at capture time. The cleaner read is to wait for M1/M5 to produce a close-confirmed break aligned with the chosen H4/M15 setup context, then use nearby active FVG/POI for execution.
