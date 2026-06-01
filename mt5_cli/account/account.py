"""
account.py — Account snapshot primitives for mt5_cli.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_call()`` via the bridge.
"""
from __future__ import annotations

from mt5_cli.bridge import (
    mt5_call,
    ACCOUNT_TRADE_MODE_DEMO,
    ACCOUNT_TRADE_MODE_CONTEST,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_cli.reports import ok, fail
from mt5_cli.risk import daily_loss

# Map raw MT5 trade_mode integers to "demo" or "real" only.
# CONTEST accounts (broker competitions with simulated funds) collapse to "demo"
# since they don't risk real money — agents and UI only need the demo/real
# distinction. The live gate in risk.check_order still discriminates strictly:
# only ACCOUNT_TRADE_MODE_REAL triggers the gate.
_TRADE_MODE_MAP: dict[int, str] = {
    ACCOUNT_TRADE_MODE_DEMO: "demo",
    ACCOUNT_TRADE_MODE_CONTEST: "demo",
    ACCOUNT_TRADE_MODE_REAL: "real",
}


def _account_info_or_fail():
    """Return (AccountInfo, None) or (None, error_dict)."""
    acc = mt5_call("account_info")
    if acc is None:
        return None, fail(
            "MT5_CONNECTION_ERROR",
            "account_info returned None — MT5 may be disconnected.",
        )
    return acc, None


def info() -> dict:
    """Return full account snapshot."""
    acc, err = _account_info_or_fail()
    if err:
        return err
    return ok({
        "login": acc.login,
        "name": acc.name,
        "server": acc.server,
        "currency": acc.currency,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "margin_level": acc.margin_level,
        "leverage": acc.leverage,
        "profit": acc.profit,
        "trade_mode": _TRADE_MODE_MAP.get(acc.trade_mode, str(acc.trade_mode)),
        "trade_allowed": acc.trade_allowed,
    })


def balance() -> dict:
    """Return quick balance subset."""
    acc, err = _account_info_or_fail()
    if err:
        return err
    return ok({
        "balance": acc.balance,
        "equity": acc.equity,
        "currency": acc.currency,
    })


def risk(cfg: dict) -> dict:
    """Return risk envelope status.

    ``safe_to_trade`` is True iff a minimal subset of risk guards pass:
    positions count, daily-loss cap, and free-margin percentage.  It does
    NOT run the full ``check_order`` (which requires a specific symbol and
    volume); it is an at-a-glance signal only.
    """
    acc, err = _account_info_or_fail()
    if err:
        return err

    positions = mt5_call("positions_get") or []
    positions_used = len(positions)
    daily_loss_used = daily_loss(cfg)

    positions_ok = positions_used < cfg["max_positions"]
    daily_loss_ok = daily_loss_used > -cfg["max_daily_loss"]
    if acc.equity <= 0:
        margin_ok = False
    else:
        margin_ok = acc.margin_free / acc.equity * 100 >= cfg["min_free_margin_pct"]

    return ok({
        "max_positions": cfg["max_positions"],
        "max_daily_loss": cfg["max_daily_loss"],
        "daily_loss_used": daily_loss_used,
        "positions_used": positions_used,
        "safe_to_trade": positions_ok and daily_loss_ok and margin_ok,
        "currency": acc.currency,
    })
