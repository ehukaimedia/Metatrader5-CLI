"""Read-only integration smoke tests against a LIVE MetaTrader 5 terminal.

These are the only tests marked ``@pytest.mark.integration``. They are excluded
from the default fast suite (``pytest -m "not integration"``) and from CI, which
has no terminal. Run them manually on Windows with a running, logged-in MT5
terminal:

    pytest -m integration

They are strictly read-only — they never place, modify, or close any order.
"""
import pytest

pytestmark = pytest.mark.integration


def test_connect_and_account_info():
    from mt5_cli import account
    from mt5_cli.bridge import connect
    connect()
    env = account.info()
    assert env["ok"] is True, env
    assert "balance" in env["data"]


def test_market_info_for_eurusd():
    from mt5_cli import market
    from mt5_cli.bridge import connect
    connect()
    env = market.info("EURUSD")
    assert env["ok"] is True, env
    assert env["data"]["bid"] > 0
    assert env["data"]["ask"] >= env["data"]["bid"]
