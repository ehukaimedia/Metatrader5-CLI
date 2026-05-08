# Depth of Market CLI Plan

**Date:** 2026-05-05
**Status:** Implemented

## Goal

Expose MetaTrader 5 Depth of Market as both structured JSON when broker data is available and as a GUI visual capture when agents need to inspect the MT5 panel. Use that context with Ehukai visual TDA to produce non-mutating, quote-aware M1 sniper POC plans.

## Architecture Decision

Implement DOM as two explicit paths:

- `market depth` is the read-only structured market-data primitive in `core/market.py`, using MT5 `market_book_*`.
- `chart depth-of-market` / `chart dom` is the GUI menu path that opens Charts > Depth Of Market for the active symbol.
- `screenshot dom` captures the GUI panel for visual agent review and closes/toggles it by default so it does not block the chart.
- `chart current` and `chart ensure SYMBOL --timeframe M15` make the active chart deterministic before GUI/TDA/DOM workflows.
- `analyze sniper-poc` consumes Ehukai structure/FVG/liquidity context plus DOM or quote fallback to return `no_trade`, `watch`, or `ready`; it never places orders and returns dryrun-before-placement commands when a setup is ready.

## Commands

```powershell
mt5 --json market depth USDJPY --levels 5
mt5 --json chart current
mt5 --json chart ensure USDJPY --timeframe M15
mt5 --json chart depth-of-market USDJPY
mt5 --json chart dom USDJPY
mt5 --json screenshot dom USDJPY --output-dir "$env:TEMP\mt5-cli\dom"
mt5 --json analyze sniper-poc USDJPY --direction auto --max-spread-points 30 --min-stop-points 50 --max-sweep-age-bars 12 --max-fvg-age-bars 20 --max-entry-distance-pips 15 --summary
```

## Implementation Notes

- Call `bridge.ensure_symbol(symbol)` before DOM access.
- Use the official lifecycle: `market_book_add(symbol)`, `market_book_get(symbol)`, then `market_book_release(symbol)` in `finally`.
- Normalize `BookInfo(type, price, volume, volume_dbl)` entries into bid/ask ladders.
- Sort asks ascending and bids descending.
- Return best bid/ask, spread, midpoint, side volumes, and volume imbalance.
- Treat unsupported broker/symbol DOM as an error envelope, not an exception.
- Open GUI DOM through the terminal menu when structured `market_book_*` data is unavailable.
- Close/toggle the DOM panel after default captures so it does not block the operator's chart layout.
- Leave TDA workflows on `M15` by default after capture.
- Reject sniper POC plans when the current bid/ask spread is wider than the configured gate or the proposed limit is not safely beyond the correct trigger quote side.
- Reject sniper POC plans when the enabling liquidity sweep is stale, the FVG is stale/partial by default, the entry midpoint is too far from the trigger quote, or the symbol is in the FX 21:00-22:59 UTC rollover window unless explicitly allowed.
- Gate sniper liquidity freshness with true `sweep_age_bars`; use faster M1/M5 liquidity pivots (`length=5`) so fresh stop-runs visible on the chart are represented in structured data.
- Treat a ready sniper POC setup as analysis only: agents must run the returned `order dryrun --order-type limit` command and then re-check quote/order freshness before sending the returned `order limit`.
- Widen the suggested SL to at least the configured minimum stop distance before computing R:R so the plan is closer to what broker dry-run checks will accept.
- Keep `EhukaiTDAOverlay` visually low-noise: in agent screenshot mode, hide oversized FVGs and distant liquidity pools while preserving full structured context in JSON.

## Verification

- Unit tests cover success, level limiting, subscribe failure, get failure with release, and CLI JSON paths.
- Demo integration smoke allows either a successful DOM snapshot or documented broker/symbol unsupported errors.
- Live Trading.com demo verification showed GUI DOM opens and screenshots work, while Python `market_book_add()` currently returns unsupported for tested FX symbols.
- Specs, README, agent skill doc, and codebase playground are updated with DOM, chart selection, and TDA final-timeframe behavior.
