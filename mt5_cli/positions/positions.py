"""
positions.py — Open position management for mt5_cli.

Cherry-picked from archive/legacy-mt5/core/position.py (247 LOC).
5 public functions: list, close, close_all, move_sl, breakeven.
(Skip: show — not in plan scope.)

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_cli.bridge.mt5_call()``.

Deliberate divergences from legacy:

1. Uses ok()/fail() from mt5_cli.reports instead of local _fail helper.
2. fail() error wraps mt5_retcode in data={"mt5_retcode": ...} (not a kwarg).
3. No risk.check_order — only _live_gate_check (account_info-based live gate).
   Positions do not go through risk gauntlet; they manage existing trades.
4. _live_gate_check shape matches mt5_cli.orders.orders._live_gate_check
   verbatim (account_info → ACCOUNT_TRADE_MODE_REAL check).
5. Module renamed plural: legacy 'position' → 'positions' package.
"""
from __future__ import annotations

import os

from mt5_cli.bridge import (
    mt5_call,
    ORDER_TYPE_BUY,
    ORDER_TYPE_SELL,
    POSITION_TYPE_BUY,
    ORDER_FILLING_FOK,
    TRADE_ACTION_DEAL,
    TRADE_ACTION_SLTP,
    TRADE_RETCODE_DONE,
    TRADE_RETCODE_PLACED,
    ORDER_TIME_GTC,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_cli.reports import ok, fail


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _live_gate_check(is_live_intent: bool, cfg: dict | None = None) -> dict | None:
    """Return a fail envelope if the live-trade gate blocks; None if clear.

    Position mutations (close/close_all/move_sl/breakeven) manage real money on
    a live account, so they enforce the SAME triple lock as order placement
    (see mt5_cli.orders.orders._live_gate_check). On a REAL account, all three
    gates must be armed:

      1. is_live_intent=True  — the caller's --live confirmation
      2. cfg["live"] is True  — the config/env layer opts in to live trading
      3. MT5_LIVE=1           — the operator's shell-level intent

    DEMO and CONTEST accounts bypass the lock by design (return None before any
    gate is checked). ``cfg`` defaults to an empty mapping, so a caller that
    omits it fails closed on a real account (cfg["live"] reads falsy).
    """
    cfg = cfg or {}
    account_info = mt5_call("account_info")
    if account_info is None:
        return fail(
            "RISK_INVALID_INPUT",
            "account_info unavailable — MT5 may be disconnected.",
        )
    if account_info.trade_mode != ACCOUNT_TRADE_MODE_REAL:
        return None  # DEMO / CONTEST bypass the triple lock (documented behavior)
    if not is_live_intent:
        return fail(
            "RISK_LIVE_GATE_BLOCKED",
            "This is a live (real-money) account. Pass --live to confirm "
            "intentional live trading.",
        )
    if not cfg.get("live"):
        return fail(
            "RISK_LIVE_GATE_BLOCKED",
            'Live trading requires cfg["live"]=true. Set it in your config '
            "file (or pass overrides={'live': True}) to arm live trading.",
        )
    if os.environ.get("MT5_LIVE") != "1":
        return fail(
            "RISK_LIVE_GATE_BLOCKED",
            "Live trading requires MT5_LIVE=1 in the environment. Export "
            "MT5_LIVE=1 (or set it in your shell profile) to arm live trading.",
        )
    return None


def _pos_to_dict(pos) -> dict:
    """Normalize a PositionInfo namedtuple/object to a plain dict."""
    return {
        "ticket": pos.ticket,
        "symbol": pos.symbol,
        "type": "buy" if pos.type == POSITION_TYPE_BUY else "sell",
        "volume": pos.volume,
        "open_price": pos.price_open,
        "sl": pos.sl,
        "tp": pos.tp,
        "profit": pos.profit,
        "swap": pos.swap,
        "magic": int(pos.magic) if hasattr(pos, "magic") else 0,
        "comment": getattr(pos, "comment", "") or "",
    }


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def list(symbol: str | None = None) -> dict:  # noqa: A001
    """Return all open positions, optionally filtered by symbol.

    Note: shadows the Python builtin ``list``; intentional per plan spec.

    Args:
        symbol: Filter to positions on this symbol only. None returns all.

    Returns:
        ok([...]) with list of position dicts, or fail envelope.
    """
    if symbol:
        positions = mt5_call("positions_get", symbol=symbol)
    else:
        positions = mt5_call("positions_get")

    if positions is None:
        return fail("MT5_NO_DATA", "positions_get returned None.")

    return ok([_pos_to_dict(p) for p in positions])


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

def close(
    ticket: int,
    volume: float | None = None,
    *,
    is_live_intent: bool,
    cfg: dict | None = None,
) -> dict:
    """Close a position fully or partially.

    MT5 has no dedicated position_close API. Close = market order in the
    opposite direction tied to the position via ``position=ticket``.

    Args:
        ticket: Position ticket number.
        volume: Lot size to close. None → close full position volume.
        is_live_intent: Must be True on a live account or the call is blocked.
        cfg: Effective config; required on a REAL account for the triple lock
            (cfg["live"] gate). Omitting it fails closed on real accounts.

    Returns:
        ok({"ticket", "result": "closed", "profit"}) on success, or fail envelope.
    """
    gate = _live_gate_check(is_live_intent, cfg)
    if gate is not None:
        return gate

    positions = mt5_call("positions_get", ticket=ticket)
    if not positions:
        return fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    close_volume = volume if volume is not None else pos.volume
    close_type = ORDER_TYPE_SELL if pos.type == POSITION_TYPE_BUY else ORDER_TYPE_BUY

    tick = mt5_call("symbol_info_tick", pos.symbol)
    if tick is None:
        return fail("MT5_NO_DATA", f"No tick data for {pos.symbol!r}.")
    # BUY closes at bid (sell price); SELL closes at ask (buy price)
    price = tick.bid if pos.type == POSITION_TYPE_BUY else tick.ask

    request = {
        "action": TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": float(close_volume),
        "type": close_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": f"close#{ticket}",
        "type_time": ORDER_TIME_GTC,
        "type_filling": ORDER_FILLING_FOK,
    }

    result = mt5_call("order_send", request)
    if result is None:
        return fail("MT5_ORDER_REJECTED", "order_send returned None.")

    retcode = result.retcode
    if retcode not in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
        return fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "Position close rejected.")),
            data={"mt5_retcode": retcode},
        )

    return ok({
        "ticket": ticket,
        "result": "closed",
        "profit": pos.profit,
    })


