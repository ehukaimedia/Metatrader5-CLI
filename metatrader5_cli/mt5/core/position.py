"""
position.py — Open position management for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()`` (indirectly, via the bridge module).
"""
from __future__ import annotations

from metatrader5_cli.mt5.utils import mt5_backend as bridge


def _fail(code: str, message: str, *, mt5_retcode: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": mt5_retcode}}


def _live_gate_check(is_live_intent: bool) -> dict | None:
    """Return an error dict if live-gate blocks the trade, or None if clear."""
    account_info = bridge.mt5_call("account_info")
    if account_info is None:
        return _fail("RISK_INVALID_INPUT", "account_info unavailable — MT5 may be disconnected.")
    if not is_live_intent and account_info.trade_mode == bridge.ACCOUNT_TRADE_MODE_REAL:
        return _fail(
            "RISK_LIVE_GATE_BLOCKED",
            "This is a live (real-money) account.  Pass --live to confirm intentional live trading.",
        )
    return None


def _pos_to_dict(pos) -> dict:
    return {
        "ticket": pos.ticket,
        "symbol": pos.symbol,
        "type": "buy" if pos.type == 0 else "sell",
        "volume": pos.volume,
        "open_price": pos.price_open,
        "sl": pos.sl,
        "tp": pos.tp,
        "profit": pos.profit,
        "swap": pos.swap,
    }


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def list(symbol: str | None = None) -> dict:
    """Return all open positions, optionally filtered by symbol."""
    if symbol:
        positions = bridge.mt5_call("positions_get", symbol=symbol)
    else:
        positions = bridge.mt5_call("positions_get")
    if positions is None:
        return _fail("MT5_NO_DATA", "positions_get returned None.")
    return {"ok": True, "data": [_pos_to_dict(p) for p in positions]}


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def show(ticket: int) -> dict:
    """Return the detail dict for a single open position."""
    positions = bridge.mt5_call("positions_get", ticket=ticket)
    if not positions:
        return _fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")
    return {"ok": True, "data": _pos_to_dict(positions[0])}


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

def close(ticket: int, volume: float | None = None, *, is_live_intent: bool) -> dict:
    """Close a position fully or partially (spec §3: opposite-side DEAL with position=ticket)."""
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    positions = bridge.mt5_call("positions_get", ticket=ticket)
    if not positions:
        return _fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    close_volume = volume if volume is not None else pos.volume
    close_type = bridge.ORDER_TYPE_SELL if pos.type == 0 else bridge.ORDER_TYPE_BUY

    tick = bridge.mt5_call("symbol_info_tick", pos.symbol)
    if tick is None:
        return _fail("MT5_NO_DATA", f"No tick data for {pos.symbol!r}.")
    price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action": bridge.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(close_volume),
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": f"close#{ticket}",
        "type_time": bridge.ORDER_TIME_GTC,
        "type_filling": bridge.ORDER_FILLING_FOK,
    }

    result = bridge.mt5_call("order_send", request)
    if result is None:
        return _fail("MT5_ORDER_REJECTED", "order_send returned None.")

    retcode = result.retcode
    if retcode not in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
        return _fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "Position close rejected.")),
            mt5_retcode=retcode,
        )

    return {
        "ok": True,
        "data": {
            "ticket": ticket,
            "result": "closed",
            "profit": pos.profit,
        },
    }


# ---------------------------------------------------------------------------
# close_all
# ---------------------------------------------------------------------------

def close_all(symbol: str | None = None, *, is_live_intent: bool) -> dict:
    """Close all open positions, optionally restricted to one symbol.

    Continues on per-ticket failure (spec §7.4 pattern).  Returns a list
    of per-ticket outcome dicts — callers must inspect each entry.
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    if symbol:
        positions = bridge.mt5_call("positions_get", symbol=symbol)
    else:
        positions = bridge.mt5_call("positions_get")

    if positions is None:
        return _fail("MT5_NO_DATA", "positions_get returned None.")

    results = []
    for pos in positions:
        outcome = close(pos.ticket, is_live_intent=is_live_intent)
        entry: dict = {"ticket": pos.ticket}
        if outcome["ok"]:
            entry["result"] = "closed"
            entry["profit"] = outcome["data"]["profit"]
        else:
            entry["result"] = "error"
            entry["error"] = outcome["error"]
        results.append(entry)

    return {"ok": True, "data": results}


# ---------------------------------------------------------------------------
# move_sl
# ---------------------------------------------------------------------------

def move_sl(ticket: int, sl: float, *, is_live_intent: bool) -> dict:
    """Move the stop-loss of an open position to ``sl`` (TRADE_ACTION_SLTP)."""
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    positions = bridge.mt5_call("positions_get", ticket=ticket)
    if not positions:
        return _fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    request = {
        "action": bridge.TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": sl,
        "tp": pos.tp,
    }
    result = bridge.mt5_call("order_send", request)
    if result is None:
        return _fail("MT5_ORDER_REJECTED", "order_send returned None.")

    retcode = result.retcode
    if retcode not in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
        return _fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "SL move rejected.")),
            mt5_retcode=retcode,
        )

    return {"ok": True, "data": {"ticket": ticket, "result": "sl_moved"}}


# ---------------------------------------------------------------------------
# breakeven
# ---------------------------------------------------------------------------

def breakeven(ticket: int, buffer_points: int = 0, *, is_live_intent: bool) -> dict:
    """Move SL to the open price ± buffer_points × symbol.point (spec §6.8).

    For BUY positions:  new_sl = open_price + buffer_points * point  (in favour)
    For SELL positions: new_sl = open_price - buffer_points * point  (in favour)
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    positions = bridge.mt5_call("positions_get", ticket=ticket)
    if not positions:
        return _fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    sym_info = bridge.mt5_call("symbol_info", pos.symbol)
    if sym_info is None:
        return _fail("MT5_NO_DATA", f"No symbol_info for {pos.symbol!r}.")

    point = sym_info.point
    open_price = pos.price_open

    if pos.type == 0:  # BUY
        new_sl = open_price + buffer_points * point
    else:              # SELL
        new_sl = open_price - buffer_points * point

    outcome = move_sl(ticket, new_sl, is_live_intent=is_live_intent)
    if not outcome["ok"]:
        return outcome

    return {
        "ok": True,
        "data": {
            "ticket": ticket,
            "result": "breakeven_set",
            "sl_set_to": new_sl,
        },
    }
