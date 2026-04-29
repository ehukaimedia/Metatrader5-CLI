"""
test_e2e.py — Integration tests for the MT5 CLI.

These tests require a running MetaTrader 5 terminal connected to a **demo
account**.  They are skipped by default and must be opted into explicitly:

    export MT5_DEMO_INTEGRATION=1
    python -m pytest cli_anything/mt5/tests/test_e2e.py -v

NEVER run these tests against a real (live) account.  The module-level safety
guard aborts the entire module if the connected account is live.
"""
from __future__ import annotations

import os
import time
import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard
# ---------------------------------------------------------------------------

if os.environ.get("MT5_DEMO_INTEGRATION") != "1":
    pytest.skip(
        "Integration tests disabled — set MT5_DEMO_INTEGRATION=1 to enable.",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Imports (only reached when MT5_DEMO_INTEGRATION=1)
# ---------------------------------------------------------------------------

from cli_anything.mt5.core import account, analyze, history, market, order, position, rates

# ---------------------------------------------------------------------------
# Safety guard — abort entire module on a real account
# ---------------------------------------------------------------------------

_acct = account.info()
assert _acct.get("ok"), f"account.info() failed: {_acct}"
assert _acct["data"]["trade_mode"] != "real", (
    "SAFETY ABORT: connected account is a real (live) account. "
    "Integration tests must only run on demo accounts."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CFG: dict = {}   # empty cfg — integration tests rely on terminal defaults


def _load_cfg() -> dict:
    """Load config from the default path, fall back to empty dict."""
    try:
        from cli_anything.mt5.core import config as cfg_module
        return cfg_module.load() or {}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestE2ERoundTrip:
    """Full connect → trade → close → history round-trip on a demo account."""

    def setup_method(self):
        self.cfg = _load_cfg()

    # ------------------------------------------------------------------
    # Test 1 — account info readable
    # ------------------------------------------------------------------

    def test_account_info_returns_balance(self):
        result = account.info()
        assert result["ok"] is True
        data = result["data"]
        assert isinstance(data["balance"], float)
        assert data["balance"] > 0
        assert data["trade_mode"] in (0, "demo")  # demo only

    # ------------------------------------------------------------------
    # Test 2 — fetch rates and compute EMA
    # ------------------------------------------------------------------

    def test_rates_and_ema(self):
        # Fetch H1 rates for EURUSD (100 bars)
        r = rates.get("EURUSD", "H1", bars=100)
        assert r["ok"] is True, r
        assert len(r["data"]) >= 10

        # Compute EMA on close prices
        ema_result = analyze.indicator("EURUSD", "H1", "EMA", period=20, bars=100)
        assert ema_result["ok"] is True, ema_result
        values = ema_result["data"]["values"]
        assert len(values) >= 1
        assert all(isinstance(v, float) for v in values)

    # ------------------------------------------------------------------
    # Test 3 — market order round-trip (place → poll → close → history)
    # ------------------------------------------------------------------

    def test_market_order_round_trip(self):
        symbol = "EURUSD"

        # Verify symbol is available
        info = market.info(symbol)
        assert info["ok"] is True, f"market.info failed: {info}"

        tick = market.tick(symbol)
        assert tick["ok"] is True, f"market.tick failed: {tick}"
        ask = tick["data"]["ask"]
        bid = tick["data"]["bid"]

        # SL placed 50 points below ask for a buy
        point = info["data"].get("point", 0.00001)
        sl = round(ask - 150 * point, 5)

        # Place a 0.01-lot demo buy
        result = order.place_market(
            symbol, "buy",
            volume=0.01,
            sl=sl,
            cfg=self.cfg,
            is_live_intent=False,
        )
        assert result["ok"] is True, f"place_market failed: {result}"
        ticket = result["data"]["ticket"]
        assert isinstance(ticket, int)

        # Poll until fill confirmed (up to 10 s)
        fill = order.poll_fill(ticket, timeout_ms=10_000)
        assert fill["ok"] is True
        assert fill["data"]["filled"] is True, "Order was not filled within 10 s"

        # Wait briefly for position to appear
        time.sleep(1)

        # Confirm position is open
        pos_list = position.list_open(symbol=symbol)
        assert pos_list["ok"] is True
        open_tickets = [p["ticket"] for p in pos_list["data"]]
        assert ticket in open_tickets, f"Ticket {ticket} not in open positions: {open_tickets}"

        # Close the position
        close_result = position.close(ticket, is_live_intent=False)
        assert close_result["ok"] is True, f"position.close failed: {close_result}"

        # Brief pause so history has time to record the deal
        time.sleep(2)

        # Verify the deal appears in history
        from datetime import date, timedelta, timezone, datetime
        today = date.today()
        date_from = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        date_to = datetime.now(tz=timezone.utc)

        deals = history.deals(date_from=date_from, date_to=date_to, symbol=symbol)
        assert deals["ok"] is True, f"history.deals failed: {deals}"
        deal_orders = [d["order"] for d in deals["data"]]
        assert ticket in deal_orders, (
            f"Ticket {ticket} not found in history deals: {deal_orders}"
        )
