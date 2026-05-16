"""
account.py — Account snapshot primitives for mt5_universal.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_call()`` via the bridge.

Pattern-ported from archive/legacy-mt5/core/account.py; imports and envelope
construction rewritten for mt5_universal.
"""
from __future__ import annotations

from mt5_universal.bridge import (
    mt5_call,
    ACCOUNT_TRADE_MODE_DEMO,
    ACCOUNT_TRADE_MODE_CONTEST,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_universal.reports import ok, fail

# Map raw MT5 trade_mode integers to human-readable strings.
_TRADE_MODE_MAP: dict = {
    ACCOUNT_TRADE_MODE_DEMO: "demo",
    ACCOUNT_TRADE_MODE_CONTEST: "contest",
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


# TODO Task 2.3.E: add risk(cfg) once mt5_universal.risk.daily_loss exists.
# Depends on mt5_universal.risk.daily_loss which lands in Task 2.3.E.
