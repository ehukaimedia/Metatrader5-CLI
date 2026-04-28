"""
risk.py — Pre-flight risk checks and position-sizing for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  All MT5 API access goes
through ``bridge.mt5_call()``.
"""
from __future__ import annotations

import collections
import hashlib
import logging
import time
from datetime import datetime, timezone

from cli_anything.mt5.utils import mt5_backend as bridge

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_rate_limiter: collections.deque = collections.deque()

# Track which strategy_ids have already been logged (for auto-derived magic).
_logged_strategy_ids: set[str] = set()

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# resolve_magic
# ---------------------------------------------------------------------------


def resolve_magic(strategy_id: str | None, cfg: dict) -> int:
    """Return the magic number for the given strategy_id.

    Three-tier priority (spec §6.7):

    1. ``strategy_id`` is truthy AND found in ``cfg["strategy_ids"]``
       → return mapped value (must be < 100 000).
    2. ``strategy_id`` is truthy but NOT in the map
       → auto-derive from SHA-256, range [100 000, 180 000).
    3. ``strategy_id`` is None/empty → return ``cfg["magic"]``.
    """
    if strategy_id:
        strategy_ids: dict = cfg.get("strategy_ids", {})
        if strategy_id in strategy_ids:
            mapped = int(strategy_ids[strategy_id])
            if mapped >= 100000:
                raise ValueError(
                    f"Configured magic {mapped} for {strategy_id!r} must be < 100000 "
                    f"to avoid collision with auto-derived range [100000, 180000)."
                )
            return mapped

        # Auto-derive
        magic = int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000
        if strategy_id not in _logged_strategy_ids:
            _log.info("Auto-derived magic %d for strategy_id %r", magic, strategy_id)
            _logged_strategy_ids.add(strategy_id)
        return magic

    return int(cfg["magic"])


# ---------------------------------------------------------------------------
# compute_volume_from_risk_pct
# ---------------------------------------------------------------------------


def compute_volume_from_risk_pct(
    symbol: str,
    risk_pct: float,
    entry_price: float,
    sl_price: float,
    cfg: dict,
) -> float | dict:
    """Return lot size that risks ``risk_pct``% of account equity.

    Uses ``entry_price`` passed in (NOT a live tick) so pending-order sizing
    is correct.

    Returns a ``float`` on success or an error dict on invalid inputs.
    Does NOT raise.
    """
    symbol_info = bridge.mt5_call("symbol_info", symbol)
    account_info = bridge.mt5_call("account_info")

    # Guard: bad symbol or account
    if symbol_info is None or account_info is None:
        return {
            "ok": False,
            "error": {
                "code": "RISK_INVALID_INPUT",
                "message": "Could not retrieve symbol_info or account_info from MT5.",
                "mt5_retcode": None,
            },
        }

    point = symbol_info.point
    tick_value = symbol_info.trade_tick_value
    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max
    volume_step = symbol_info.volume_step
    equity = account_info.equity

    if point == 0:
        return {
            "ok": False,
            "error": {
                "code": "RISK_INVALID_INPUT",
                "message": "Symbol point size is zero — cannot compute SL distance.",
                "mt5_retcode": None,
            },
        }

    sl_distance_points = abs(entry_price - sl_price) / point

    if sl_distance_points == 0:
        return {
            "ok": False,
            "error": {
                "code": "RISK_INVALID_INPUT",
                "message": "SL distance is zero — entry and SL prices are equal.",
                "mt5_retcode": None,
            },
        }

    if tick_value == 0:
        return {
            "ok": False,
            "error": {
                "code": "RISK_INVALID_INPUT",
                "message": "Symbol tick value is zero — cannot size position.",
                "mt5_retcode": None,
            },
        }

    volume = (equity * risk_pct / 100) / (sl_distance_points * tick_value)

    # Round to volume_step
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step

    # Clamp to [volume_min, volume_max]
    volume = max(volume_min, min(volume_max, volume))

    return volume


