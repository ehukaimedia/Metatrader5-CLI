# Depth of Market CLI Plan

**Date:** 2026-05-05
**Status:** Implemented

## Goal

Expose MetaTrader 5 Depth of Market as both structured JSON when broker data is available and as a GUI visual capture when agents need to inspect the MT5 panel.

## Architecture Decision

Implement DOM as two explicit paths:

- `market depth` is the read-only structured market-data primitive in `core/market.py`, using MT5 `market_book_*`.
- `chart depth-of-market` / `chart dom` is the GUI menu path that opens Charts > Depth Of Market for the active symbol.
- `screenshot dom` captures the GUI panel for visual agent review and closes/toggles it by default so it does not block the chart.
- `chart current` and `chart ensure SYMBOL --timeframe M15` make the active chart deterministic before GUI/TDA/DOM workflows.

## Commands

```powershell
mt5 --json market depth USDJPY --levels 5
mt5 --json chart current
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json chart depth-of-market USDJPY
mt5 --json chart dom USDJPY
mt5 --json screenshot dom USDJPY --output-dir "$env:TEMP\mt5-cli\dom"
```

## Implementation Notes

- Call `bridge.ensure_symbol(symbol)` before DOM access.
- Use the official lifecycle: `market_book_add(symbol)`, `market_book_get(symbol)`, then `market_book_release(symbol)` in `finally`.
- Normalize `BookInfo(type, price, volume, volume_dbl)` entries into bid/ask ladders.
- Sort asks ascending and bids descending.
- Return best bid/ask, spread, midpoint, side volumes, and volume imbalance.
- Treat unsupported broker/symbol DOM as an error envelope, not an exception.
- Open GUI DOM through the terminal menu when structured `market_book_*` data is unavailable.
- Keep DOM child-window closing opt-in only; default captures must not close or disturb the operator's chart layout.
- Leave TDA workflows on `M15` by default after capture.

## Verification

- Unit tests cover success, level limiting, subscribe failure, get failure with release, and CLI JSON paths.
- Demo integration smoke allows either a successful DOM snapshot or documented broker/symbol unsupported errors.
- Live Trading.com demo verification showed GUI DOM opens and screenshots work, while Python `market_book_add()` currently returns unsupported for tested FX symbols.
- Specs, README, agent skill doc, and codebase playground are updated with DOM, chart selection, and TDA final-timeframe behavior.
