"""
market.py — Market data (symbol info, ticks, search, sessions) for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from metatrader5_cli.mt5.utils import mt5_backend as bridge


def _fail(code: str, message: str, *, mt5_retcode: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": mt5_retcode}}


def _pip_size(digits: int) -> float:
    """Return pip size for the given number of decimal digits.

    FX 5-digit (EURUSD) → 0.0001; FX 3-digit (USDJPY) → 0.01.
    Formula: 10 ** (1 - digits).
    """
    return 10 ** (1 - digits)


BOOK_TYPE_NAMES = {
    1: "ask",
    2: "bid",
    3: "sell_market",
    4: "buy_market",
}


def _last_error() -> tuple[int | None, str]:
    err = bridge.mt5_call("last_error")
    if isinstance(err, tuple) and len(err) >= 2:
        message = str(err[1])
        if err[0] == 1 and message.lower() == "success":
            message = "No terminal error details; broker/symbol may not expose Depth of Market through the Python API."
        return err[0], message
    return None, str(err)


def _entry_dict(entry) -> dict:
    if hasattr(entry, "_asdict"):
        return dict(entry._asdict())
    return {
        "type": getattr(entry, "type", None),
        "price": getattr(entry, "price", None),
        "volume": getattr(entry, "volume", None),
        "volume_dbl": getattr(entry, "volume_dbl", getattr(entry, "volume_real", None)),
    }


def _normalize_book_entry(entry) -> dict:
    raw = _entry_dict(entry)
    type_id = int(raw.get("type", 0) or 0)
    volume_dbl = raw.get("volume_dbl", raw.get("volume_real", raw.get("volume")))
    return {
        "type": type_id,
        "side": BOOK_TYPE_NAMES.get(type_id, "unknown"),
        "price": float(raw.get("price")),
        "volume": int(raw.get("volume", 0) or 0),
        "volume_dbl": float(volume_dbl if volume_dbl is not None else raw.get("volume", 0) or 0),
    }


def _limited_levels(entries: list[dict], levels: int) -> list[dict]:
    if levels <= 0:
        return entries
    return entries[:levels]


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
            "point": sym.point,
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


def depth(symbol: str, levels: int = 0) -> dict:
    """Return a one-shot Depth of Market snapshot for *symbol*.

    MT5 requires a DOM subscription before ``market_book_get`` can return
    entries. This CLI command is intentionally one-shot: subscribe, read,
    release. Long-running streamers should manage their own subscription
    lifecycle outside the command process.
    """
    if levels < 0:
        return _fail("MT5_INVALID_ARGUMENT", "--levels must be zero or greater.")
    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} could not be added to Market Watch.")

    if not bridge.mt5_call("market_book_add", symbol):
        code, message = _last_error()
        return _fail(
            "MT5_MARKET_BOOK_SUBSCRIBE_FAILED",
            f"Could not subscribe to Depth of Market for {symbol!r}: {message}",
            mt5_retcode=code,
        )

    try:
        book = bridge.mt5_call("market_book_get", symbol)
        if book is None:
            code, message = _last_error()
            return _fail(
                "MT5_MARKET_BOOK_UNAVAILABLE",
                f"No Depth of Market data for {symbol!r}: {message}",
                mt5_retcode=code,
            )

        entries = [_normalize_book_entry(entry) for entry in book]
        asks = sorted(
            (entry for entry in entries if entry["side"] in {"ask", "sell_market"}),
            key=lambda entry: entry["price"],
        )
        bids = sorted(
            (entry for entry in entries if entry["side"] in {"bid", "buy_market"}),
            key=lambda entry: entry["price"],
            reverse=True,
        )
        asks = _limited_levels(asks, levels)
        bids = _limited_levels(bids, levels)
        best_ask = asks[0]["price"] if asks else None
        best_bid = bids[0]["price"] if bids else None
        spread = (best_ask - best_bid) if best_ask is not None and best_bid is not None else None
        mid = ((best_ask + best_bid) / 2) if best_ask is not None and best_bid is not None else None
        bid_volume = sum(entry["volume_dbl"] for entry in bids)
        ask_volume = sum(entry["volume_dbl"] for entry in asks)
        total_volume = bid_volume + ask_volume
        volume_imbalance = ((bid_volume - ask_volume) / total_volume) if total_volume else None
        sym = bridge.mt5_call("symbol_info", symbol)
        point = getattr(sym, "point", None) if sym is not None else None
        spread_points = (spread / point) if spread is not None and isinstance(point, (int, float)) and point else None

        return {
            "ok": True,
            "data": {
                "symbol": symbol,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "levels": levels,
                "raw_count": len(entries),
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "spread_points": spread_points,
                "mid": mid,
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "volume_imbalance": volume_imbalance,
                "raw": entries,
            },
        }
    finally:
        bridge.mt5_call("market_book_release", symbol)


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
            f"No static session table entry for {symbol!r}; use market info for broker metadata.",
        )
    return {"ok": True, "data": entry}
