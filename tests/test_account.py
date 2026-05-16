import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    # Same cache-safe pattern as tests/test_bridge.py — purge bridge submodules so
    # each test rebinds against this test's fake instead of a cached fake.
    for name in list(sys.modules):
        if name == "mt5_universal.bridge" or name.startswith("mt5_universal.bridge."):
            sys.modules.pop(name, None)
        if name == "mt5_universal.account" or name.startswith("mt5_universal.account."):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    fake.account_info.return_value = MagicMock(
        login=88888, balance=10000.0, equity=10012.5,
        margin=0.0, margin_free=10012.5, margin_level=0.0,
        leverage=50, currency="USD", server="Trading.comMarkets-MT5",
        trade_mode=0,  # ACCOUNT_TRADE_MODE_DEMO sentinel; map below sets it to "demo"
    )
    # Bridge needs to know the trade-mode integer values to map them.
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    fake.ACCOUNT_TRADE_MODE_CONTEST = 1
    fake.ACCOUNT_TRADE_MODE_REAL = 2
    # Required bridge constants (from Task 2.2 fixture pattern).
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 10
    fake.ORDER_TYPE_SELL = 11
    fake.TRADE_ACTION_SLTP = 30
    fake.TIMEFRAME_M5 = 500
    fake.COPY_TICKS_ALL = 700
    fake.ORDER_TIME_GTC = 1000
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name == "mt5_universal.bridge" or name.startswith("mt5_universal.bridge."):
            sys.modules.pop(name, None)
        if name == "mt5_universal.account" or name.startswith("mt5_universal.account."):
            sys.modules.pop(name, None)


def test_account_info_returns_envelope(mocked_mt5):
    from mt5_universal.account import info
    env = info()
    assert env["ok"] is True
    assert env["data"]["balance"] == 10000.0
    assert env["data"]["currency"] == "USD"


def test_account_info_maps_trade_mode_demo(mocked_mt5):
    from mt5_universal.account import info
    env = info()
    assert env["data"]["trade_mode"] == "demo"


def test_account_balance_subset(mocked_mt5):
    from mt5_universal.account import balance
    env = balance()
    assert env["ok"] is True
    assert "balance" in env["data"]
    assert "currency" in env["data"]


def test_account_info_fails_when_mt5_returns_none(mocked_mt5):
    mocked_mt5.account_info.return_value = None
    from mt5_universal.account import info
    env = info()
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_CONNECTION_ERROR"
