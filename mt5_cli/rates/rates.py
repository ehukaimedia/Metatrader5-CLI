"""
rates.py — OHLCV bar and tick data primitives for mt5_cli.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_call()`` / ``ensure_symbol()`` via the bridge.

Pattern-ported from archive/legacy-mt5/core/rates.py with absolute imports
from mt5_cli.bridge and ok()/fail() envelopes from mt5_cli.reports.

Deliberate divergences from legacy:
- ``_bar_to_dict`` and ``_tick_to_dict`` use subscript access (``row["time"]``)
  because ``copy_rates_*`` and ``copy_ticks_*`` return numpy structured arrays
  whose rows are ``numpy.void`` objects — subscript access only. Attribute
  access (``row.time``) raises ``AttributeError`` on real MT5 data.
  Distinct from ``copy_deals_*`` / ``market_book_get`` which return NamedTuples
  and do support attribute access (see history.py, market.py).
- Local ``_fail`` helper dropped; replaced with ``fail()`` from
  mt5_cli.reports (the new envelope API).
- ``_TIMEFRAME_MAP`` values come from bridge re-exports (TIMEFRAME_M1 …
  TIMEFRAME_MN1) rather than hardcoded MT5 wire values — single-source-of-truth.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mt5_cli.bridge import (
    mt5_call, ensure_symbol,
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30,
    TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1, TIMEFRAME_W1, TIMEFRAME_MN1,
    COPY_TICKS_ALL,
)
from mt5_cli.reports import ok, fail


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TIMEFRAME_MAP: dict[str, object] = {
    "M1":  TIMEFRAME_M1,
    "M5":  TIMEFRAME_M5,
    "M15": TIMEFRAME_M15,
    "M30": TIMEFRAME_M30,
    "H1":  TIMEFRAME_H1,
    "H4":  TIMEFRAME_H4,
    "D1":  TIMEFRAME_D1,
    "W1":  TIMEFRAME_W1,
    "MN1": TIMEFRAME_MN1,
}


def _resolve_tf(timeframe: str):
    """Return ``(tf_constant, None)`` or ``(None, fail_envelope)``."""
    tf = _TIMEFRAME_MAP.get(
        timeframe.upper() if isinstance(timeframe, str) else timeframe
    )
    if tf is None:
        valid = ", ".join(_TIMEFRAME_MAP)
        return None, fail(
            "MT5_INVALID_TIMEFRAME",
            f"Unknown timeframe {timeframe!r}. Valid: {valid}.",
        )
    return tf, None


def _epoch_to_iso(epoch: int | float) -> str:
    """Convert a Unix-epoch integer to an ISO-8601 UTC string."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _bar_to_dict(row) -> dict:
    """Normalise an OHLCV bar to a plain dict with an ISO-8601 timestamp.

    Uses subscript access (``row["time"]``) because ``copy_rates_*`` returns
    numpy structured arrays whose rows are ``numpy.void`` objects — subscript
    access only. Attribute access raises ``AttributeError`` on real MT5 data.
    """
    return {
        "time":        _epoch_to_iso(row["time"]),
        "open":        float(row["open"]),
        "high":        float(row["high"]),
        "low":         float(row["low"]),
        "close":       float(row["close"]),
        "tick_volume": int(row["tick_volume"]),
    }


def _tick_to_dict(row) -> dict:
    """Normalise a tick to a plain dict with an ISO-8601 timestamp.

    Uses subscript access (``row["time"]``) because ``copy_ticks_*`` returns
    numpy structured arrays whose rows are ``numpy.void`` objects — subscript
    access only. Attribute access raises ``AttributeError`` on real MT5 data.
    """
    return {
        "time":   _epoch_to_iso(row["time"]),
        "bid":    float(row["bid"]),
        "ask":    float(row["ask"]),
        "last":   float(row["last"]),
        "volume": int(row["volume"]),
        "flags":  int(row["flags"]),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch(symbol: str, timeframe: str, bars: int) -> dict:
    """Return the last *bars* OHLCV bars for *symbol* / *timeframe*.

    Calls ``copy_rates_from_pos(symbol, tf, 0, bars)`` — start_pos=0 means
    the most-recent bar is first in the result set (which may be the still-open
    current bar).  Use ``latest()`` when you need the last *closed* bar only.
    """
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = mt5_call("copy_rates_from_pos", symbol, tf, 0, bars)
    if raw is None or len(raw) == 0:
        return fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe}.")
    return ok([_bar_to_dict(r) for r in raw])


def latest(symbol: str, timeframe: str) -> dict:
    """Return the most-recently *closed* bar for *symbol* / *timeframe*.

    Uses ``start_pos=1`` to skip the live forming bar (the current open bar at
    position 0) and retrieve the last fully-closed bar instead.
    """
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = mt5_call("copy_rates_from_pos", symbol, tf, 1, 1)
    if raw is None or len(raw) == 0:
        return fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe}.")
    return ok(_bar_to_dict(raw[0]))


def range(symbol: str, timeframe: str, date_from: datetime, date_to: datetime) -> dict:  # noqa: A001
    """Return all OHLCV bars in [*date_from*, *date_to*] for *symbol* / *timeframe*.

    *date_from* and *date_to* must be ``datetime`` objects (UTC).
    CLI/MCP coerces user strings before this layer.
    """
    tf, err = _resolve_tf(timeframe)
    if err:
        return err
    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = mt5_call("copy_rates_range", symbol, tf, date_from, date_to)
    if raw is None or len(raw) == 0:
        return fail("MT5_NO_DATA", f"No rate data for {symbol!r} / {timeframe} in range.")
    return ok([_bar_to_dict(r) for r in raw])


def ticks(symbol: str, bars: int) -> dict:
    """Return the last *bars* ticks using a 24-hour lookback window.

    Requests ``bars * 10`` ticks to survive sparse periods, then slices the
    last *bars* from the result.  The 24h window is sufficient for all liquid
    FX pairs and indices.
    """
    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    date_from = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    raw = mt5_call("copy_ticks_from", symbol, date_from, bars * 10, COPY_TICKS_ALL)
    if raw is None or len(raw) == 0:
        return fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
    return ok([_tick_to_dict(t) for t in raw[-bars:]])


def ticks_range(symbol: str, date_from: datetime, date_to: datetime) -> dict:
    """Return all ticks in [*date_from*, *date_to*] for *symbol*.

    *date_from* and *date_to* must be ``datetime`` objects (UTC).
    """
    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    raw = mt5_call("copy_ticks_range", symbol, date_from, date_to, COPY_TICKS_ALL)
    if raw is None or len(raw) == 0:
        return fail("MT5_NO_DATA", f"No tick data for {symbol!r} in range.")
    return ok([_tick_to_dict(t) for t in raw])
