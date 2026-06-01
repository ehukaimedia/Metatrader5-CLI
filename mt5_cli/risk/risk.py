"""
risk.py — Pre-flight risk checks and position-sizing for mt5_cli.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_cli.bridge.mt5_call()``.

Conventions used throughout this module:

1. ``compute_volume_from_risk_pct`` returns an ok({"volume": ...}) envelope
   on success — the same JSON envelope used everywhere in mt5_cli.
2. ``check_order`` returns ok(None) on success.
3. Error dicts use fail(code, message) from mt5_cli.reports — no
   mt5_retcode field (risk gates are local checks, not broker responses).
4. The rate limiter uses time.monotonic() so that wall-clock jumps cannot
   break the sliding window.
5. Gate 2 (live) triggers on is_live_intent=False with a REAL account.
6. Gate 10 (daily loss) triggers on daily_loss(cfg) <= -max_daily_loss, so a
   winning day never trips the limit.

The full gate order, run in sequence:
  Guard 1  RISK_STRATEGY_ID_TOO_LONG
  Guard 2  RISK_LIVE_GATE_BLOCKED
  Guard 3  RISK_SYMBOL_NOT_ALLOWED
  Guard 4  RISK_MAX_LOT_EXCEEDED
  Guard 5a RISK_NO_STOP_LOSS/None
  Guard 5b RISK_NO_STOP_LOSS/distance
  Guard 6  RISK_SPREAD_TOO_WIDE
  Guard 7  RISK_HEDGE_BLOCKED
  Guard 8  RISK_MAX_POSITIONS
  Guard 9  RISK_INSUFFICIENT_MARGIN
  Guard 10 RISK_MAX_DAILY_LOSS
  Guard 11 RISK_RATE_LIMIT
"""
from __future__ import annotations

import collections
import hashlib
import logging
import os
import time
from datetime import datetime, timezone

