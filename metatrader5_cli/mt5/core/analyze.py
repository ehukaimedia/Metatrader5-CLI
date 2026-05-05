"""
analyze.py — Top-down multi-timeframe analysis and price structure for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()`` indirectly via the rates module.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from metatrader5_cli.mt5.core import rates as rates_module


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


# ---------------------------------------------------------------------------
# structure — N-bar pivot detection (spec §6.5)
# ---------------------------------------------------------------------------

def structure(symbol: str, timeframe: str, bars: int = 200, pivot_n: int = 5) -> dict:
    """Return swing highs/lows, support, and resistance via N-bar pivot detection.

    A bar at index i is a swing high if its high is the highest of the pivot_n
    bars before AND after it; swing low symmetrically.  support = highest
    swing low below current price; resistance = lowest swing high above it.
    """
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result

    df = pd.DataFrame(result["data"])
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    times = df["time"].tolist()
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(pivot_n, n - pivot_n):
        window_h = highs[i - pivot_n:i] + highs[i + 1:i + pivot_n + 1]
        if highs[i] > max(window_h):
            swing_highs.append({"time": times[i], "price": highs[i]})

        window_l = lows[i - pivot_n:i] + lows[i + 1:i + pivot_n + 1]
        if lows[i] < min(window_l):
            swing_lows.append({"time": times[i], "price": lows[i]})

    current_price = float(df["close"].iloc[-1])

    resistance_candidates = [s["price"] for s in swing_highs if s["price"] > current_price]
    support_candidates = [s["price"] for s in swing_lows if s["price"] < current_price]

    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "pivot_n": pivot_n,
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "support": max(support_candidates) if support_candidates else None,
            "resistance": min(resistance_candidates) if resistance_candidates else None,
            "current_price": current_price,
        },
    }


# ---------------------------------------------------------------------------
# _classify_tf — single-timeframe market-structure classification
# ---------------------------------------------------------------------------

def _classify_tf(symbol: str, timeframe: str, bars: int) -> dict | None:
    """Return TF market-structure classification or None on any data error."""
    result = structure(symbol, timeframe, bars=bars)
    if not result["ok"]:
        return None
    data = result["data"]
    swing_highs = data["swing_highs"]
    swing_lows = data["swing_lows"]

    structure_state = "range"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        prev_high, last_high = swing_highs[-2]["price"], swing_highs[-1]["price"]
        prev_low, last_low = swing_lows[-2]["price"], swing_lows[-1]["price"]
        if last_high > prev_high and last_low > prev_low:
            structure_state = "HH_HL"
        elif last_high < prev_high and last_low < prev_low:
            structure_state = "LH_LL"
        else:
            structure_state = "mixed"

    if structure_state == "HH_HL":
        trend = "bullish"
    elif structure_state == "LH_LL":
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "timeframe": timeframe,
        "trend": trend,
        "structure": structure_state,
        "current_price": data["current_price"],
        "support": data["support"],
        "resistance": data["resistance"],
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


# ---------------------------------------------------------------------------
# topdown
# ---------------------------------------------------------------------------

def topdown(symbol: str, timeframes: list[str], bars: int = 200) -> dict:
    """Multi-timeframe market-structure summary (spec §6.5).

    For each TF: detect swing highs/lows and classify HH/HL or LH/LL structure.
    Aggregates bias from majority across TFs. confluence_score = fraction
    of TFs agreeing with the majority bias.
    """
    tf_dict: dict[str, dict] = {}
    for tf in timeframes:
        classified = _classify_tf(symbol, tf, bars)
        if classified is not None:
            tf_dict[tf] = {k: v for k, v in classified.items() if k != "timeframe"}

    if not tf_dict:
        return _fail("MT5_NO_DATA", f"Could not compute market structure for any timeframe for {symbol!r}.")

    counts: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
    for r in tf_dict.values():
        counts[r["trend"]] += 1

    bias = max(counts, key=lambda k: counts[k])
    confluence_score = counts[bias] / len(tf_dict)

    notes = []
    for tf, r in tf_dict.items():
        notes.append(
            f"{tf}: {r['trend']} structure ({r['structure']}); "
            f"support={r['support']}, resistance={r['resistance']}"
        )

    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "bias": bias,
            "confluence_score": confluence_score,
            "timeframes": tf_dict,
            "notes": notes,
        },
    }


# ---------------------------------------------------------------------------
# bias
# ---------------------------------------------------------------------------

_DEFAULT_TIMEFRAMES = ["D1", "H4", "H1"]


def bias(symbol: str) -> dict:
    """Quick directional bias using default TFs D1, H4, H1 (spec §6.5)."""
    result = topdown(symbol, _DEFAULT_TIMEFRAMES)
    if not result["ok"]:
        return result
    data = result["data"]
    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "bias": data["bias"],
            "confidence": data["confluence_score"],
            "reasoning": "\n".join(data["notes"]),
        },
    }
