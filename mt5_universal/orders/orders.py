"""
orders.py — Order placement, modification, cancellation and fill-polling
for mt5_universal.

Cherry-picked from archive/legacy-mt5/core/order.py (685 LOC).
9 public functions: list_pending, place_market, place_limit, place_stop,
dryrun, cancel, cancel_all_pending, modify, poll_fill.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_universal.bridge.mt5_call()``.

Deliberate divergences from legacy:

1. risk_pct parameter dropped from place_market / place_limit / dryrun.
   compute_volume_from_risk_pct is not called in this slice; that parameter
   is handled at the CLI layer and will be wired in a later task.

2. expiry parameter dropped from place_limit. ORDER_TIME_SPECIFIED not
   needed here; all pending orders use ORDER_TIME_GTC.

3. _resolve_filling always returns ORDER_FILLING_FOK for "auto".
   Legacy read symbol_info().filling_mode bitmask. Hardcoded to FOK
   for Trading.com compatibility. Broker profile abstraction lands in Task 2.8.

4. _resolve_pending_filling for "auto" also returns ORDER_FILLING_FOK.
   Legacy returned ORDER_FILLING_RETURN for pending "auto". The plan
   spec says FOK/IOC only; no RETURN for pending. FOK hardcoded for now.

5. _finalize_order wraps mt5_retcode as fail(code, msg, data={"mt5_retcode": ...})
   instead of a top-level kwarg. Matches the new envelope API established in
   market.py (no mt5_retcode parameter on fail()).

6. check_order called with full keyword arguments (new API is keyword-only).
   Legacy passed symbol/side/volume/sl/strategy_id/cfg positionally.

7. cancel's live gate uses _live_gate_check (account_info-based check).
   place_market / place_limit / dryrun get their live gate via check_order
   Guard 2 — no double-gating.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from mt5_universal.bridge import (
    mt5_call,
    ensure_symbol,
    ORDER_FILLING_FOK,
    ORDER_FILLING_IOC,
    ORDER_FILLING_RETURN,
    ORDER_TYPE_BUY,
    ORDER_TYPE_SELL,
    ORDER_TYPE_BUY_LIMIT,
    ORDER_TYPE_SELL_LIMIT,
    ORDER_TYPE_BUY_STOP,
    ORDER_TYPE_SELL_STOP,
    TRADE_ACTION_DEAL,
    TRADE_ACTION_PENDING,
    TRADE_ACTION_MODIFY,
    TRADE_ACTION_REMOVE,
    TRADE_ACTION_SLTP,
    TRADE_RETCODE_DONE,
    TRADE_RETCODE_PLACED,
    TRADE_RETCODE_INVALID_FILL,
    ORDER_TIME_GTC,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_universal.reports import ok, fail
from mt5_universal.risk import resolve_magic, check_order

# ---------------------------------------------------------------------------
# Module-level look-up tables
# ---------------------------------------------------------------------------

_FILLING_MAP: dict[str, int] = {
    "FOK": ORDER_FILLING_FOK,
    "IOC": ORDER_FILLING_IOC,
    "RETURN": ORDER_FILLING_RETURN,
}

_ORDER_TYPE_STR: dict[int, str] = {
    0: "buy",
    1: "sell",
    2: "buy_limit",
    3: "sell_limit",
    4: "buy_stop",
    5: "sell_stop",
    6: "buy_stop_limit",
    7: "sell_stop_limit",
    8: "close_by",
}

_ORDER_STATE_STR: dict[int, str] = {
    0: "started",
    1: "placed",
    2: "canceled",
    3: "partial",
    4: "filled",
    5: "rejected",
    6: "expired",
}

_FILLING_STR: dict[int, str] = {0: "FOK", 1: "IOC", 2: "RETURN"}

_AGENT_MAGIC_MIN = 100000
_AGENT_MAGIC_MAX = 180000


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize_side(side: str) -> tuple[str | None, dict | None]:
    """Return (lowercased_side, None) on valid input or (None, fail_envelope)
    on invalid. side must be exactly 'buy' or 'sell' (case-insensitive).
    Anything else returns a fail envelope — silently treating typos as
    sells is a production safety bug for an agent-facing trading API.
    """
    if not isinstance(side, str):
        return None, fail("MT5_INVALID_PARAMS", f"side must be a string, got {type(side).__name__}.")
    side_lower = side.lower()
    if side_lower not in {"buy", "sell"}:
        return None, fail("MT5_INVALID_PARAMS", f"side must be one of: buy, sell. got {side!r}.")
    return side_lower, None


def _epoch_to_iso(epoch: int | float | None) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _is_agent_magic(magic: int | None) -> bool:
    """Return True when magic falls in the auto-derived range [100000, 180000)."""
    try:
        value = int(magic)
    except (TypeError, ValueError):
        return False
    return _AGENT_MAGIC_MIN <= value < _AGENT_MAGIC_MAX


def _magic_to_strategy_id(magic: int, cfg: dict | None) -> str | None:
    """Reverse-lookup strategy_id by magic in cfg['strategy_ids']."""
    if cfg is None:
        return None
    return next(
        (k for k, v in cfg.get("strategy_ids", {}).items() if int(v) == int(magic)),
        None,
    )


def _resolve_filling(symbol: str, filling_str: str) -> int:
    """Map filling string to MT5 constant for market orders.

    "auto" → ORDER_FILLING_FOK (hardcoded for Trading.com; broker profile
    abstraction lands in Task 2.8).
    Explicit "FOK"/"IOC"/"RETURN" → mapped constant.
    """
    upper = filling_str.upper()
    if upper in _FILLING_MAP:
        return _FILLING_MAP[upper]
    # "auto" — hardcode FOK (no symbol_info bitmask read in this task slice)
    return ORDER_FILLING_FOK


def _resolve_pending_filling(filling_str: str) -> int:
    """Resolve filling for pending orders.

    Per plan spec: FOK/IOC only; no RETURN for pending.
    "auto" → ORDER_FILLING_FOK (hardcoded).
    Explicit "FOK"/"IOC" → mapped constant. "RETURN" → FOK override.
    """
    upper = filling_str.upper()
    # Only FOK and IOC are valid for pending orders per plan spec
    if upper == "IOC":
        return ORDER_FILLING_IOC
    if upper == "FOK":
        return ORDER_FILLING_FOK
    # "auto" or "RETURN" → FOK for pending
    return ORDER_FILLING_FOK


def _live_gate_check(is_live_intent: bool) -> dict | None:
    """Return a fail envelope if live-gate blocks; None if clear.

    Used by cancel (which bypasses check_order's risk gates). Place functions
    get their live gate through check_order Guard 2 — no double-gating.
    """
    account_info = mt5_call("account_info")
    if account_info is None:
        return fail(
            "RISK_INVALID_INPUT",
            "account_info unavailable — MT5 may be disconnected.",
        )
    if not is_live_intent and account_info.trade_mode == ACCOUNT_TRADE_MODE_REAL:
        return fail(
            "RISK_LIVE_GATE_BLOCKED",
            "This is a live (real-money) account. Pass --live to confirm intentional live trading.",
        )
    return None


def _pending_order_to_dict(
    order,
    cfg: dict | None,
    strategy_id_hint: str | None = None,
) -> dict:
    """Normalize an MT5 pending order namedtuple/object to a plain dict."""
    type_filling = getattr(order, "type_filling", None)
    try:
        type_filling_key = int(type_filling)
    except (TypeError, ValueError):
        type_filling_key = type_filling
    strategy_id = strategy_id_hint or _magic_to_strategy_id(order.magic, cfg)
    comment = getattr(order, "comment", "") or ""
    comment_truncated = bool(
        comment
        and len(comment) >= 16
        and (strategy_id is None or comment != str(strategy_id))
    )
    return {
        "ticket": order.ticket,
        "symbol": order.symbol,
        "type": _ORDER_TYPE_STR.get(order.type, str(order.type)),
        "volume_initial": getattr(order, "volume_initial", None),
        "volume_current": getattr(order, "volume_current", None),
        "price_open": order.price_open,
        "price_current": getattr(order, "price_current", None),
        "sl": order.sl,
        "tp": order.tp,
        "time_setup": _epoch_to_iso(getattr(order, "time_setup", None)),
        "time_expiration": _epoch_to_iso(getattr(order, "time_expiration", None)),
        "state": _ORDER_STATE_STR.get(
            getattr(order, "state", None),
            str(getattr(order, "state", "")),
        ),
        "type_time": getattr(order, "type_time", None),
        "type_filling": type_filling,
        "type_filling_name": _FILLING_STR.get(type_filling_key, str(type_filling)),
        "magic": order.magic,
        "is_agent_magic": _is_agent_magic(order.magic),
        "strategy_id": strategy_id,
        "comment": comment,
        "comment_truncated": comment_truncated,
    }


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
    """Map order_send result to a JSON envelope."""
    if result is None:
        return fail("MT5_ORDER_REJECTED", "order_send returned None.")

    retcode = result.retcode

    if retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
        return ok({
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
        })

    if retcode == TRADE_RETCODE_INVALID_FILL:
        sym_info = mt5_call("symbol_info", symbol)
        filling_mode = sym_info.filling_mode if sym_info is not None else None
        return fail(
            "MT5_ORDER_REJECTED",
            f"Invalid filling mode (retcode 10030). Symbol filling_mode bitmask: {filling_mode}",
            data={"mt5_retcode": retcode},
        )

    comment = getattr(result, "comment", "Order rejected by broker.")
    return fail(
        "MT5_ORDER_REJECTED",
        str(comment),
        data={"mt5_retcode": retcode},
    )


# ---------------------------------------------------------------------------
# list_pending
# ---------------------------------------------------------------------------

def list_pending(
    symbol: str | None = None,
    *,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Return currently pending orders, optionally filtered by symbol/strategy.

    Args:
        symbol: Filter to orders on this symbol only. None returns all.
        strategy_id: Filter by strategy magic (requires cfg).
        cfg: Configuration dict; required when strategy_id is specified.

    Returns:
        ok([...]) with list of pending order dicts, or fail envelope.
    """
    if strategy_id and cfg is None:
        return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")

    if symbol:
        orders = mt5_call("orders_get", symbol=symbol)
    else:
        orders = mt5_call("orders_get")

    if orders is None:
        return fail("MT5_NO_DATA", "orders_get returned None.")

    result = list(orders)
    if strategy_id:
        magic = resolve_magic(strategy_id, cfg)
        result = [o for o in result if int(o.magic) == int(magic)]

    return ok([_pending_order_to_dict(o, cfg, strategy_id_hint=strategy_id) for o in result])


# ---------------------------------------------------------------------------
# place_market
# ---------------------------------------------------------------------------

def place_market(
    symbol: str,
    side: str,
    *,
    volume: float,
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
    """Place a market order (TRADE_ACTION_DEAL).

    The live gate is handled by check_order Guard 2. risk_pct sizing is
    deferred to the CLI layer; this function takes an explicit volume.

    Args:
        symbol: Instrument symbol.
        side: "buy" or "sell".
        volume: Lot size (required; pass risk-sized lot from caller).
        sl: Stop-loss price (required).
        tp: Take-profit price (optional).
        comment: Custom comment (defaults to strategy_id or "").
        strategy_id: Optional strategy identifier (max 31 chars).
        magic: Override magic number; defaults to resolve_magic(strategy_id, cfg).
        deviation: Slippage tolerance in points.
        filling: "auto" (FOK) / "FOK" / "IOC" / "RETURN".
        cfg: Effective configuration dict.
        is_live_intent: Pass True to confirm intentional live trading.

    Returns:
        ok({"ticket": ..., "symbol": ..., ...}) on success, or fail envelope.
    """
    side_lower, side_err = _normalize_side(side)
    if side_err is not None:
        return side_err

    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    tick = mt5_call("symbol_info_tick", symbol)
    if tick is None:
        return fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
    entry_price = tick.ask if side_lower == "buy" else tick.bid

    risk_result = check_order(
        symbol=symbol,
        side=side,
        volume=volume,
        sl=sl,
        tp=tp,
        strategy_id=strategy_id,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_filling(symbol, filling)
    order_type = ORDER_TYPE_BUY if side_lower == "buy" else ORDER_TYPE_SELL

    request = {
        "action": TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "deviation": deviation,
        "magic": resolved_magic,
        "comment": comment or strategy_id or "",
        "type_time": ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }

    result = mt5_call("order_send", request)
    return _finalize_order(
        result, symbol, side, float(volume), entry_price, sl, tp,
        resolved_magic, strategy_id,
    )


# ---------------------------------------------------------------------------
# place_limit
# ---------------------------------------------------------------------------

def place_limit(
    symbol: str,
    side: str,
    price: float,
    *,
    volume: float,
    sl: float,
    tp: float | None = None,
    strategy_id: str | None = None,
    magic: int | None = None,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a limit pending order (TRADE_ACTION_PENDING, BUY_LIMIT / SELL_LIMIT).

    Note: expiry/ORDER_TIME_SPECIFIED is deferred. All pending orders use GTC.

    Args:
        symbol: Instrument symbol.
        side: "buy" or "sell".
        price: Limit price at which the order will execute.
        volume: Lot size.
        sl: Stop-loss price (required).
        tp: Take-profit price (optional).
        strategy_id: Optional strategy identifier (max 31 chars).
        magic: Override magic number.
        filling: "auto" (FOK) / "FOK" / "IOC". RETURN not valid for pending.
        cfg: Effective configuration dict.
        is_live_intent: Pass True to confirm intentional live trading.

    Returns:
        ok({"ticket": ..., ...}) on success, or fail envelope.
    """
    side_lower, side_err = _normalize_side(side)
    if side_err is not None:
        return side_err

    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    risk_result = check_order(
        symbol=symbol,
        side=side,
        volume=volume,
        sl=sl,
        tp=tp,
        strategy_id=strategy_id,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_pending_filling(filling)
    order_type = (
        ORDER_TYPE_BUY_LIMIT if side_lower == "buy" else ORDER_TYPE_SELL_LIMIT
    )

    request = {
        "action": TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }

    result = mt5_call("order_send", request)
    return _finalize_order(
        result, symbol, side, float(volume), float(price), sl, tp,
        resolved_magic, strategy_id,
    )


# ---------------------------------------------------------------------------
# dryrun
# ---------------------------------------------------------------------------

def dryrun(
    symbol: str,
    side: str,
    *,
    order_type: str = "market",
    price: float | None = None,
    volume: float,
    sl: float,
    tp: float | None = None,
    strategy_id: str | None = None,
    magic: int | None = None,
    deviation: int = 20,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Validate an order without placing it.

    Runs the full risk envelope then calls order_check (NOT order_send).
    Returns margin, margin_free, margin_level, profit, retcode.

    Args:
        symbol: Instrument symbol.
        side: "buy" or "sell".
        order_type: "market", "limit", or "stop".
        price: Required for limit/stop order types.
        volume: Lot size.
        sl: Stop-loss price (required).
        tp: Take-profit price (optional).
        strategy_id: Optional strategy identifier.
        magic: Override magic number.
        deviation: Slippage tolerance (market orders only).
        filling: Filling mode string.
        cfg: Effective configuration dict.
        is_live_intent: Dry-run checks live gate without consuming rate limit.

    Returns:
        ok({"dry_run": True, "margin": ..., ...}) on success, or fail envelope.
    """
    side_lower, side_err = _normalize_side(side)
    if side_err is not None:
        return side_err

    order_type_lower = order_type.lower()
    if order_type_lower not in {"market", "limit", "stop"}:
        return fail("MT5_INVALID_PARAMS", "order_type must be one of: market, limit, stop.")
    if order_type_lower in {"limit", "stop"} and price is None:
        return fail("MT5_INVALID_PARAMS", "--price is required for pending order dryrun.")

    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    if order_type_lower == "market":
        tick = mt5_call("symbol_info_tick", symbol)
        if tick is None:
            return fail("MT5_NO_DATA", f"No tick data for {symbol!r}.")
        entry_price = tick.ask if side_lower == "buy" else tick.bid
    else:
        entry_price = float(price)

    risk_result = check_order(
        symbol=symbol,
        side=side,
        volume=volume,
        sl=sl,
        tp=tp,
        strategy_id=strategy_id,
        cfg=cfg,
        is_live_intent=is_live_intent,
        consume_rate_limit=False,  # dry-run never consumes a rate-limit slot
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else resolve_magic(strategy_id, cfg)
    resolved_filling = (
        _resolve_filling(symbol, filling)
        if order_type_lower == "market"
        else _resolve_pending_filling(filling)
    )

    if order_type_lower == "market":
        mt5_order_type = ORDER_TYPE_BUY if side_lower == "buy" else ORDER_TYPE_SELL
        action = TRADE_ACTION_DEAL
    elif order_type_lower == "limit":
        mt5_order_type = (
            ORDER_TYPE_BUY_LIMIT if side_lower == "buy" else ORDER_TYPE_SELL_LIMIT
        )
        action = TRADE_ACTION_PENDING
    else:
        # stop — ORDER_TYPE_BUY_STOP / SELL_STOP
        mt5_order_type = (
            ORDER_TYPE_BUY_STOP if side_lower == "buy" else ORDER_TYPE_SELL_STOP
        )
        action = TRADE_ACTION_PENDING

    request = {
        "action": action,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5_order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }
    if order_type_lower == "market":
        request["deviation"] = deviation

    result = mt5_call("order_check", request)
    if result is None:
        return fail("MT5_ORDER_REJECTED", "order_check returned None.")

    retcode = getattr(result, "retcode", None)
    if retcode not in (0, TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
        return fail(
            "MT5_ORDER_REJECTED",
            getattr(result, "comment", None) or "order_check rejected request.",
            data={"mt5_retcode": retcode},
        )

    return ok({
        "dry_run": True,
        "symbol": symbol,
        "side": side,
        "order_type": order_type_lower,
        "price": entry_price,
        "volume": float(volume),
        "sl": sl,
        "tp": tp,
        "margin": getattr(result, "margin", None),
        "margin_free": getattr(result, "margin_free", None),
        "margin_level": getattr(result, "margin_level", None),
        "profit": getattr(result, "profit", None),
        "retcode": retcode,
    })


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

def cancel(ticket: int, *, is_live_intent: bool) -> dict:
    """Cancel a pending order (TRADE_ACTION_REMOVE).

    Live gate checked via _live_gate_check (account_info-based), NOT check_order,
    because cancel does not go through the full risk gauntlet.

    Args:
        ticket: Pending order ticket number.
        is_live_intent: Must be True on a live account or the call is blocked.

    Returns:
        ok({"ticket": ..., "cancelled": True}) on success, or fail envelope.
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    orders = mt5_call("orders_get", ticket=ticket)
    if not orders:
        return fail("MT5_TICKET_NOT_FOUND", f"Pending order {ticket} not found.")

    ord_ = orders[0]
    request = {
        "action": TRADE_ACTION_REMOVE,
        "order": ticket,
        "symbol": ord_.symbol,
    }
    result = mt5_call("order_send", request)
    if result is None:
        return fail("MT5_ORDER_REJECTED", "order_send returned None for REMOVE.")
    if result.retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
        return ok({"ticket": ticket, "cancelled": True})
    return fail(
        "MT5_ORDER_REJECTED",
        str(getattr(result, "comment", "")),
        data={"mt5_retcode": result.retcode},
    )


# ---------------------------------------------------------------------------
# poll_fill
# ---------------------------------------------------------------------------

def poll_fill(ticket: int, timeout_ms: int = 5000) -> dict:
    """Poll until the ticket appears as a position or the timeout expires.

    Polls via positions_get; if the ticket vanishes from pending orders
    (rejected/cancelled by broker) returns filled=False immediately.

    Args:
        ticket: Order ticket to watch.
        timeout_ms: Maximum wait in milliseconds (default 5000).

    Returns:
        ok({"filled": bool, "ticket": int}) — caller decides to cancel on False.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        positions = mt5_call("positions_get", ticket=ticket)
        if positions:
            return ok({"filled": True, "ticket": ticket})
        pending = mt5_call("orders_get", ticket=ticket)
        if not pending:
            # Order disappeared without becoming a position — rejected/cancelled
            return ok({"filled": False, "ticket": ticket})
        time.sleep(0.1)

    return ok({"filled": False, "ticket": ticket})


# ---------------------------------------------------------------------------
# place_stop
# ---------------------------------------------------------------------------

def place_stop(
    symbol: str,
    side: str,
    price: float,
    *,
    volume: float,
    sl: float,
    tp: float | None = None,
    strategy_id: str | None = None,
    magic: int | None = None,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a stop pending order (TRADE_ACTION_PENDING, BUY_STOP / SELL_STOP).

    Same shape as place_limit but uses the stop order types. Risk gate runs
    first via check_order (Guard 2 handles the live gate).

    Note: expiry / ORDER_TIME_SPECIFIED is deferred. All stop orders use GTC.
    # TODO: expiry support pending ORDER_TIME_SPECIFIED bridge widening.

    Args:
        symbol: Instrument symbol.
        side: "buy" or "sell".
        price: Stop trigger price.
        volume: Lot size.
        sl: Stop-loss price (required).
        tp: Take-profit price (optional).
        strategy_id: Optional strategy identifier.
        magic: Override magic number.
        filling: "auto" (FOK) / "FOK" / "IOC". RETURN not valid for pending.
        cfg: Effective configuration dict.
        is_live_intent: Pass True to confirm intentional live trading.

    Returns:
        ok({"ticket": ..., ...}) on success, or fail envelope.
    """
    side_lower, side_err = _normalize_side(side)
    if side_err is not None:
        return side_err

    if not ensure_symbol(symbol):
        return fail("MT5_INVALID_SYMBOL", f"Symbol {symbol!r} is not available in MT5.")

    risk_result = check_order(
        symbol=symbol,
        side=side,
        volume=volume,
        sl=sl,
        tp=tp,
        strategy_id=strategy_id,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not risk_result["ok"]:
        return risk_result

    resolved_magic = magic if magic is not None else resolve_magic(strategy_id, cfg)
    resolved_filling = _resolve_pending_filling(filling)
    order_type = ORDER_TYPE_BUY_STOP if side_lower == "buy" else ORDER_TYPE_SELL_STOP

    request = {
        "action": TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": float(price),
        "sl": sl,
        "tp": tp if tp is not None else 0.0,
        "magic": resolved_magic,
        "comment": strategy_id or "",
        "type_time": ORDER_TIME_GTC,
        "type_filling": resolved_filling,
    }

    result = mt5_call("order_send", request)
    return _finalize_order(
        result, symbol, side, float(volume), float(price), sl, tp,
        resolved_magic, strategy_id,
    )


# ---------------------------------------------------------------------------
# modify
# ---------------------------------------------------------------------------

def modify(
    ticket: int,
    *,
    sl: float | None = None,
    tp: float | None = None,
    price: float | None = None,
    expiry=None,
    is_live_intent: bool,
) -> dict:
    """Modify an open position (SL/TP) or a pending order (price/SL/TP).

    Auto-detects ticket type: positions_get first, then orders_get.

    - Open position → TRADE_ACTION_SLTP. Preserves existing sl/tp when
      caller passes None. price and expiry are ignored for positions.
    - Pending order → TRADE_ACTION_MODIFY. Preserves existing price/sl/tp
      when caller passes None. expiry is deferred (GTC always).

    # TODO: expiry support pending ORDER_TIME_SPECIFIED bridge widening.

    Live gate uses _live_gate_check (same pattern as cancel).

    Args:
        ticket: Order or position ticket.
        sl: New stop-loss price. None preserves existing.
        tp: New take-profit price. None preserves existing.
        price: New pending-order price. None preserves existing.
        expiry: Deferred — accepted for signature stability but ignored.
        is_live_intent: Must be True on a live account.

    Returns:
        ok({"ticket": ..., "action": "SLTP"|"MODIFY", ...}) on success,
        or fail envelope.
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    # --- Open position branch ---
    positions = mt5_call("positions_get", ticket=ticket)
    if positions:
        pos = positions[0]
        sl_final = sl if sl is not None else pos.sl
        tp_final = tp if tp is not None else pos.tp
        request = {
            "action": TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": sl_final,
            "tp": tp_final,
            "magic": pos.magic,
        }
        result = mt5_call("order_send", request)
        if result is None:
            return fail("MT5_ORDER_REJECTED", "order_send returned None for SLTP modify.")
        if result.retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
            return ok({"ticket": ticket, "action": "SLTP", "sl": sl_final, "tp": tp_final})
        return fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "")),
            data={"mt5_retcode": result.retcode},
        )

    # --- Pending order branch ---
    orders = mt5_call("orders_get", ticket=ticket)
    if orders:
        ord_ = orders[0]
        price_final = price if price is not None else ord_.price_open
        sl_final = sl if sl is not None else ord_.sl
        tp_final = tp if tp is not None else ord_.tp
        request = {
            "action": TRADE_ACTION_MODIFY,
            "order": ticket,
            "symbol": ord_.symbol,
            "price": price_final,
            "sl": sl_final,
            "tp": tp_final,
            "type_time": ord_.type_time,
            "expiration": ord_.time_expiration,
            "magic": ord_.magic,
        }
        result = mt5_call("order_send", request)
        if result is None:
            return fail("MT5_ORDER_REJECTED", "order_send returned None for MODIFY.")
        if result.retcode in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
            return ok({"ticket": ticket, "action": "MODIFY", "price": price_final,
                       "sl": sl_final, "tp": tp_final})
        return fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "")),
            data={"mt5_retcode": result.retcode},
        )

    return fail(
        "MT5_TICKET_NOT_FOUND",
        f"Ticket {ticket} not found in positions or pending orders.",
    )


# ---------------------------------------------------------------------------
# cancel_all_pending
# ---------------------------------------------------------------------------

def cancel_all_pending(symbol: str | None = None, *, is_live_intent: bool) -> dict:
    """Cancel all pending orders, optionally scoped to one symbol.

    Continues on per-ticket failure (fail-soft). Returns per-ticket outcome
    dicts with cancelled/failed summary counts.

    Deliberate divergence from legacy: return shape uses {"per_ticket": [...],
    "cancelled": N, "failed": N} instead of legacy's flat list of {"ticket": ...,
    "result": "canceled"/"error"} entries. The structured shape is easier for
    agents to parse without iterating to count outcomes.

    Args:
        symbol: Filter to this symbol only. None cancels all pending orders.
        is_live_intent: Must be True on a live account.

    Returns:
        ok({"per_ticket": [...], "cancelled": N, "failed": N}) — outer ok=True
        even when some tickets fail. fail envelope only if the live gate or
        orders_get itself fails.
    """
    gate = _live_gate_check(is_live_intent)
    if gate is not None:
        return gate

    if symbol:
        pending = mt5_call("orders_get", symbol=symbol)
    else:
        pending = mt5_call("orders_get")

    if pending is None:
        return fail("MT5_CONNECTION_ERROR", "orders_get returned None.")

    results = []
    cancelled = 0
    failed = 0
    for order in pending:
        ticket = int(order.ticket)
        result = cancel(ticket, is_live_intent=is_live_intent)
        if result["ok"]:
            cancelled += 1
            results.append({"ticket": ticket, "ok": True})
        else:
            failed += 1
            results.append({"ticket": ticket, "ok": False, "error": result["error"]})

    return ok({"per_ticket": results, "cancelled": cancelled, "failed": failed})
