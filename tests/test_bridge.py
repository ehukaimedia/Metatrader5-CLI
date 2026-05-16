import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    # The bridge imports MetaTrader5 at module import time. Purge bridge modules
    # so each test binds to this test's fake instead of a cached earlier fake.
    for name in list(sys.modules):
        if name == "mt5_universal.bridge" or name.startswith("mt5_universal.bridge."):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    fake.symbol_select.return_value = True
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 10
    fake.ORDER_TYPE_SELL = 11
    fake.TRADE_ACTION_SLTP = 30
    fake.TIMEFRAME_M5 = 500
    fake.COPY_TICKS_ALL = 700
    fake.ACCOUNT_TRADE_MODE_DEMO = 900
    fake.ORDER_TIME_GTC = 1000
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name == "mt5_universal.bridge" or name.startswith("mt5_universal.bridge."):
            sys.modules.pop(name, None)


def test_bridge_imports(mocked_mt5):
    from mt5_universal.bridge import connect, mt5_call, ensure_symbol, reconnect_once  # noqa: F401


def test_connect_is_idempotent(mocked_mt5):
    from mt5_universal.bridge import connect
    connect(login=1, password="x", server="s")
    connect(login=1, password="x", server="s")
    assert mocked_mt5.initialize.call_count <= 1


def test_connect_without_password_calls_bare_initialize(mocked_mt5):
    from mt5_universal.bridge import connect
    connect()
    mocked_mt5.initialize.assert_called_once_with()


def test_mt5_call_dispatches(mocked_mt5):
    from mt5_universal.bridge import mt5_call
    mocked_mt5.symbol_info_tick.return_value = MagicMock(bid=1.0, ask=1.0001)
    out = mt5_call("symbol_info_tick", "EURUSD")
    assert out is not None
    mocked_mt5.symbol_info_tick.assert_called_once_with("EURUSD")


def test_ensure_symbol_returns_bool(mocked_mt5):
    from mt5_universal.bridge import ensure_symbol
    assert ensure_symbol("USDJPY") is True
    mocked_mt5.symbol_select.assert_called_with("USDJPY", True)


def test_filling_constants_re_exported(mocked_mt5):
    import mt5_universal.bridge as br
    assert br.ORDER_FILLING_FOK == 1
    assert br.ORDER_FILLING_IOC == 2
    assert br.ORDER_FILLING_RETURN == 3
    assert br.TIMEFRAME_M5 == 500
    assert br.COPY_TICKS_ALL == 700
    assert br.ACCOUNT_TRADE_MODE_DEMO == 900
    assert br.ORDER_TIME_GTC == 1000
    assert br.TRADE_ACTION_SLTP == 30