# ---------------------------------------------------------------------------
# daily_loss
# ---------------------------------------------------------------------------


def daily_loss(cfg: dict) -> float:  # noqa: ARG001 (cfg reserved for future use)
    """Return the signed net P&L for today (UTC).

    Negative value means a losing day.  Combines:
    * Realized P&L: closed deals since 00:00 UTC today.
    * Floating P&L: open positions' unrealized profit.

    Uses ``datetime.now(timezone.utc)`` (NOT the deprecated
    ``datetime.utcnow()``) to stay compatible with Python 3.13+.
    """
    now = datetime.now(timezone.utc)
    date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)

    deals = bridge.mt5_call("history_deals_get", date_from, now) or []
    positions = bridge.mt5_call("positions_get") or []

    realized: float = sum(
        deal.profit + deal.commission + deal.swap for deal in deals
    )
    floating: float = sum(pos.profit for pos in positions)

    return realized + floating


# ---------------------------------------------------------------------------
# check_order
# ---------------------------------------------------------------------------


def check_order(
    symbol: str,
    side: str,
    volume: float,
    sl: float | None,
    strategy_id: str | None,
    cfg: dict,
    *,
    is_live_intent: bool,
) -> dict:
    """Master pre-flight risk check.  Returns ``{"ok": True}`` or an error dict.

    IMPORTANT: callers must call ``bridge.ensure_symbol(symbol)`` BEFORE
    invoking this function.  ``check_order`` does NOT call ``ensure_symbol``
    itself.

    Parameters
    ----------
    symbol:
        The instrument to trade.
    side:
        "buy" or "sell" (case-insensitive).
    volume:
        Requested lot size.
    sl:
        Stop-loss price, or ``None`` if not supplied.
    strategy_id:
        Optional strategy identifier (max 31 chars).
    cfg:
        Effective configuration dict.
    is_live_intent:
        Pre-computed three-way AND: ``cfg["live"] & --live flag & MT5_LIVE=="1"``.
        When True the live-gate guard passes unconditionally.
    """

    def _fail(code: str, message: str) -> dict:
        return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}

    # ------------------------------------------------------------------
    # Guard 1 — strategy_id length
    # ------------------------------------------------------------------
    if strategy_id and len(strategy_id) > 31:
        return _fail("RISK_STRATEGY_ID_TOO_LONG", "strategy_id must be 31 characters or fewer.")

    # ------------------------------------------------------------------
    # Guard 2 — Live gate
    # ------------------------------------------------------------------
    account_info = bridge.mt5_call("account_info")
    if account_info is None:
        return _fail("RISK_INVALID_INPUT", "account_info unavailable — MT5 may be disconnected.")
    if not is_live_intent and account_info.trade_mode == bridge.ACCOUNT_TRADE_MODE_REAL:
        return _fail(
            "RISK_LIVE_GATE_BLOCKED",
            "This is a live (real-money) account.  Pass --live to confirm intentional live trading.",
        )

    # ------------------------------------------------------------------
    # Guard 3 — Symbol allowlist
    # ------------------------------------------------------------------
    allowlist: list = cfg.get("symbol_allowlist", [])
    if allowlist and symbol not in allowlist:
        return _fail("RISK_SYMBOL_NOT_ALLOWED", f"Symbol {symbol!r} is not in the configured allowlist.")

    # ------------------------------------------------------------------
    # Guard 4 — Max lot per order
    # ------------------------------------------------------------------
    if volume > cfg["max_lot_per_order"]:
        return _fail(
            "RISK_MAX_LOT_EXCEEDED",
            f"Volume {volume} exceeds max_lot_per_order {cfg['max_lot_per_order']}.",
        )

    # ------------------------------------------------------------------
    # Guard 5 — SL presence + minimum distance
    # ------------------------------------------------------------------
    if sl is None:
        return _fail("RISK_NO_STOP_LOSS", "A stop-loss price is required.")

    tick = bridge.mt5_call("symbol_info_tick", symbol)
    sym_info = bridge.mt5_call("symbol_info", symbol)
    if tick is None:
        return _fail("RISK_INVALID_INPUT", "No tick data for symbol — quote may be unavailable.")
    if sym_info is None or sym_info.point == 0:
        return _fail("RISK_INVALID_INPUT", "Symbol info unavailable or point size is zero.")
    entry_price = tick.ask  # spec: use ask for both sides

    sl_distance_points = abs(entry_price - sl) / sym_info.point
    if sl_distance_points < cfg["min_sl_distance_points"]:
        return _fail(
            "RISK_NO_STOP_LOSS",
            f"SL distance {sl_distance_points:.1f} pts is below minimum {cfg['min_sl_distance_points']} pts.",
        )

    # ------------------------------------------------------------------
    # Guard 6 — Max spread
    # ------------------------------------------------------------------
    spread_points = (tick.ask - tick.bid) / sym_info.point
    if spread_points > cfg["max_spread_points"]:
        return _fail(
            "RISK_SPREAD_TOO_WIDE",
            f"Current spread {spread_points:.1f} pts exceeds max_spread_points {cfg['max_spread_points']}.",
        )

    # ------------------------------------------------------------------
    # Guard 7 — Hedge check
    # ------------------------------------------------------------------
    all_positions = bridge.mt5_call("positions_get") or []
    if not cfg.get("allow_hedging", False):
        side_lower = side.lower()
        for pos in all_positions:
            if pos.symbol != symbol:
                continue
            # pos.type: 0 = BUY, 1 = SELL (raw MT5 integers)
            existing_is_buy = pos.type == 0
            new_is_buy = side_lower == "buy"
            if existing_is_buy != new_is_buy:
                return _fail(
                    "RISK_HEDGE_BLOCKED",
                    f"Hedging is disabled.  An opposing position already exists for {symbol!r}.",
                )

    # ------------------------------------------------------------------
    # Guard 8 — Max positions
    # ------------------------------------------------------------------
    if len(all_positions) >= cfg["max_positions"]:
        return _fail(
            "RISK_MAX_POSITIONS",
            f"Already at the maximum of {cfg['max_positions']} open positions.",
        )

    # ------------------------------------------------------------------
    # Guard 9 — Minimum free margin %
    # ------------------------------------------------------------------
    if account_info.equity <= 0:
        return _fail("RISK_INSUFFICIENT_MARGIN", "Account equity is zero or negative.")
    free_margin_pct = account_info.free_margin / account_info.equity * 100
    if free_margin_pct < cfg["min_free_margin_pct"]:
        return _fail(
            "RISK_INSUFFICIENT_MARGIN",
            f"Free margin {free_margin_pct:.1f}% is below the required {cfg['min_free_margin_pct']}%.",
        )

    # ------------------------------------------------------------------
    # Guard 10 — Max daily loss
    # ------------------------------------------------------------------
    if daily_loss(cfg) <= -cfg["max_daily_loss"]:
        return _fail(
            "RISK_MAX_DAILY_LOSS",
            f"Daily loss has reached or exceeded the limit of {cfg['max_daily_loss']}.",
        )

    # ------------------------------------------------------------------
    # Guard 11 — Rate limiter (sliding 60-second window; last gate)
    # ------------------------------------------------------------------
    now = time.monotonic()
    while _rate_limiter and now - _rate_limiter[0] > 60:
        _rate_limiter.popleft()
    if len(_rate_limiter) >= cfg["max_orders_per_minute"]:
        return _fail(
            "RISK_RATE_LIMIT",
            f"Order rate limit of {cfg['max_orders_per_minute']} orders/minute exceeded.",
        )
    _rate_limiter.append(now)  # consume slot only after all guards pass

    return {"ok": True}
