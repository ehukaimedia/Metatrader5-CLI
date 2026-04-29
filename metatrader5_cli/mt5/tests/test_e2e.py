"""
test_e2e.py — Integration tests for the MT5 CLI.

These tests require a running MetaTrader 5 terminal connected to a **demo
account**.  They are skipped by default and must be opted into explicitly:

    export MT5_DEMO_INTEGRATION=1
    python -m pytest metatrader5_cli/mt5/tests/test_e2e.py -v

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

from metatrader5_cli.mt5.core import (
    account,
    history,
    indicator,
    market,
    order,
    position,
    project,
    rates,
)
from metatrader5_cli.mt5.utils import mt5_backend as bridge

# ---------------------------------------------------------------------------
# Connect to MT5 terminal before safety assertion
# ---------------------------------------------------------------------------

_CFG: dict = project.load()

try:
    bridge.connect(
        login=_CFG.get("login"),
        password=_CFG.get("password"),
        server=_CFG.get("server", ""),
        timeout=_CFG.get("timeout", 10000),
    )
except ConnectionError as _connect_exc:
    pytest.skip(
        f"MT5 terminal not reachable: {_connect_exc}",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Safety guard — abort entire module on a real account
# ---------------------------------------------------------------------------

_acct = account.info()
assert _acct.get("ok"), f"account.info() failed after connect: {_acct}"
assert _acct["data"]["trade_mode"] != "real", (
    "SAFETY ABORT: connected account is a real (live) account. "
    "Integration tests must only run on demo accounts."
)

# ---------------------------------------------------------------------------
# API smoke check (runs without MT5 — verifies callable shapes only)
# ---------------------------------------------------------------------------

def test_core_apis_are_callable():
    """Verify the core API functions exist and are callable."""
    assert callable(account.info)
    assert callable(rates.fetch)
    assert callable(indicator.ema)
    assert callable(market.info)
    assert callable(market.tick)
    assert callable(market.search)
    assert callable(order.place_market)
    assert callable(order.poll_fill)
    assert callable(position.list)
    assert callable(position.close)
    assert callable(history.deals)
    assert callable(project.load)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestE2ERoundTrip:
    """Full connect → trade → close → history round-trip on a demo account."""

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
        r = rates.fetch("USDJPY", "H1", bars=100)
        assert r["ok"] is True, r
        assert len(r["data"]) >= 10

        ema_result = indicator.ema("USDJPY", "H1", period=20, bars=100)
        assert ema_result["ok"] is True, ema_result
        values = ema_result["data"]["values"]
        assert len(values) >= 1
        assert all(isinstance(v["ema"], float) for v in values)

    # ------------------------------------------------------------------
    # Test 3 — market order round-trip (place → poll → close → history)
    # ------------------------------------------------------------------

    def test_market_order_round_trip(self):
        symbol = "USDJPY"

        info = market.info(symbol)
        assert info["ok"] is True, f"market.info failed: {info}"

        tick_result = market.tick(symbol)
        assert tick_result["ok"] is True, f"market.tick failed: {tick_result}"
        ask = tick_result["data"]["ask"]

        # SL placed 150 points below ask for a buy
        point = info["data"].get("point", 0.00001)
        sl = round(ask - 150 * point, 5)

        dryrun = order.dryrun(
            symbol, "buy",
            volume=0.01,
            sl=sl,
            cfg=_CFG,
            is_live_intent=False,
        )
        assert dryrun["ok"] is True, f"dryrun failed: {dryrun}"

        result = order.place_market(
            symbol, "buy",
            volume=0.01,
            sl=sl,
            cfg=_CFG,
            is_live_intent=False,
        )
        assert result["ok"] is True, f"place_market failed: {result}"
        ticket = result["data"]["ticket"]
        assert isinstance(ticket, int)

        fill = order.poll_fill(ticket, timeout_ms=10_000)
        assert fill["ok"] is True
        assert fill["data"]["filled"] is True, "Order was not filled within 10 s"

        time.sleep(1)

        pos_list = position.list(symbol=symbol)
        assert pos_list["ok"] is True
        open_tickets = [p["ticket"] for p in pos_list["data"]]
        assert ticket in open_tickets, (
            f"Ticket {ticket} not in open positions: {open_tickets}"
        )

        close_result = position.close(ticket, is_live_intent=False)
        assert close_result["ok"] is True, f"position.close failed: {close_result}"

        time.sleep(2)

        from datetime import date, timezone, datetime
        today = date.today()
        date_from = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        date_to = datetime.now(tz=timezone.utc)

        deals = history.deals(date_from=date_from, date_to=date_to, symbol=symbol)
        assert deals["ok"] is True, f"history.deals failed: {deals}"
        deal_orders = [d["order"] for d in deals["data"]]
        assert ticket in deal_orders, (
            f"Ticket {ticket} not found in history deals: {deal_orders}"
        )
