"""
order.py — Order placement, modification, cancellation and fill-polling for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()`` (indirectly, via the bridge module).
"""
from __future__ import annotations

import time

from cli_anything.mt5.core import risk as risk_module
from cli_anything.mt5.utils import mt5_backend as bridge


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


_FILLING_MAP = {
    "FOK": bridge.ORDER_FILLING_FOK,
    "IOC": bridge.ORDER_FILLING_IOC,
    "RETURN": bridge.ORDER_FILLING_RETURN,
}


def _resolve_filling(symbol: str, filling_str: str) -> int:
    """Map filling string to MT5 constant.

    "auto" reads symbol_info().filling_mode bitmask (1=FOK, 2=IOC, 4=RETURN).
    Explicit "FOK"/"IOC"/"RETURN" maps directly.
    """
    upper = filling_str.upper()
    if upper in _FILLING_MAP:
        return _FILLING_MAP[upper]

    # "auto" — read symbol_info bitmask; priority: FOK > IOC > RETURN
    sym_info = bridge.mt5_call("symbol_info", symbol)
    if sym_info is None:
        return bridge.ORDER_FILLING_FOK
    filling_mode = sym_info.filling_mode
    if filling_mode & 1:
        return bridge.ORDER_FILLING_FOK
    if filling_mode & 2:
        return bridge.ORDER_FILLING_IOC
    return bridge.ORDER_FILLING_RETURN


def _finalize_order(
    result,
    symbol: str,
    side: str,
    volume: float,
    price: float,
    sl: float,
    tp: float | None,
    magic: int,
    strategy_id: str | None,
) -> dict:
    """Map order_send result to a JSON envelope (spec §6.7 output keys)."""
    if result is None:
        return _fail("MT5_ORDER_REJECTED", "order_send returned None.", mt5_retcode=None)

    retcode = result.retcode

    if retcode in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
        return {
            "ok": True,
            "data": {
                "ticket": result.order,
                "symbol": symbol,
                "type": side,
                "volume": volume,
                "price": price,
                "sl": sl,
                "tp": tp,
                "time": getattr(result, "time", None),
                "magic": magic,
                "strategy_id": strategy_id,
                "retcode": retcode,
            },
        }

    if retcode == bridge.TRADE_RETCODE_INVALID_FILL:
        sym_info = bridge.mt5_call("symbol_info", symbol)
        filling_mode = sym_info.filling_mode if sym_info is not None else None
        msg = (
            f"Invalid filling mode (retcode 10030). "
            f"Symbol filling_mode bitmask: {filling_mode}"
        )
        return _fail("MT5_ORDER_REJECTED", msg, mt5_retcode=retcode)

    comment = getattr(result, "comment", "Order rejected by broker.")
    return _fail("MT5_ORDER_REJECTED", str(comment), mt5_retcode=retcode)


# ---------------------------------------------------------------------------
# place_market
# ---------------------------------------------------------------------------

