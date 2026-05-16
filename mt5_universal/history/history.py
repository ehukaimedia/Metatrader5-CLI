"""
history.py — Trade history primitives for mt5_universal.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_call()`` via the bridge.

Pattern-ported from archive/legacy-mt5/core/history.py; imports and envelope
construction rewritten for mt5_universal.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from mt5_universal.bridge import mt5_call
from mt5_universal.reports import ok, fail


# ---------------------------------------------------------------------------
# TEMPORARY: inline magic resolver until Task 2.3.E ships
# ---------------------------------------------------------------------------

def _resolve_magic(strategy_id: str | None, cfg: dict | None) -> int:
    """TEMPORARY: duplicates archive/legacy-mt5/core/risk.py::resolve_magic.

    Delete this when Task 2.3.E ships mt5_universal.risk.resolve_magic;
    replace the three call sites with `from mt5_universal.risk import resolve_magic`.

    NOTE: This is a simplified version of the legacy resolve_magic.  Differences
    from archive/legacy-mt5/core/risk.py::resolve_magic (intentional for a stub):
    - Uses cfg.get("magic", 88888) instead of cfg["magic"] (no KeyError on missing key).
    - Does NOT raise ValueError when a configured magic >= 100000 (collision guard removed).
    - Does NOT log auto-derived magics (no _logged_strategy_ids tracking).
    - Checks `if strategy_id is None` for the fallback (vs legacy's `if strategy_id:` truthy
      check — semantically equivalent for None/non-None but differs on empty string "").

    MT5_NO_DATA → MT5_CONNECTION_ERROR rename (intentional): mt5.history_*_get returning
    None indicates a connection/terminal failure, not an empty result set. An empty result
    returns an empty tuple, not None. The rename makes the error semantically correct so
    2.3.E implementers do not silently revert it when the real risk module lands.
    """
    cfg = cfg or {}
    if strategy_id is None:
        return int(cfg.get("magic", 88888))
    ids_map = cfg.get("strategy_ids") or {}
    if strategy_id in ids_map:
        return int(ids_map[strategy_id])
    digest = hashlib.sha256(strategy_id.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) % 80000 + 100000


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

# date_from/date_to are datetime objects (UTC). CLI/MCP coerces user strings before this layer.
def orders(
    date_from: datetime,
    date_to: datetime,
    symbol: str | None = None,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Return historical orders in [date_from, date_to].

    Filters in Python by symbol and/or resolved magic (strategy_id).
    ``cfg`` is required when ``strategy_id`` is supplied.
    """
    if strategy_id and cfg is None:
        return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")

    raw = mt5_call("history_orders_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_orders_get returned None.")

    result = list(raw)
    if symbol:
        result = [o for o in result if o.symbol == symbol]
    if strategy_id:
        # TODO Task 2.3.E: replace _resolve_magic with `from mt5_universal.risk import resolve_magic`
        magic = _resolve_magic(strategy_id, cfg)
        result = [o for o in result if o.magic == magic]

    return ok([_order_to_dict(o, cfg) for o in result])


# ---------------------------------------------------------------------------
# deals
# ---------------------------------------------------------------------------

def deals(
    date_from: datetime,
    date_to: datetime,
    symbol: str | None = None,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Return historical deals in [date_from, date_to].

    Filters in Python by symbol and/or resolved magic (strategy_id).
    ``cfg`` is required when ``strategy_id`` is supplied.
    """
    if strategy_id and cfg is None:
        return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")

    raw = mt5_call("history_deals_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_deals_get returned None.")

    result = list(raw)
    if symbol:
        result = [d for d in result if d.symbol == symbol]
    if strategy_id:
        # TODO Task 2.3.E: replace _resolve_magic with `from mt5_universal.risk import resolve_magic`
        magic = _resolve_magic(strategy_id, cfg)
        result = [d for d in result if d.magic == magic]

    return ok([_deal_to_dict(d) for d in result])


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def stats(
    date_from: datetime,
    date_to: datetime,
    strategy_id: str | None = None,
    cfg: dict | None = None,
) -> dict:
    """Compute performance statistics for deals in [date_from, date_to].

    Optionally scoped to one strategy_id (matched via resolved magic).
    ``cfg`` is required when ``strategy_id`` is supplied.
    Returns zeros (not NaN) when there are no deals.
    """
    if strategy_id and cfg is None:
        return fail("RISK_INVALID_INPUT", "cfg is required when strategy_id is specified.")

    raw = mt5_call("history_deals_get", date_from, date_to)
    if raw is None:
        return fail("MT5_CONNECTION_ERROR", "history_deals_get returned None.")

    deal_list = sorted(raw, key=lambda d: d.time)
    if strategy_id:
        # TODO Task 2.3.E: replace _resolve_magic with `from mt5_universal.risk import resolve_magic`
        magic = _resolve_magic(strategy_id, cfg)
        deal_list = [d for d in deal_list if d.magic == magic]

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
