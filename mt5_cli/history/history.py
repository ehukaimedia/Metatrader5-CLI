"""
history.py — Trade history primitives for mt5_cli.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_call()`` via the bridge.

Provides historical orders, deals, and aggregate performance statistics as
plain dicts wrapped in standard result envelopes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from mt5_cli.bridge import mt5_call
from mt5_cli.reports import ok, fail
from mt5_cli.risk import resolve_magic


# ---------------------------------------------------------------------------
# Int → string maps (MT5 wire values — stable across MT5 versions)
# ---------------------------------------------------------------------------

_ORDER_TYPE_STR: dict[int, str] = {
    0: "buy", 1: "sell", 2: "buy_limit", 3: "sell_limit",
    4: "buy_stop", 5: "sell_stop", 6: "buy_stop_limit", 7: "sell_stop_limit",
    8: "close_by",
}

_ORDER_STATE_STR: dict[int, str] = {
    0: "started", 1: "placed", 2: "canceled", 3: "partial",
    4: "filled", 5: "rejected", 6: "expired",
}

_DEAL_TYPE_STR: dict[int, str] = {
    0: "buy", 1: "sell", 2: "balance", 3: "credit", 4: "charge",
    5: "correction", 6: "bonus", 7: "commission", 12: "interest",
    13: "buy_canceled", 14: "sell_canceled",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _magic_to_strategy_id(magic: int, cfg: dict | None) -> str | None:
    if cfg is None:
        return None
    return next((k for k, v in cfg.get("strategy_ids", {}).items() if int(v) == magic), None)


def _epoch_to_iso(epoch: int | float) -> str:
    """Convert a Unix-epoch integer to an ISO-8601 UTC string."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _order_to_dict(order, cfg: dict | None) -> dict:
    return {
        "ticket": order.ticket,
        "symbol": order.symbol,
        "type": _ORDER_TYPE_STR.get(order.type, str(order.type)),
        "volume": order.volume_initial,
        "price": order.price_open,
        "sl": order.sl,
        "tp": order.tp,
        "time_setup": _epoch_to_iso(order.time_setup),
        "time_done": _epoch_to_iso(order.time_done),
        "state": _ORDER_STATE_STR.get(order.state, str(order.state)),
        "magic": order.magic,
        "strategy_id": _magic_to_strategy_id(order.magic, cfg),
    }


def _deal_to_dict(deal) -> dict:
    return {
        "ticket": deal.ticket,
        "order": deal.order,
        "symbol": deal.symbol,
        "type": _DEAL_TYPE_STR.get(deal.type, str(deal.type)),
        "volume": deal.volume,
        "price": deal.price,
        "profit": deal.profit,
        "commission": deal.commission,
        "swap": deal.swap,
        "time": _epoch_to_iso(deal.time),
        "magic": deal.magic,
    }


# ---------------------------------------------------------------------------
# orders
# ---------------------------------------------------------------------------

# date_from/date_to are UTC datetimes or None. CLI/MCP coerces user strings before this layer.
def orders(
    date_from: datetime | None,
    date_to: datetime | None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Return historical orders in [date_from, date_to].

    Filters in Python by symbol and/or resolved magic (strategy_id).
    ``cfg`` is required when ``strategy_id`` is supplied.
    """
    magic_filter: int | None = None
    if strategy_id:
        if cfg is None:
            return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")
        magic_filter = resolve_magic(strategy_id, cfg)

    raw = mt5_call("history_orders_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_orders_get returned None.")

    result = list(raw)
    if symbol:
        result = [o for o in result if o.symbol == symbol]
    if magic_filter is not None:
        result = [o for o in result if o.magic == magic_filter]

    return ok([_order_to_dict(o, cfg) for o in result])


# ---------------------------------------------------------------------------
# deals
# ---------------------------------------------------------------------------

def deals(
    date_from: datetime | None,
    date_to: datetime | None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Return historical deals in [date_from, date_to].

    Filters in Python by symbol and/or resolved magic (strategy_id).
    ``cfg`` is required when ``strategy_id`` is supplied.
    """
    magic_filter: int | None = None
    if strategy_id:
        if cfg is None:
            return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")
        magic_filter = resolve_magic(strategy_id, cfg)

    raw = mt5_call("history_deals_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_deals_get returned None.")

    result = list(raw)
    if symbol:
        result = [d for d in result if d.symbol == symbol]
    if magic_filter is not None:
        result = [d for d in result if d.magic == magic_filter]

    return ok([_deal_to_dict(d) for d in result])


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def stats(
    date_from: datetime | None,
    date_to: datetime | None,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Compute performance statistics for deals in [date_from, date_to].

    Optionally scoped to one strategy_id (matched via resolved magic).
    ``cfg`` is required when ``strategy_id`` is supplied.
    Returns zeros (not NaN) when there are no deals.
    """
    magic_filter: int | None = None
    if strategy_id:
        if cfg is None:
            return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")
        magic_filter = resolve_magic(strategy_id, cfg)

    raw = mt5_call("history_deals_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_deals_get returned None.")

    deal_list = sorted(raw, key=lambda d: d.time)
    if magic_filter is not None:
        deal_list = [d for d in deal_list if d.magic == magic_filter]

    n = len(deal_list)
    if n == 0:
        return ok({
            "trades": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        })

    profits = [d.profit for d in deal_list]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    sum_wins = sum(wins) if wins else 0.0
    sum_losses = abs(sum(losses)) if losses else 0.0

    # Max drawdown from running equity curve
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in profits:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    return ok({
        "trades": n,
        "win_rate": len(wins) / n,
        "total_profit": sum(profits),
        "avg_profit": sum_wins / len(wins) if wins else 0.0,
        "avg_loss": sum_losses / len(losses) if losses else 0.0,
        "profit_factor": sum_wins / sum_losses if sum_losses > 0 else 0.0,
        "max_drawdown": max_dd,
    })