def place_market(
    symbol: str,
    side: str,
    *,
    volume: float | None = None,
    risk_pct: float | None = None,
    sl: float,
    tp: float | None = None,
    comment: str | None = None,
    strategy_id: str | None = None,
    magic: int | None = None,
    deviation: int = 20,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a market order (TRADE_ACTION_DEAL)."""
    if (volume is None) == (risk_pct is None):
        return _fail("MT5_INVALID_PARAMS", "Provide exactly one of --volume or --risk-pct.")

    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    tick = bridge.mt5_call("symbol_info_tick", symbol)
    if tick is None:
        return _fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
    entry_price = tick.ask if side.lower() == "buy" else tick.bid

    if risk_pct is not None:
        vol = risk_module.compute_volume_from_risk_pct(symbol, risk_pct, entry_price, sl, cfg)
        if isinstance(vol, dict):
            return vol
        volume = vol

    risk_result = risk_module.check_order(
        symbol, side, volume, sl, strategy_id, cfg, is_live_intent=is_live_intent
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else risk_module.resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_filling(symbol, filling)
    order_type = bridge.ORDER_TYPE_BUY if side.lower() == "buy" else bridge.ORDER_TYPE_SELL

    request = {
        "action": bridge.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "deviation": deviation,
        "magic": resolved_magic,
        "comment": comment or strategy_id or "",
        "type_time": bridge.ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }

    result = bridge.mt5_call("order_send", request)
    return _finalize_order(result, symbol, side, float(volume), entry_price, sl, tp, resolved_magic, strategy_id)


# ---------------------------------------------------------------------------
# place_limit
# ---------------------------------------------------------------------------

def place_limit(
    symbol: str,
    side: str,
    price: float,
    *,
    volume: float | None = None,
    risk_pct: float | None = None,
    sl: float,
    tp: float | None = None,
    expiry=None,
    strategy_id: str | None = None,
    magic: int | None = None,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a limit pending order (TRADE_ACTION_PENDING, BUY_LIMIT / SELL_LIMIT)."""
    if (volume is None) == (risk_pct is None):
        return _fail("MT5_INVALID_PARAMS", "Provide exactly one of --volume or --risk-pct.")

    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    if risk_pct is not None:
        vol = risk_module.compute_volume_from_risk_pct(symbol, risk_pct, price, sl, cfg)
        if isinstance(vol, dict):
            return vol
        volume = vol

    risk_result = risk_module.check_order(
        symbol, side, volume, sl, strategy_id, cfg, is_live_intent=is_live_intent
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else risk_module.resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_filling(symbol, filling)
    order_type = (
        bridge.ORDER_TYPE_BUY_LIMIT if side.lower() == "buy" else bridge.ORDER_TYPE_SELL_LIMIT
    )

    request = {
        "action": bridge.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": bridge.ORDER_TIME_SPECIFIED if expiry else bridge.ORDER_TIME_GTC,
        "expiration": expiry if expiry else 0,
        "type_filling": resolved_filling,
    }

    result = bridge.mt5_call("order_send", request)
    return _finalize_order(result, symbol, side, float(volume), price, sl, tp, resolved_magic, strategy_id)


# ---------------------------------------------------------------------------
# place_stop
# ---------------------------------------------------------------------------

def place_stop(
    symbol: str,
    side: str,
    price: float,
    *,
    volume: float | None = None,
    risk_pct: float | None = None,
    sl: float,
    tp: float | None = None,
    expiry=None,
    strategy_id: str | None = None,
    magic: int | None = None,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a stop pending order (TRADE_ACTION_PENDING, BUY_STOP / SELL_STOP)."""
    if (volume is None) == (risk_pct is None):
        return _fail("MT5_INVALID_PARAMS", "Provide exactly one of --volume or --risk-pct.")

    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    if risk_pct is not None:
        vol = risk_module.compute_volume_from_risk_pct(symbol, risk_pct, price, sl, cfg)
        if isinstance(vol, dict):
            return vol
        volume = vol

    risk_result = risk_module.check_order(
        symbol, side, volume, sl, strategy_id, cfg, is_live_intent=is_live_intent
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else risk_module.resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_filling(symbol, filling)
    order_type = (
        bridge.ORDER_TYPE_BUY_STOP if side.lower() == "buy" else bridge.ORDER_TYPE_SELL_STOP
    )

    request = {
        "action": bridge.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": bridge.ORDER_TIME_SPECIFIED if expiry else bridge.ORDER_TIME_GTC,
        "expiration": expiry if expiry else 0,
        "type_filling": resolved_filling,
    }

    result = bridge.mt5_call("order_send", request)
    return _finalize_order(result, symbol, side, float(volume), price, sl, tp, resolved_magic, strategy_id)


# ---------------------------------------------------------------------------
# modify
# ---------------------------------------------------------------------------

def modify(ticket: int, *, sl: float | None = None, tp: float | None = None, price: float | None = None) -> dict:
    """Modify a position (SLTP) or pending order (MODIFY).

    Auto-detects ticket type: positions_get first, then orders_get.
    """
    positions = bridge.mt5_call("positions_get", ticket=ticket)
    if positions:
        pos = positions[0]
        request = {
            "action": bridge.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
        }
        result = bridge.mt5_call("order_send", request)
        if result is None:
            return _fail("MT5_ORDER_REJECTED", "order_send returned None for SLTP modify.")
        if result.retcode in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
            return {"ok": True, "data": {"ticket": ticket, "action": "SLTP"}}
        return _fail("MT5_ORDER_REJECTED", str(getattr(result, "comment", "")), mt5_retcode=result.retcode)

    orders = bridge.mt5_call("orders_get", ticket=ticket)
    if orders:
        ord_ = orders[0]
        request = {
            "action": bridge.TRADE_ACTION_MODIFY,
            "order": ticket,
            "symbol": ord_.symbol,
            "price": price if price is not None else ord_.price_open,
            "sl": sl if sl is not None else ord_.sl,
            "tp": tp if tp is not None else ord_.tp,
            "type_time": ord_.type_time,
            "expiration": ord_.time_expiration,
        }
        result = bridge.mt5_call("order_send", request)
        if result is None:
            return _fail("MT5_ORDER_REJECTED", "order_send returned None for MODIFY.")
        if result.retcode in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
            return {"ok": True, "data": {"ticket": ticket, "action": "MODIFY"}}
        return _fail("MT5_ORDER_REJECTED", str(getattr(result, "comment", "")), mt5_retcode=result.retcode)

    return _fail("MT5_TICKET_NOT_FOUND", f"Ticket {ticket} not found in positions or pending orders.")


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

def cancel_all_pending(symbol: str | None = None, *, is_live_intent: bool) -> dict:
    """Cancel all pending orders, optionally scoped to one symbol.

    Continues on per-ticket failure (spec §7.4 pattern).  Returns a list
    of per-ticket outcome dicts — callers must inspect each entry.
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    if symbol:
        orders = bridge.mt5_call("orders_get", symbol=symbol)
    else:
        orders = bridge.mt5_call("orders_get")

    if orders is None:
        return _fail("MT5_NO_DATA", "orders_get returned None.")

    results = []
    for o in orders:
        outcome = cancel(o.ticket, is_live_intent=is_live_intent)
        entry: dict = {"ticket": o.ticket}
        if outcome["ok"]:
            entry["result"] = "canceled"
        else:
            entry["result"] = "error"
            entry["error"] = outcome["error"]
        results.append(entry)

    return {"ok": True, "data": results}


def cancel(ticket: int, *, is_live_intent: bool) -> dict:
    """Cancel a pending order (TRADE_ACTION_REMOVE)."""
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    orders = bridge.mt5_call("orders_get", ticket=ticket)
    if not orders:
        return _fail("MT5_TICKET_NOT_FOUND", f"Pending order {ticket} not found.")

    ord_ = orders[0]
    request = {
        "action": bridge.TRADE_ACTION_REMOVE,
        "order": ticket,
        "symbol": ord_.symbol,
    }
    result = bridge.mt5_call("order_send", request)
    if result is None:
        return _fail("MT5_ORDER_REJECTED", "order_send returned None for REMOVE.")
    if result.retcode in (bridge.TRADE_RETCODE_DONE, bridge.TRADE_RETCODE_PLACED):
        return {"ok": True, "data": {"ticket": ticket, "cancelled": True}}
    return _fail("MT5_ORDER_REJECTED", str(getattr(result, "comment", "")), mt5_retcode=result.retcode)


# ---------------------------------------------------------------------------
# poll_fill
# ---------------------------------------------------------------------------

def poll_fill(ticket: int, timeout_ms: int = 5000) -> dict:
    """Poll until ticket appears as a position or timeout expires.

    Spec §6.7: returns ``{"filled": False}`` on timeout — caller decides to cancel.
    Returns ``{"filled": False}`` also if the ticket vanishes from pending orders
    (rejected/cancelled by broker).
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        positions = bridge.mt5_call("positions_get", ticket=ticket)
        if positions:
            return {"ok": True, "data": {"filled": True, "ticket": ticket}}
        pending = bridge.mt5_call("orders_get", ticket=ticket)
        if not pending:
            return {"ok": True, "data": {"filled": False, "ticket": ticket}}
        time.sleep(0.1)

    return {"ok": True, "data": {"filled": False, "ticket": ticket}}


# ---------------------------------------------------------------------------
# dryrun
# ---------------------------------------------------------------------------

def dryrun(
    symbol: str,
    side: str,
    *,
    volume: float | None = None,
    risk_pct: float | None = None,
    sl: float,
    tp: float | None = None,
    strategy_id: str | None = None,
    magic: int | None = None,
    deviation: int = 20,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Validate an order without placing it (spec §7.3).

    Runs the full risk envelope then calls ``order_check`` (NOT ``order_send``).
    Returns margin, margin_free, margin_level, profit, retcode.
    """
    if (volume is None) == (risk_pct is None):
        return _fail("MT5_INVALID_PARAMS", "Provide exactly one of --volume or --risk-pct.")

    if not bridge.ensure_symbol(symbol):
        return _fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    tick = bridge.mt5_call("symbol_info_tick", symbol)
    if tick is None:
        return _fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
    entry_price = tick.ask if side.lower() == "buy" else tick.bid

    if risk_pct is not None:
        vol = risk_module.compute_volume_from_risk_pct(symbol, risk_pct, entry_price, sl, cfg)
        if isinstance(vol, dict):
            return vol
        volume = vol

    risk_result = risk_module.check_order(
        symbol, side, volume, sl, strategy_id, cfg,
        is_live_intent=is_live_intent,
        consume_rate_limit=False,
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else risk_module.resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_filling(symbol, filling)
    order_type = bridge.ORDER_TYPE_BUY if side.lower() == "buy" else bridge.ORDER_TYPE_SELL

    request = {
        "action": bridge.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "deviation": deviation,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": bridge.ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }

    result = bridge.mt5_call("order_check", request)
    if result is None:
        return _fail("MT5_ORDER_REJECTED", "order_check returned None.")

    return {
        "ok": True,
        "data": {
            "dry_run": True,
            "symbol": symbol,
            "side": side,
            "volume": float(volume),
            "sl": sl,
            "tp": tp,
            "margin": getattr(result, "margin", None),
            "margin_free": getattr(result, "margin_free", None),
            "margin_level": getattr(result, "margin_level", None),
            "profit": getattr(result, "profit", None),
            "retcode": getattr(result, "retcode", None),
        },
    }
