"""
analyze.py — Top-down multi-timeframe analysis and price structure for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()`` (indirectly, via rates and indicator modules).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from metatrader5_cli.mt5.core import indicator as indicator_module
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
# _classify_tf — single-timeframe trend classification
# ---------------------------------------------------------------------------

def _classify_tf(symbol: str, timeframe: str, bars: int) -> dict | None:
    """Return TF classification dict or None on any data error."""
    ema_result = indicator_module.ema(symbol, timeframe, period=20, bars=bars)
    if not ema_result["ok"]:
        return None
    rsi_result = indicator_module.rsi(symbol, timeframe, period=14, bars=bars)
    if not rsi_result["ok"]:
        return None

    ema_values = ema_result["data"]["values"]
    rsi_values = rsi_result["data"]["values"]

    if len(ema_values) < 2 or not rsi_values:
        return None

    rates_result = rates_module.fetch(symbol, timeframe, bars)
    if not rates_result["ok"]:
        return None
    last_close = float(rates_result["data"][-1]["close"])

    ema_now = ema_values[-1]["ema"]
    ema_prev = ema_values[-2]["ema"]
    ema_slope = ema_now - ema_prev
    rsi_14 = rsi_values[-1]["rsi"]

    if last_close > ema_now and ema_slope > 0:
        trend = "bullish"
    elif last_close < ema_now and ema_slope < 0:
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "timeframe": timeframe,
        "trend": trend,
        "last_close": last_close,
        "ema_20": ema_now,
        "ema_slope": ema_slope,
        "rsi_14": rsi_14,
        "price_vs_ema": "above" if last_close > ema_now else "below",
    }


# ---------------------------------------------------------------------------
# topdown
# ---------------------------------------------------------------------------

def topdown(symbol: str, timeframes: list[str], bars: int = 200) -> dict:
    """Multi-timeframe trend + momentum summary (spec §6.5).

    For each TF: fetch rates, compute EMA20 + RSI14, classify trend.
    Aggregates bias from majority across TFs.  confluence_score = fraction
    of TFs agreeing with the majority bias.
    """
    tf_dict: dict[str, dict] = {}
    for tf in timeframes:
        classified = _classify_tf(symbol, tf, bars)
        if classified is not None:
            tf_dict[tf] = {k: v for k, v in classified.items() if k != "timeframe"}

    if not tf_dict:
        return _fail("MT5_NO_DATA", f"Could not compute indicators for any timeframe for {symbol!r}.")

    counts: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
    for r in tf_dict.values():
        counts[r["trend"]] += 1

    bias = max(counts, key=lambda k: counts[k])
    confluence_score = counts[bias] / len(tf_dict)

    notes = []
    for tf, r in tf_dict.items():
        rsi = r["rsi_14"]
        rsi_note = "overbought" if rsi > 70 else "oversold" if rsi < 30 else "neutral RSI"
        notes.append(f"{tf}: {r['trend']} — price {r['price_vs_ema']} EMA20, RSI {rsi:.1f} ({rsi_note})")

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