from mt5_cli.bridge import (
    mt5_call,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_cli.reports import ok, fail

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_rate_limiter: collections.deque = collections.deque()

# Track which strategy_ids have already been logged (for auto-derived magic).
_logged_strategy_ids: set[str] = set()

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test-only helper: reset rate limiter between tests
# ---------------------------------------------------------------------------


def _reset_rate_limiter() -> None:
    """Clear the sliding-window deque. Call in pytest fixtures for test isolation."""
    _rate_limiter.clear()


# ---------------------------------------------------------------------------
# resolve_magic
# ---------------------------------------------------------------------------


def resolve_magic(strategy_id: str | None, cfg: dict) -> int:
    """Return the magic number for the given strategy_id.

    Three-tier priority:

    1. ``strategy_id`` is truthy AND found in ``cfg["strategy_ids"]``
       → return mapped value (must be < 100 000 to avoid auto-derive collision).
    2. ``strategy_id`` is truthy but NOT in the map
       → auto-derive from SHA-256, range [100 000, 180 000).
    3. ``strategy_id`` is None/empty → return ``cfg["magic"]``.

    Raises:
        ValueError: when a configured magic >= 100 000 (collision guard).
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

        # Auto-derive via SHA-256
        magic = (
            int(hashlib.sha256(strategy_id.encode("utf-8")).hexdigest()[:8], 16)
            % 80000
            + 100000
        )
        if strategy_id not in _logged_strategy_ids:
            _log.info("Auto-derived magic %d for strategy_id %r", magic, strategy_id)
            _logged_strategy_ids.add(strategy_id)
        return magic

    default_magic = int(cfg.get("magic", 88888))
    if default_magic >= 100000:
        raise ValueError(
            f"Configured default magic {default_magic} must be < 100000 "
            "to avoid collision with auto-derived range [100000, 180000)."
        )
    return default_magic


# ---------------------------------------------------------------------------
# compute_volume_from_risk_pct
# ---------------------------------------------------------------------------


def compute_volume_from_risk_pct(
    symbol: str,
    risk_pct: float,
    entry_price: float,
    sl_price: float,
    cfg: dict,  # noqa: ARG001 (reserved for future per-strategy overrides)
) -> dict:
    """Return an ok envelope with ``volume`` sized to risk ``risk_pct``% of equity.

    Uses ``entry_price`` passed in (NOT a live tick) so pending-order sizing
    is correct.

    Returns:
        ok({"volume": float}) on success.
        fail("RISK_INVALID_INPUT", ...) on bad inputs.
    Does NOT raise.
    """
    symbol_info = mt5_call("symbol_info", symbol)
    account_info = mt5_call("account_info")

    # Guard: bad symbol or account
    if symbol_info is None or account_info is None:
        return fail(
            "RISK_INVALID_INPUT",
            "Could not retrieve symbol_info or account_info from MT5.",
        )

    point = symbol_info.point
    tick_value = symbol_info.trade_tick_value
    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max
    volume_step = symbol_info.volume_step
    equity = account_info.equity

    if point == 0:
        return fail(
            "RISK_INVALID_INPUT",
            "Symbol point size is zero — cannot compute SL distance.",
        )

    sl_distance_points = abs(entry_price - sl_price) / point

    if sl_distance_points == 0:
        return fail(
            "RISK_INVALID_INPUT",
            "SL distance is zero — entry and SL prices are equal.",
        )

    if tick_value == 0:
        return fail(
            "RISK_INVALID_INPUT",
            "Symbol tick value is zero — cannot size position.",
        )

    volume = (equity * risk_pct / 100) / (sl_distance_points * tick_value)

    # Round to volume_step
    if volume_step > 0:
        volume = round(volume / volume_step) * volume_step

    # Clamp to [volume_min, volume_max]
    volume = max(volume_min, min(volume_max, volume))

    return ok({"volume": round(volume, 8)})


# ---------------------------------------------------------------------------
# daily_loss
# ---------------------------------------------------------------------------


def daily_loss(cfg: dict) -> float:  # noqa: ARG001 (cfg reserved for future use)
    """Return the signed net P&L for today (UTC).

    Negative value means a losing day. Combines:
    * Realized P&L: closed deals since 00:00 UTC today (profit + commission + swap).
    * Floating P&L: open positions' unrealized profit.

    Uses ``datetime.now(timezone.utc)`` (NOT the deprecated
    ``datetime.utcnow()``) to stay compatible with Python 3.13+.
    """
    now = datetime.now(timezone.utc)
    date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)

    deals = mt5_call("history_deals_get", date_from, now) or []
    positions = mt5_call("positions_get") or []

    realized: float = sum(
        deal.profit + deal.commission + deal.swap for deal in deals
    )
    floating: float = sum(pos.profit for pos in positions)

    return realized + floating


# ---------------------------------------------------------------------------
# check_order — the 11-gate gauntlet
# ---------------------------------------------------------------------------


def check_order(
    *,
    symbol: str,
    side: str,
    volume: float,
    sl: float | None,
    tp: float | None = None,  # accepted for API forward-compat, not used in gates
    entry_price: float | None = None,
    strategy_id: str | None = None,
    cfg: dict,
    is_live_intent: bool,
    consume_rate_limit: bool = True,
) -> dict:
    """Master pre-flight risk check.

    Returns ok(None) when all gates pass, or a fail(...) envelope on the
    first gate that trips.

    IMPORTANT: callers must call ``ensure_symbol(symbol)`` BEFORE invoking
    this function. ``check_order`` does NOT call ``ensure_symbol`` itself.

    Parameters
    ----------
    symbol:
        The instrument to trade.
    side:
        "buy" or "sell" (case-insensitive).
    volume:
        Requested lot size.
    sl:
        Stop-loss price, or None if not supplied.
    tp:
        Take-profit price (optional, accepted for API compat, not gated).
    strategy_id:
        Optional strategy identifier (max 31 chars).
    cfg:
        Effective configuration dict.
    entry_price:
        Optional expected execution price. For PENDING orders (limit /
        stop), pass the order's trigger price so the SL-distance gate
        is measured from the actual entry, not from the current ask
        (which can be far from the trigger). When None, the current
        symbol_info_tick.ask is used (correct for market orders).
    is_live_intent:
        Pass True only when the caller has confirmed live trading intent.
        Combined with cfg["live"] and the MT5_LIVE env var, this forms
        the live-trading triple lock — see Guard 2.
    consume_rate_limit:
        When False the rate-limit window is still checked but no slot is
        consumed. Pass False from dry-run calls so they never reduce real
        order capacity.
    """

    # ------------------------------------------------------------------
    # Guard 1 — strategy_id length
    # ------------------------------------------------------------------
    if strategy_id and len(strategy_id) > 31:
        return fail(
            "RISK_STRATEGY_ID_TOO_LONG",
            "strategy_id must be 31 characters or fewer.",
        )

    # ------------------------------------------------------------------
    # Guard 2 — Live trading triple lock
    # When account is REAL, ALL THREE of these must be armed:
    #   1. cfg["live"] is True
    #   2. MT5_LIVE env var == "1"
    #   3. is_live_intent=True (the CLI/library caller's --live proxy)
    # Library is a first-class surface; the gate enforces all three here
    # so direct mt5_cli.orders.place_market(...) calls cannot bypass.
    # ------------------------------------------------------------------
    account_info = mt5_call("account_info")
    if account_info is None:
        return fail(
            "RISK_INVALID_INPUT",
            "account_info unavailable — MT5 may be disconnected.",
        )
    if account_info.trade_mode == ACCOUNT_TRADE_MODE_REAL:
        if not is_live_intent:
            return fail(
                "RISK_LIVE_GATE_BLOCKED",
                "This is a live (real-money) account. Pass is_live_intent=True "
                "(--live on the CLI) to confirm intentional live trading.",
            )
        if not cfg.get("live"):
            return fail(
                "RISK_LIVE_GATE_BLOCKED",
                'Live trading requires cfg["live"]=true. Set it in your config '
                "file or pass overrides={'live': True} to load().",
            )
        if os.environ.get("MT5_LIVE") != "1":
            return fail(
                "RISK_LIVE_GATE_BLOCKED",
                "Live trading requires MT5_LIVE=1 in the environment. Export "
                "MT5_LIVE=1 (or set it in your shell profile) to arm live trading.",
            )

    # ------------------------------------------------------------------
    # Guard 3 — Symbol allowlist
    # ------------------------------------------------------------------
    allowlist: list = cfg.get("symbol_allowlist", [])
    if allowlist and symbol not in allowlist:
        return fail(
            "RISK_SYMBOL_NOT_ALLOWED",
            f"Symbol {symbol!r} is not in the configured allowlist.",
        )

    # ------------------------------------------------------------------
    # Guard 4 — Max lot per order
    # ------------------------------------------------------------------
    if volume > cfg["max_lot_per_order"]:
        return fail(
            "RISK_MAX_LOT_EXCEEDED",
            f"Volume {volume} exceeds max_lot_per_order {cfg['max_lot_per_order']}.",
        )

    # ------------------------------------------------------------------
    # Guard 5a — SL presence
    # ------------------------------------------------------------------
    if sl is None:
        return fail("RISK_NO_STOP_LOSS", "A stop-loss price is required.")

    # ------------------------------------------------------------------
    # Guard 5b — SL minimum distance
    # ------------------------------------------------------------------
    tick = mt5_call("symbol_info_tick", symbol)
    sym_info = mt5_call("symbol_info", symbol)
    if tick is None:
        return fail(
            "RISK_INVALID_INPUT",
            "No tick data for symbol — quote may be unavailable.",
        )
    if sym_info is None or sym_info.point == 0:
        return fail(
            "RISK_INVALID_INPUT",
            "Symbol info unavailable or point size is zero.",
        )
    # For market orders (entry_price=None), use the current ask as the
    # entry proxy. For pending orders (limit/stop), the caller passes the
    # trigger price so SL distance is measured from the actual entry, not
    # from the current ask (which can be far from the trigger).
    sl_reference_price = entry_price if entry_price is not None else tick.ask

    sl_distance_points = abs(sl_reference_price - sl) / sym_info.point
    if sl_distance_points < cfg["min_sl_distance_points"]:
        return fail(
            "RISK_NO_STOP_LOSS",
            f"SL distance {sl_distance_points:.1f} pts is below minimum "
            f"{cfg['min_sl_distance_points']} pts.",
        )

    # ------------------------------------------------------------------
    # Guard 6 — Max spread
    # ------------------------------------------------------------------
    spread_points = (tick.ask - tick.bid) / sym_info.point
    if spread_points > cfg["max_spread_points"]:
        return fail(
            "RISK_SPREAD_TOO_WIDE",
            f"Current spread {spread_points:.1f} pts exceeds "
            f"max_spread_points {cfg['max_spread_points']}.",
        )

    # ------------------------------------------------------------------
    # Guard 7 — Hedge check
    # ------------------------------------------------------------------
    all_positions = mt5_call("positions_get") or []
    if not cfg.get("allow_hedging", False):
        side_lower = side.lower()
        for pos in all_positions:
            if pos.symbol != symbol:
                continue
            # pos.type: 0=BUY, 1=SELL (raw MT5 integers)
            existing_is_buy = pos.type == 0
            new_is_buy = side_lower == "buy"
            if existing_is_buy != new_is_buy:
                return fail(
                    "RISK_HEDGE_BLOCKED",
                    f"Hedging is disabled. An opposing position already exists for {symbol!r}.",
                )

    # ------------------------------------------------------------------
    # Guard 8 — Max positions
    # ------------------------------------------------------------------
    if len(all_positions) >= cfg["max_positions"]:
        return fail(
            "RISK_MAX_POSITIONS",
            f"Already at the maximum of {cfg['max_positions']} open positions.",
        )

    # ------------------------------------------------------------------
    # Guard 9 — Minimum free margin %
    # ------------------------------------------------------------------
    if account_info.equity <= 0:
        return fail("RISK_INSUFFICIENT_MARGIN", "Account equity is zero or negative.")
    free_margin_pct = account_info.margin_free / account_info.equity * 100
    if free_margin_pct < cfg["min_free_margin_pct"]:
        return fail(
            "RISK_INSUFFICIENT_MARGIN",
            f"Free margin {free_margin_pct:.1f}% is below the required "
            f"{cfg['min_free_margin_pct']}%.",
        )

    # ------------------------------------------------------------------
    # Guard 10 — Max daily loss
    # NOTE: triggers on daily_loss <= -max_daily_loss (NOT abs()), so a
    # winning day never trips the limit.
    # ------------------------------------------------------------------
    if daily_loss(cfg) <= -cfg["max_daily_loss"]:
        return fail(
            "RISK_MAX_DAILY_LOSS",
            f"Daily loss has reached or exceeded the limit of {cfg['max_daily_loss']}.",
        )

    # ------------------------------------------------------------------
    # Guard 11 — Rate limiter: sliding 60-second window
    # Uses time.monotonic() — immune to wall-clock jumps.
    # ------------------------------------------------------------------
    now = time.monotonic()
    while _rate_limiter and now - _rate_limiter[0] > 60:
        _rate_limiter.popleft()
    if len(_rate_limiter) >= cfg["max_orders_per_minute"]:
        return fail(
            "RISK_RATE_LIMIT",
            f"Order rate limit of {cfg['max_orders_per_minute']} orders/minute exceeded.",
        )
    if consume_rate_limit:
        _rate_limiter.append(now)

    return ok(None)
