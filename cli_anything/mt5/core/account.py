"""
account.py — Account snapshot and risk status for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()``.
"""
from __future__ import annotations

from cli_anything.mt5.utils import mt5_backend as bridge
from cli_anything.mt5.core import risk as risk_module

# Map raw MT5 trade_mode integers to human-readable strings (spec §7.1).
_TRADE_MODE_MAP: dict = {
    bridge.ACCOUNT_TRADE_MODE_DEMO: "demo",
    bridge.ACCOUNT_TRADE_MODE_CONTEST: "contest",
    bridge.ACCOUNT_TRADE_MODE_REAL: "real",
}


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _account_info_or_fail():
    """Return (AccountInfo, None) or (None, error_dict)."""
    acc = bridge.mt5_call("account_info")
    if acc is None:
        return None, _fail(
            "MT5_CONNECTION_ERROR",
            "account_info returned None — MT5 may be disconnected.",
        )
    return acc, None


def info() -> dict:
    """Return full account snapshot (spec §6.1)."""
    acc, err = _account_info_or_fail()
    if err:
        return err
    return {
        "ok": True,
        "data": {
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
        },
    }


def balance() -> dict:
    """Return quick balance subset (spec §6.1)."""
    acc, err = _account_info_or_fail()
    if err:
        return err
    return {
        "ok": True,
        "data": {
            "balance": acc.balance,
            "equity": acc.equity,
            "currency": acc.currency,
        },
    }


def risk(cfg: dict) -> dict:
    """Return risk envelope status (spec §6.1).

    ``safe_to_trade`` is True iff a minimal subset of risk guards pass:
    positions count, daily-loss cap, and free-margin percentage.  It does
    NOT run the full ``check_order`` (which requires a specific symbol and
    volume); it is an at-a-glance signal only.
    """
    acc, err = _account_info_or_fail()
    if err:
        return err

    positions = bridge.mt5_call("positions_get") or []
    positions_used = len(positions)
    daily_loss_used = risk_module.daily_loss(cfg)

    positions_ok = positions_used < cfg["max_positions"]
    daily_loss_ok = daily_loss_used > -cfg["max_daily_loss"]
    if acc.equity <= 0:
        margin_ok = False
    else:
        margin_ok = acc.margin_free / acc.equity * 100 >= cfg["min_free_margin_pct"]

    return {
        "ok": True,
        "data": {
            "max_positions": cfg["max_positions"],
            "max_daily_loss": cfg["max_daily_loss"],
            "daily_loss_used": daily_loss_used,
            "positions_used": positions_used,
            "safe_to_trade": positions_ok and daily_loss_ok and margin_ok,
            "currency": acc.currency,
        },
    }
