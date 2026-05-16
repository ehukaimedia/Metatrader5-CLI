"""
rates.py — OHLCV bar and tick data for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from metatrader5_cli.mt5.utils import mt5_backend as bridge


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


_TIMEFRAME_MAP: dict[str, object] = {
    "M1":  bridge.TIMEFRAME_M1,
    "M5":  bridge.TIMEFRAME_M5,
    "M15": bridge.TIMEFRAME_M15,
    "M30": bridge.TIMEFRAME_M30,
    "H1":  bridge.TIMEFRAME_H1,
    "H4":  bridge.TIMEFRAME_H4,
    "D1":  bridge.TIMEFRAME_D1,
    "W1":  bridge.TIMEFRAME_W1,
    "MN1": bridge.TIMEFRAME_MN1,
}


def _resolve_tf(timeframe: str):
    """Return (tf_constant, None) or (None, error_dict)."""
    tf = _TIMEFRAME_MAP.get(timeframe.upper() if isinstance(timeframe, str) else timeframe)
    if tf is None:
        valid = ", ".join(_TIMEFRAME_MAP)
        return None, _fail("MT5_INVALID_TIMEFRAME", f"Unknown timeframe {timeframe!r}. Valid: {valid}.")
    return tf, None


def _bar_to_dict(row) -> dict:
    return {
        "time":        datetime.fromtimestamp(row["time"], tz=timezone.utc).isoformat(),
        "open":        float(row["open"]),
        "high":        float(row["high"]),
        "low":         float(row["low"]),
        "close":       float(row["close"]),
        "tick_volume": int(row["tick_volume"]),
    }


def _tick_to_dict(row) -> dict:
    return {
        "time":   datetime.fromtimestamp(row["time"], tz=timezone.utc).isoformat(),
        "bid":    float(row["bid"]),
        "ask":    float(row["ask"]),
        "last":   float(row["last"]),
        "volume": int(row["volume"]),
        "flags":  int(row["flags"]),
    }


def fetch(symbol: str, timeframe: str, bars: int) -> dict:
    """Return the last *bars* OHLCV bars for *symbol* / *timeframe* (spec §6.3)."""
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = bridge.mt5_call("copy_rates_from_pos", symbol, tf, 0, bars)
    if raw is None or len(raw) == 0:
        return _fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe}.")
    return {"ok": True, "data": [_bar_to_dict(r) for r in raw]}


def latest(symbol: str, timeframe: str) -> dict:
    """Return the most-recently *closed* bar for *symbol* / *timeframe* (spec §6.3).

    Uses ``start_pos=1`` to skip the live forming bar.
    """
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = bridge.mt5_call("copy_rates_from_pos", symbol, tf, 1, 1)
    if raw is None or len(raw) == 0:
        return _fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe}.")
    return {"ok": True, "data": _bar_to_dict(raw[0])}


def range(symbol: str, timeframe: str, date_from: datetime, date_to: datetime) -> dict:  # noqa: A001
    """Return all OHLCV bars in [*date_from*, *date_to*] for *symbol* / *timeframe*."""
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = bridge.mt5_call("copy_rates_range", symbol, tf, date_from, date_to)
    if raw is None or len(raw) == 0:
        return _fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe} in range.")
    return {"ok": True, "data": [_bar_to_dict(r) for r in raw]}


def ticks(symbol: str, bars: int) -> dict:
    """Return the last *bars* ticks using a 24-hour lookback window (spec §6.3).

    Requests ``bars * 10`` ticks to survive sparse periods, then slices the
    last *bars* from the result.
    """
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    date_from = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    raw = bridge.mt5_call("copy_ticks_from", symbol, date_from, bars * 10, bridge.COPY_TICKS_ALL)
    if raw is None or len(raw) == 0:
        return _fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
    return {"ok": True, "data": [_tick_to_dict(t) for t in raw[-bars:]]}


def ticks_range(symbol: str, date_from: datetime, date_to: datetime) -> dict:
    """Return all ticks in [*date_from*, *date_to*] for *symbol*."""
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = bridge.mt5_call("copy_ticks_range", symbol, date_from, date_to, bridge.COPY_TICKS_ALL)
    if raw is None or len(raw) == 0:
        return _fail("MT5_NO_DATA", f"No tick data for {symbol!r} in range.")
    return {"ok": True, "data": [_tick_to_dict(t) for t in raw]}
