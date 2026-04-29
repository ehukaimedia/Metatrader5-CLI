"""
indicator.py — Technical indicators via pandas-ta for the MT5 CLI.

All indicator functions delegate rate fetching to ``rates.fetch()`` (spec §6.4).
This module never imports MetaTrader5 directly.
"""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta  # noqa: F401  (imported for its DataFrame accessor)

from cli_anything.mt5.core import rates as rates_module


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _values_with_time(df: pd.DataFrame, col: str, field: str) -> list[dict]:
    """Return [{time, <field>}] for *col*, dropping NaN rows."""
    return [
        {"time": row["time"], field: float(row[col])}
        for _, row in df.iterrows()
        if not pd.isna(row[col])
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ema(symbol: str, timeframe: str, period: int, bars: int = 100) -> dict:
    """Exponential Moving Average (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.ema(length=period, append=True)
    col = f"EMA_{period}"
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe, "period": period,
            "values": _values_with_time(df, col, "ema"),
        },
    }


def sma(symbol: str, timeframe: str, period: int, bars: int = 100) -> dict:
    """Simple Moving Average (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.sma(length=period, append=True)
    col = f"SMA_{period}"
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe, "period": period,
            "values": _values_with_time(df, col, "sma"),
        },
    }


def rsi(symbol: str, timeframe: str, period: int, bars: int = 100) -> dict:
    """Relative Strength Index (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.rsi(length=period, append=True)
    col = f"RSI_{period}"
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe, "period": period,
            "values": _values_with_time(df, col, "rsi"),
        },
    }


def macd(
    symbol: str,
    timeframe: str,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    bars: int = 200,
) -> dict:
    """MACD — Moving Average Convergence/Divergence (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.macd(fast=fast, slow=slow, signal=signal, append=True)
    macd_col = f"MACD_{fast}_{slow}_{signal}"
    hist_col = f"MACDh_{fast}_{slow}_{signal}"
    sig_col  = f"MACDs_{fast}_{slow}_{signal}"
    rows = [
        {
            "time":      row["time"],
            "macd":      float(row[macd_col]),
            "signal":    float(row[sig_col]),
            "histogram": float(row[hist_col]),
        }
        for _, row in df.iterrows()
        if not pd.isna(row.get(macd_col))
    ]
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe,
            "fast": fast, "slow": slow, "signal": signal,
            "values": rows,
        },
    }


def bb(
    symbol: str,
    timeframe: str,
    period: int = 20,
    std: float = 2.0,
    bars: int = 100,
) -> dict:
    """Bollinger Bands (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.bbands(length=period, std=std, append=True)
    lower_col = next((c for c in df.columns if c.startswith("BBL_")), None)
    mid_col   = next((c for c in df.columns if c.startswith("BBM_")), None)
    upper_col = next((c for c in df.columns if c.startswith("BBU_")), None)
    if lower_col is None:
        return _fail("INDICATOR_ERROR", "Bollinger Bands computation returned no data.")
    rows = [
        {
            "time":  row["time"],
            "upper": float(row[upper_col]),
            "mid":   float(row[mid_col]),
            "lower": float(row[lower_col]),
        }
        for _, row in df.iterrows()
        if not pd.isna(row.get(lower_col))
    ]
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe,
            "period": period, "std": std,
            "values": rows,
        },
    }


def atr(symbol: str, timeframe: str, period: int = 14, bars: int = 100) -> dict:
    """Average True Range (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    atr_series = df.ta.atr(
        high=df["high"], low=df["low"], close=df["close"], length=period
    )
    rows = [
        {"time": df.iloc[i]["time"], "atr": float(v)}
        for i, v in enumerate(atr_series)
        if not pd.isna(v)
    ]
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe,
            "period": period, "values": rows,
        },
    }


def list_available() -> dict:
    """Return the static catalogue of supported indicators (spec §6.4)."""
    return {
        "ok": True,
        "data": [
            {"name": "ema",  "description": "Exponential Moving Average",             "params": ["period", "bars"]},
            {"name": "sma",  "description": "Simple Moving Average",                  "params": ["period", "bars"]},
            {"name": "rsi",  "description": "Relative Strength Index",                "params": ["period", "bars"]},
            {"name": "macd", "description": "MACD (Moving Average Convergence/Divergence)", "params": ["fast", "slow", "signal", "bars"]},
            {"name": "bb",   "description": "Bollinger Bands",                        "params": ["period", "std", "bars"]},
            {"name": "atr",  "description": "Average True Range",                     "params": ["period", "bars"]},
        ],
    }
