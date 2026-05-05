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


VISUAL_MANIFEST_VERSION = "2026-05-05"


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
            "label_pattern": "TDA <TF>: <BIAS> | H <kind> <price> | L <kind> <price>",
            "meaning": "Preferred visual presentation layer for screenshot agents. Composes structure, FVG, and liquidity with low-noise defaults.",
            "structured_source": "ehukai structure + ehukai fvg + ehukai liquidity",
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
            "structured_source": "analyze structure / analyze topdown",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "LH / LL swing labels",
            "label_pattern": "LH|LL",
            "meaning": "Bearish swing structure: lower high or lower low.",
            "structured_source": "analyze structure / analyze topdown",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "top-right MS panel",
            "label_pattern": "MS <TF>: <BULLISH|BEARISH|NEUTRAL> ...",
            "meaning": "Current timeframe structure bias and latest high/low classification.",
            "structured_source": "analyze topdown timeframes[TF]",
        },
        {
            "indicator": "EhukaiMarketStructure",
            "visual": "BULLISH BOS / BEARISH BOS text near latest candle",
            "label_pattern": "<BULLISH|BEARISH> BOS",
            "meaning": "Current close has broken the latest swing high or low.",
            "structured_source": "analyze structure current_price vs support/resistance",
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
            "meaning": "The pool has been crossed by a later close. Treat nearby passive entries with extra suspicion.",
            "structured_source": "ehukai liquidity pools[].status == swept",
        },
    ],
    "agent_rules": [
        "Apply only EhukaiTDAOverlay to charts for visual TDA by default.",
        "Use primitive overlays only for debugging: EhukaiFVG, EhukaiMarketStructure, EhukaiLiquiditySwings.",
        "Use screenshots for spatial confluence and chart cleanliness.",
        "Use structured_context for exact prices, states, and distances.",
        "Treat visual and structured data as complementary; if they disagree, report the discrepancy.",
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
