# Depth of Market and TDA Review

**Agent:** Codex
**Date:** 2026-05-05
**Scope:** Depth of Market CLI, GUI DOM capture, active chart targeting, Ehukai visual TDA context, and TDA final-timeframe restore

## Findings

No unresolved code-review findings after the latest changes.

## Notes

- `market depth` is the structured MT5 Python API path using `market_book_add()`, `market_book_get()`, and `market_book_release()`.
- `chart depth-of-market` opens the actual MT5 Charts > Depth Of Market GUI panel.
- `chart current` reports the active MT5 chart title.
- `chart ensure SYMBOL --timeframe M15` is the broker-agnostic chart-selection primitive agents should run before GUI/screenshot work.
- `ehukai structure` and `ehukai fvg` expose the structured mirrors of the vendored Ehukai MT5 visual indicators.
- `screenshot tda` now returns a visual manifest, a sibling JSON manifest file, and per-frame Ehukai FVG/market-structure context.
- `screenshot dom` opens and captures the GUI DOM panel, then closes/toggles it by default so the DOM view does not block the chart.
- `screenshot tda` now restores the active chart to `M15` by default after the capture loop. Agents can pass `--final-timeframe none` to leave the last captured timeframe active.

## Verification

```powershell
python -m pytest metatrader5_cli/mt5/tests/test_core.py -q
python -m pytest -q
```

Result: `174 passed, 1 skipped`.

Additional live verification:

- `screenshot tda USDJPY --timeframes H1,M15,M5 --context-bars 160 --fvg-limit 4` produced PNGs plus a manifest with `EhukaiMarketStructure` and `EhukaiFVG` context for every frame.
- `ehukai fvg USDJPY M15` returned `source: EhukaiFVG`.
- `ehukai structure USDJPY M15` returned `source: EhukaiMarketStructure`.
- MetaEditor compiled both vendored/deployed indicators with `0 errors, 0 warnings`.

## Residual Risk

GUI automation depends on MT5 window state. Agents should run `chart current` and `chart ensure SYMBOL --timeframe M15` before visual e2e checks so the intended chart is active and verified.
