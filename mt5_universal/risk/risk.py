"""
risk.py — Pre-flight risk checks and position-sizing for mt5_universal.

This module NEVER imports MetaTrader5 directly. All MT5 API access goes
through ``mt5_universal.bridge.mt5_call()``.

Cherry-picked from archive/legacy-mt5/core/risk.py (354 LOC) with the
following intentional divergences from legacy:

1. ``compute_volume_from_risk_pct`` returns an ok({"volume": ...}) envelope
   on success instead of a raw float (spec §3 — same JSON envelope everywhere).
2. ``check_order`` returns ok(None) on success instead of {"ok": True}.
3. Error dicts use fail(code, message) from mt5_universal.reports — no
   mt5_retcode field (risk gates are local checks, not broker responses).
4. Rate limiter uses time.monotonic() (unchanged from legacy) — correct choice
   since wall-clock jumps would break the sliding window.
5. Gate 2 (live) triggers on is_live_intent=False with a REAL account — the
   task-table description is inverted; legacy line 239 is authoritative.
6. Gate 10 (daily loss) triggers on daily_loss(cfg) <= -max_daily_loss — the
   task table's abs() form would block winning days; legacy line 334 is correct.

Gate order matches legacy exactly (verified against legacy lines 229–352):
  Guard 1  RISK_STRATEGY_ID_TOO_LONG  (line 230)
  Guard 2  RISK_LIVE_GATE_BLOCKED     (line 239)
  Guard 3  RISK_SYMBOL_NOT_ALLOWED    (line 249)
  Guard 4  RISK_MAX_LOT_EXCEEDED      (line 255)
  Guard 5a RISK_NO_STOP_LOSS/None     (line 264)
  Guard 5b RISK_NO_STOP_LOSS/distance (line 276)
  Guard 6  RISK_SPREAD_TOO_WIDE       (line 285)
  Guard 7  RISK_HEDGE_BLOCKED         (line 298)
  Guard 8  RISK_MAX_POSITIONS         (line 313)
  Guard 9  RISK_INSUFFICIENT_MARGIN   (line 322)
  Guard 10 RISK_MAX_DAILY_LOSS        (line 334)
  Guard 11 RISK_RATE_LIMIT            (line 343)
"""
from __future__ import annotations

import collections
import hashlib
import logging
import time
from datetime import datetime, timezone

from mt5_universal.bridge import (
    mt5_call,
    ACCOUNT_TRADE_MODE_REAL,
)
from mt5_universal.reports import ok, fail

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

    Three-tier priority (spec §6.7):

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
    is_live_intent:
        Pass True only when the caller has confirmed live trading intent.
        When False AND the account is REAL, Gate 2 blocks the order.
    consume_rate_limit:
        When False the rate-limit window is still checked but no slot is
        consumed. Pass False from dry-run calls so they never reduce real
        order capacity.
    """

    # ------------------------------------------------------------------
    # Guard 1 — strategy_id length (legacy line 230)
    # ------------------------------------------------------------------
    if strategy_id and len(strategy_id) > 31:
        return fail(
            "RISK_STRATEGY_ID_TOO_LONG",
            "strategy_id must be 31 characters or fewer.",
        )

    # ------------------------------------------------------------------
    # Guard 2 — Live gate (legacy line 236–243)
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Guard 3 — Symbol allowlist (legacy line 248–250)
    # ------------------------------------------------------------------
    allowlist: list = cfg.get("symbol_allowlist", [])
    if allowlist and symbol not in allowlist:
        return fail(
            "RISK_SYMBOL_NOT_ALLOWED",
            f"Symbol {symbol!r} is not in the configured allowlist.",
        )

    # ------------------------------------------------------------------
    # Guard 4 — Max lot per order (legacy line 254–259)
    # ------------------------------------------------------------------
    if volume > cfg["max_lot_per_order"]:
        return fail(
            "RISK_MAX_LOT_EXCEEDED",
            f"Volume {volume} exceeds max_lot_per_order {cfg['max_lot_per_order']}.",
        )

    # ------------------------------------------------------------------
    # Guard 5a — SL presence (legacy line 264–265)
    # ------------------------------------------------------------------
    if sl is None:
        return fail("RISK_NO_STOP_LOSS", "A stop-loss price is required.")

    # ------------------------------------------------------------------
    # Guard 5b — SL minimum distance (legacy line 267–280)
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
    entry_price = tick.ask  # spec: use ask for both sides

    sl_distance_points = abs(entry_price - sl) / sym_info.point
    if sl_distance_points < cfg["min_sl_distance_points"]:
        return fail(
            "RISK_NO_STOP_LOSS",
            f"SL distance {sl_distance_points:.1f} pts is below minimum "
            f"{cfg['min_sl_distance_points']} pts.",
        )

    # ------------------------------------------------------------------
    # Guard 6 — Max spread (legacy line 284–290)
    # ------------------------------------------------------------------
    spread_points = (tick.ask - tick.bid) / sym_info.point
    if spread_points > cfg["max_spread_points"]:
        return fail(
            "RISK_SPREAD_TOO_WIDE",
            f"Current spread {spread_points:.1f} pts exceeds "
            f"max_spread_points {cfg['max_spread_points']}.",
        )

    # ------------------------------------------------------------------
    # Guard 7 — Hedge check (legacy line 294–308)
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
    # Guard 8 — Max positions (legacy line 312–317)
    # ------------------------------------------------------------------
    if len(all_positions) >= cfg["max_positions"]:
        return fail(
            "RISK_MAX_POSITIONS",
            f"Already at the maximum of {cfg['max_positions']} open positions.",
        )

    # ------------------------------------------------------------------
    # Guard 9 — Minimum free margin % (legacy line 319–329)
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
    # Guard 10 — Max daily loss (legacy line 333–338)
    # NOTE: triggers on daily_loss <= -max_daily_loss (NOT abs()) — the
    # task table's abs() form would block winning days; legacy is correct.
    # ------------------------------------------------------------------
    if daily_loss(cfg) <= -cfg["max_daily_loss"]:
        return fail(
            "RISK_MAX_DAILY_LOSS",
            f"Daily loss has reached or exceeded the limit of {cfg['max_daily_loss']}.",
        )

    # ------------------------------------------------------------------
    # Guard 11 — Rate limiter: sliding 60-second window (legacy line 342–352)
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