# ---------------------------------------------------------------------------
# close_all
# ---------------------------------------------------------------------------

def close_all(
    symbol: str | None = None,
    *,
    is_live_intent: bool,
    cfg: dict | None = None,
) -> dict:
    """Close all open positions, optionally restricted to one symbol.

    Fail-soft: continues on per-ticket failure. Returns a list of per-ticket
    outcome dicts — callers must inspect each entry.

    Args:
        symbol: Filter to positions on this symbol only. None closes all.
        is_live_intent: Must be True on a live account or the call is blocked.
        cfg: Effective config; threaded into each per-ticket close for the
            triple lock. Omitting it fails closed on real accounts.

    Returns:
        ok([{ticket, result, profit|error}, ...]) — always ok-level on success,
        with per-ticket error entries for individual failures.
    """
    gate = _live_gate_check(is_live_intent, cfg)
    if gate is not None:
        return gate

    if symbol:
        positions = mt5_call("positions_get", symbol=symbol)
    else:
        positions = mt5_call("positions_get")

    if positions is None:
        return fail("MT5_NO_DATA", "positions_get returned None.")

    results = []
    for pos in positions:
        outcome = close(pos.ticket, is_live_intent=is_live_intent, cfg=cfg)
        entry: dict = {"ticket": pos.ticket}
        if outcome["ok"]:
            entry["result"] = "closed"
            entry["profit"] = outcome["data"]["profit"]
        else:
            entry["result"] = "error"
            entry["error"] = outcome["error"]
        results.append(entry)

    return ok(results)


# ---------------------------------------------------------------------------
# move_sl
# ---------------------------------------------------------------------------

def move_sl(
    ticket: int,
    sl: float,
    *,
    is_live_intent: bool,
    cfg: dict | None = None,
) -> dict:
    """Move the stop-loss of an open position (TRADE_ACTION_SLTP).

    Preserves the existing TP — does not clobber it.

    Args:
        ticket: Position ticket number.
        sl: New stop-loss price.
        is_live_intent: Must be True on a live account or the call is blocked.
        cfg: Effective config; required on a REAL account for the triple lock.
            Omitting it fails closed on real accounts.

    Returns:
        ok({"ticket", "result": "sl_moved"}) on success, or fail envelope.
    """
    gate = _live_gate_check(is_live_intent, cfg)
    if gate is not None:
        return gate

    positions = mt5_call("positions_get", ticket=ticket)
    if not positions:
        return fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    request = {
        "action": TRADE_ACTION_SLTP,
        "symbol": pos.symbol,
        "position": ticket,
        "sl": sl,
        "tp": pos.tp,  # preserve existing TP
    }

    result = mt5_call("order_send", request)
    if result is None:
        return fail("MT5_ORDER_REJECTED", "order_send returned None.")

    retcode = result.retcode
    if retcode not in (TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED):
        return fail(
            "MT5_ORDER_REJECTED",
            str(getattr(result, "comment", "SL move rejected.")),
            data={"mt5_retcode": retcode},
        )

    return ok({"ticket": ticket, "result": "sl_moved"})


# ---------------------------------------------------------------------------
# breakeven
# ---------------------------------------------------------------------------

def breakeven(
    ticket: int,
    buffer_points: int = 0,
    *,
    is_live_intent: bool,
    cfg: dict | None = None,
) -> dict:
    """Move SL to the open price ± buffer_points × symbol.point.

    For BUY positions:  new_sl = open_price + buffer_points * point  (in favour)
    For SELL positions: new_sl = open_price - buffer_points * point  (in favour)

    Args:
        ticket: Position ticket number.
        buffer_points: Extra points beyond open price (default 0 = exact breakeven).
        is_live_intent: Must be True on a live account or the call is blocked.
        cfg: Effective config; threaded into the underlying move_sl for the
            triple lock. Omitting it fails closed on real accounts.

    Returns:
        ok({"ticket", "result": "breakeven_set", "sl_set_to"}) on success,
        or fail envelope.
    """
    gate = _live_gate_check(is_live_intent, cfg)
    if gate is not None:
        return gate

    positions = mt5_call("positions_get", ticket=ticket)
    if not positions:
        return fail("MT5_TICKET_NOT_FOUND", f"Position {ticket} not found.")

    pos = positions[0]
    sym_info = mt5_call("symbol_info", pos.symbol)
    if sym_info is None:
        return fail("MT5_NO_DATA", f"No symbol_info for {pos.symbol!r}.")

    point = sym_info.point
    open_price = pos.price_open

    if pos.type == POSITION_TYPE_BUY:
        new_sl = open_price + buffer_points * point
    else:              # SELL
        new_sl = open_price - buffer_points * point

    outcome = move_sl(ticket, new_sl, is_live_intent=is_live_intent, cfg=cfg)
    if not outcome["ok"]:
        return outcome

    return ok({
        "ticket": ticket,
        "result": "breakeven_set",
        "sl_set_to": new_sl,
    })
