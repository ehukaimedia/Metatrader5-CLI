"""
market.py — Market data (symbol info, ticks, search, sessions) for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cli_anything.mt5.utils import mt5_backend as bridge


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _pip_size(digits: int) -> float:
    """Return pip size for the given number of decimal digits.

    FX 5-digit (EURUSD) → 0.0001; FX 3-digit (USDJPY) → 0.01.
    Formula: 10 ** (1 - digits).
    """
    return 10 ** (1 - digits)


# ---------------------------------------------------------------------------
# Static FX session table (spec §6.2) — all times UTC wall-clock strings
# ---------------------------------------------------------------------------

_FX_SESSIONS = {
    "sydney": {"start_utc": "21:00", "end_utc": "06:00"},
    "tokyo":  {"start_utc": "00:00", "end_utc": "09:00"},
    "london": {"start_utc": "08:00", "end_utc": "17:00"},
    "ny":     {"start_utc": "13:00", "end_utc": "22:00"},
}

_INDEX_SESSIONS = {
    "sydney": {"start_utc": "21:00", "end_utc": "06:00"},
    "tokyo":  {"start_utc": "00:00", "end_utc": "09:00"},
    "london": {"start_utc": "08:00", "end_utc": "16:30"},
    "ny":     {"start_utc": "13:30", "end_utc": "20:00"},
}

_FX_MAJORS: frozenset[str] = frozenset({
    "EURUSD", "USDJPY", "GBPUSD", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "CHFJPY", "CADJPY", "AUDJPY", "NZDJPY",
    "EURCAD", "EURCHF", "EURAUD", "EURNZD", "GBPCAD", "GBPCHF", "GBPAUD",
    "GBPNZD", "AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "NZDCAD", "NZDCHF",
})
_METALS: frozenset[str] = frozenset({"XAUUSD", "XAGUSD"})
_US_INDICES: frozenset[str] = frozenset({"NAS100", "SPX500", "US30"})

_SESSIONS_TABLE: dict[str, dict] = {}
for _sym in _FX_MAJORS | _METALS:
    _SESSIONS_TABLE[_sym] = _FX_SESSIONS
for _sym in _US_INDICES:
    _SESSIONS_TABLE[_sym] = _INDEX_SESSIONS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def info(symbol: str) -> dict:
    """Return symbol specification (spec §6.2).

    Calls ``bridge.ensure_symbol`` before any MT5 query so the symbol is
    visible in MarketWatch (spec §3 contract).  Returns MT5_INVALID_SYMBOL
    if the symbol cannot be added to Market Watch.
    """
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    sym = bridge.mt5_call("symbol_info", symbol)
    if sym is None:
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} not found.")
    return {
        "ok": True,
        "data": {
            "symbol": sym.name,
            "bid": sym.bid,
            "ask": sym.ask,
            "spread": sym.spread,
            "digits": sym.digits,
            "pip_size": _pip_size(sym.digits),
            "trade_tick_value": sym.trade_tick_value,
            "volume_min": sym.volume_min,
            "volume_step": sym.volume_step,
            "volume_max": sym.volume_max,
            "swap_long": sym.swap_long,
            "swap_short": sym.swap_short,
            "filling_mode": sym.filling_mode,
            "trade_mode": sym.trade_mode,
        },
    }


def tick(symbol: str) -> dict:
    """Return the latest tick for *symbol* (spec §6.2).

    Time is converted to ISO-8601 UTC.  Calls ``bridge.ensure_symbol``
    first (spec §3 contract).  Returns MT5_INVALID_SYMBOL if the symbol
    cannot be added to Market Watch.
    """
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    t = bridge.mt5_call("symbol_info_tick", symbol)
    if t is None:
        return _fail("MT5_INVALID_SYMBOL", f"No tick data for {symbol!r}.")
    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "time": datetime.fromtimestamp(t.time, tz=timezone.utc).isoformat(),
            "bid": t.bid,
            "ask": t.ask,
            "last": t.last,
            "volume": t.volume,
        },
    }


def search(pattern: str) -> dict:
    """Return symbols matching *pattern* (spec §6.2).

    Bare terms (no ``*`` or ``,``) are auto-wrapped as ``*PATTERN*``.
    Explicit MT5 glob syntax (e.g. ``EUR*,GBP*``) is passed through as-is.
    """
    if "*" not in pattern and "," not in pattern:
        pattern = f"*{pattern}*"
    symbols = bridge.mt5_call("symbols_get", group=pattern) or []
    return {
        "ok": True,
        "data": [
            {
                "symbol": s.name,
                "description": s.description,
                "currency_base": s.currency_base,
                "currency_profit": s.currency_profit,
            }
            for s in symbols
        ],
    }


def session(symbol: str) -> dict:
    """Return current session window for *symbol* (spec §6.2).

    Uses ``symbol_info_session_trade(symbol, day_of_week, session_index=0)``
    which returns a (from_seconds, to_seconds) tuple measured from midnight.
    MT5 day-of-week: SUNDAY=0, MONDAY=1, ..., SATURDAY=6.

    Overnight sessions (e.g. 21:00→06:00) are handled correctly:
    * If current time >= from_sec → session opened today; closes_at is tomorrow.
    * If current time < to_sec   → we are in the tail of yesterday's session.
    * Otherwise                  → between sessions; next open is today.
    """
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")
    now = datetime.now(timezone.utc)
    mt5_dow = (now.weekday() + 1) % 7  # Python Mon=0→MT5 Mon=1; Sun=6→MT5 Sun=0
    result = bridge.mt5_call("symbol_info_session_trade", symbol, mt5_dow, 0)
    if result is None:
        return _fail("MT5_INVALID_SYMBOL", f"No session data for {symbol!r}.")
    from_sec, to_sec = int(result[0]), int(result[1])
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    now_secs = int((now - midnight).total_seconds())

    if to_sec > from_sec:
        # Normal same-day session (e.g. 08:00→17:00)
        opens_at = midnight + timedelta(seconds=from_sec)
        closes_at = midnight + timedelta(seconds=to_sec)
    else:
        # Overnight session (e.g. 21:00→06:00)
        if now_secs >= from_sec:
            # Opening portion: session started today, closes tomorrow
            opens_at = midnight + timedelta(seconds=from_sec)
            closes_at = midnight + timedelta(days=1, seconds=to_sec)
        elif now_secs < to_sec:
            # Closing portion: still in yesterday's session tail
            opens_at = midnight - timedelta(days=1) + timedelta(seconds=from_sec)
            closes_at = midnight + timedelta(seconds=to_sec)
        else:
            # Between sessions: next open is today
            opens_at = midnight + timedelta(seconds=from_sec)
            closes_at = midnight + timedelta(days=1, seconds=to_sec)

    return {
        "ok": True,
        "data": {
            "is_open": opens_at <= now < closes_at,
            "opens_at": opens_at.isoformat(),
            "closes_at": closes_at.isoformat(),
        },
    }


def sessions(symbol: str) -> dict:
    """Return named FX session boundaries from the static table (spec §6.2).

    Covers FX majors (28 pairs), gold (XAUUSD), silver (XAGUSD), and major
    US indices (NAS100, SPX500, US30).  Unknown symbols return an error
    envelope with code ``MT5_INVALID_SYMBOL``.
    """
    entry = _SESSIONS_TABLE.get(symbol)
    if entry is None:
        return _fail(
            "MT5_INVALID_SYMBOL",
            f"No static session table entry for {symbol!r}; query market session instead.",
        )
    return {"ok": True, "data": entry}
