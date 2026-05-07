"""
tda_manifest.py - Visual TDA legend and structured context helpers.

The visual TDA workflow combines MT5 screenshots with rate-derived JSON.  The
manifest describes the chart-object contract used by the Ehukai MQ5 indicators
so visual agents can interpret screenshots consistently.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path


INDICATOR_ROOT = Path(__file__).resolve().parents[1] / "mql5" / "Indicators"


VISUAL_MANIFEST_VERSION = "2026-05-07"


_VISUAL_MANIFEST = {
    "version": VISUAL_MANIFEST_VERSION,
    "purpose": "Map Ehukai MT5 visual indicator overlays to structured TDA concepts.",
    "preferred_chart_indicator": "EhukaiTDAOverlay",
    "indicator_assets": {
        "EhukaiTDAOverlay": str(INDICATOR_ROOT / "EhukaiTDAOverlay.mq5"),
        "EhukaiFVG": str(INDICATOR_ROOT / "EhukaiFVG.mq5"),
        "EhukaiMarketStructure": str(INDICATOR_ROOT / "EhukaiMarketStructure.mq5"),
        "EhukaiLiquiditySwings": str(INDICATOR_ROOT / "EhukaiLiquiditySwings.mq5"),
    },
    "object_contract": {
        "tda_overlay_prefix": "ETDA_",
        "fvg_prefix": "EFVG_",
        "market_structure_prefix": "EMS_",
        "liquidity_swings_prefix": "ELS_",
        "stable_name_parts": ["prefix", "symbol", "timeframe", "type", "ordinal_or_bar_index"],
        "tooltip_policy": "Objects should expose timeframe, side/status, and price levels when MT5 supports tooltips.",
    },
    "legend": [
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "single clean chart overlay",
            "label_pattern": "TDA v1.23 TOP-DOWN / GUIDE: <WAIT|WATCH|NO TRADE> ...",
            "meaning": "Preferred visual presentation layer for screenshot agents and manual TDA. Manual mode shows a left-side top-down structure panel, current-timeframe swing labels, the latest close-confirmed BOS/CHOCH/iBOS rail with a compact marker, active historical FVG zones without text labels by default, subtle recent sweep hints, and a left-side GUIDE panel. M1/M5 use a smaller adaptive FVG threshold for entry work. Filled FVGs disappear; open or partially filled historical FVGs remain eligible and are selected by proximity to current price. Structure reads use the elite-v1 closed-bar contract: swing BOS/CHOCH determines trade permission, internal structure confirms entry-side pressure, and FVG/POI supplies execution context. Top-right status headers, dense FVG text labels, historical BOS/CHOCH text labels, full liquidity rails, stale debug objects, and elite strong/weak rails stay visual-off by default while remaining available as structured context.",
            "structured_source": "ehukai structure + ehukai fvg + ehukai liquidity",
        },
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "manual trade guide label",
            "label_pattern": "GUIDE: <WAIT|WATCH|NO TRADE> ...",
            "meaning": "Checklist-style visual guide that summarizes bias, sweep context, nearest FVG POI, and invalidation. It is a decision aid, not an automatic order trigger.",
            "structured_source": "EhukaiTDAOverlay setup context",
        },
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "top-down structure panel",
            "label_pattern": "TDA v1.23 TOP-DOWN / D1|H4|M15|M5|M1 <read>",
            "meaning": "Multi-timeframe structure scan for setup alignment. D1/H4 set directional permission, M15 frames the setup area, and M5/M1 are execution structure. Reads are based on the last closed candle, not the forming candle.",
            "structured_source": "EhukaiTDAOverlay CopyRates structure read + ehukai.market_structure elite-v1",
        },
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "BOS/CHOCH/iBOS rails",
            "label_pattern": "latest solid/dotted break rail with compact BOS/CHOCH/iBOS marker",
            "meaning": "Latest close-confirmed break map. BOS/CHOCH frame market structure; iBOS helps read lower-timeframe entry structure. Older break rails are hidden by default to avoid treating stale opposite-side breaks as current guidance.",
            "structured_source": "EhukaiTDAOverlay elite event engine",
        },
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "sniper state label",
            "label_pattern": "SNIPER <TF> | <NO_TRADE|WATCH_BUY|WATCH_SELL|ARMED_BUY|ARMED_SELL|TRIGGER_BUY|TRIGGER_SELL> | <score> | <reason>",
            "meaning": "Sniper-mode summary. Wicks can arm liquidity context, but BOS/CHOCH requires a closed candle beyond the swing level.",
            "structured_source": "EhukaiTDAOverlay TDA_SNIPER mode",
        },
        {
            "indicator": "EhukaiFVG",
            "visual": "lime or green rectangle/lines",
            "label_pattern": "BULL FVG <OPEN|PARTIAL|FILLED> <pips>p",
            "meaning": "Bullish fair value gap. Price may rebalance into this demand-side inefficiency.",
            "structured_source": "indicator fvg --direction bullish",
        },
        {
            "indicator": "EhukaiFVG",
            "visual": "red rectangle/lines",
            "label_pattern": "BEAR FVG <OPEN|PARTIAL|FILLED> <pips>p",
            "meaning": "Bearish fair value gap. Price may rebalance into this supply-side inefficiency.",
            "structured_source": "indicator fvg --direction bearish",
        },
        {
            "indicator": "EhukaiFVG",
            "visual": "dashed midpoint line inside an FVG",
            "label_pattern": "midline",
            "meaning": "FVG mean threshold. Use as a visual refinement level, not a standalone entry.",
            "structured_source": "indicator fvg values[].mid",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "HH / HL swing labels",
            "label_pattern": "HH|HL",
            "meaning": "Bullish swing structure: higher high or higher low.",
            "structured_source": "ehukai.market_structure / analyze topdown elite-v1",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "LH / LL swing labels",
            "label_pattern": "LH|LL",
            "meaning": "Bearish swing structure: lower high or lower low.",
            "structured_source": "ehukai.market_structure / analyze topdown elite-v1",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "top-right MS panel",
            "label_pattern": "MS <TF>: <BULLISH|BEARISH|NEUTRAL> ...",
            "meaning": "Current timeframe structure bias and latest high/low classification.",
            "structured_source": "analyze topdown timeframes[TF] elite-v1",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "BULLISH/BEARISH BOS or CHOCH text near latest candle",
            "label_pattern": "<BULLISH|BEARISH> <BOS|CHOCH>",
            "meaning": "BOS is continuation through the latest swing level. CHOCH is a close-confirmed break against the prior HH/HL or LH/LL structure.",
            "structured_source": "ehukai.market_structure last_closed_bar vs swing support/resistance",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "green support / red resistance level",
            "label_pattern": "SUPPORT|RESISTANCE",
            "meaning": "Latest swing low/high level extended right for visual reference.",
            "structured_source": "analyze structure support/resistance",
        },
        {
            "indicator": "EhukaiLiquiditySwings",
            "visual": "red liquidity zone above a swing high",
            "label_pattern": "BSL LIQ <OPEN|SWEPT> C<count> V<volume>",
            "meaning": "Buy-side liquidity resting above a swing high. Use as a target or trap zone, not as a long signal.",
            "structured_source": "ehukai liquidity pools[].side == buy_side",
        },
        {
            "indicator": "EhukaiLiquiditySwings",
            "visual": "teal liquidity zone below a swing low",
            "label_pattern": "SSL LIQ <OPEN|SWEPT> C<count> V<volume>",
            "meaning": "Sell-side liquidity resting below a swing low. Use as a target or trap zone, not as a short signal.",
            "structured_source": "ehukai liquidity pools[].side == sell_side",
        },
        {
            "indicator": "EhukaiLiquiditySwings",
            "visual": "dashed liquidity level",
            "label_pattern": "SWEPT",
            "meaning": "The pool has been pierced by a wick and price closed back through the pool, marking sweep context rather than directional confirmation.",
            "structured_source": "ehukai liquidity pools[].status == swept",
        },
        {
            "indicator": "EhukaiTDAOverlay",
            "visual": "tiny BSL sweep / SSL sweep marker",
            "label_pattern": "BSL sweep|SSL sweep",
            "meaning": "Subtle liquidity sweep context shown without drawing full liquidity rails through the chart.",
            "structured_source": "ehukai liquidity pools[].status == swept",
        },
    ],
    "agent_rules": [
        "Apply only EhukaiTDAOverlay to charts for visual TDA by default.",
        "Use primitive overlays only for debugging: EhukaiFVG, EhukaiMarketStructure, EhukaiLiquiditySwings.",
        "Keep full liquidity drawings off by default; use structured_context liquidity and subtle sweep markers as target/sweep context, not as a directional trigger.",
        "Keep clean agent screenshot mode on for visual TDA; it clears stale EMS_/EFVG_/ELS_ objects and leaves the chart focused on structure, FVG, sweep markers, and the GUIDE panel.",
        "Use screenshots for spatial confluence and chart cleanliness.",
        "Use structured_context for exact prices, states, and distances.",
        "Use the elite-v1 hierarchy: D1/H4 permission, M15 setup area, M5/M1 entry structure; do not invert that order because a lower-timeframe CHOCH alone is only an early signal.",
        "Treat visual and structured data as complementary; if they disagree, report the discrepancy.",
        "In TDA_SNIPER mode, treat wick-through/close-back as sweep context and closed-body breaks as BOS/CHOCH confirmation.",
        "Do not use FVG, BOS, or DOM alone as a trade trigger without TDA context and dry-run validation.",
    ],
}


def visual_manifest() -> dict:
    """Return a copy of the visual TDA manifest."""
    return deepcopy(_VISUAL_MANIFEST)


def _compact_error(result: dict | object) -> dict:
    if isinstance(result, dict) and isinstance(result.get("error"), dict):
        error = result["error"]
        return {
            "code": error.get("code"),
            "message": error.get("message"),
            "mt5_retcode": error.get("mt5_retcode"),
        }
    return {
        "code": "TDA_CONTEXT_ERROR",
        "message": "Structured TDA context could not be computed.",
        "mt5_retcode": None,
    }


def _limit_tail(rows: list[dict], limit: int = 5) -> list[dict]:
    return rows[-limit:] if len(rows) > limit else rows


def frame_context(symbol: str, timeframe: str, *, bars: int = 300, fvg_limit: int = 8) -> dict:
    """Return Ehukai-structured context for one screenshot frame.

    This is intentionally fail-soft: screenshot capture should still succeed
    when market data is temporarily unavailable.
    """
    context: dict = {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "source": "ehukai_recomputed",
        "notes": [
            "This context follows the vendored Ehukai MQ5 indicator contracts.",
            "It is recomputed from rates; it is not a direct dump of MT5 chart objects.",
        ],
    }

    try:
        from metatrader5_cli.mt5.core import ehukai  # noqa: PLC0415

        structure_result = ehukai.market_structure(symbol, timeframe, bars=bars)
        if isinstance(structure_result, dict) and structure_result.get("ok"):
            context["market_structure"] = structure_result["data"]
        else:
            context["market_structure_error"] = _compact_error(structure_result)

        fvg_result = ehukai.fvg(
            symbol,
            timeframe,
            bars=min(bars, 100),
            max_zones=fvg_limit,
        )
        if isinstance(fvg_result, dict) and fvg_result.get("ok"):
            context["fvg"] = fvg_result["data"]
        else:
            context["fvg_error"] = _compact_error(fvg_result)

        liquidity_result = ehukai.liquidity(
            symbol,
            timeframe,
            bars=bars,
            max_pools=10,
        )
        if isinstance(liquidity_result, dict) and liquidity_result.get("ok"):
            context["liquidity"] = liquidity_result["data"]
        else:
            context["liquidity_error"] = _compact_error(liquidity_result)
    except Exception as exc:  # noqa: BLE001
        context["error"] = {
            "code": "TDA_CONTEXT_EXCEPTION",
            "message": str(exc),
            "mt5_retcode": None,
        }

    return context
