import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    for name in list(sys.modules):
        if name.startswith("mt5_universal.bridge") or name.startswith("mt5_universal.rates"):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    # bridge timeframe constants (each one unique so _resolve_tf can distinguish)
    fake.TIMEFRAME_M1 = 1
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_M30 = 30
    fake.TIMEFRAME_H1 = 60
    fake.TIMEFRAME_H4 = 240
    fake.TIMEFRAME_D1 = 1440
    fake.TIMEFRAME_W1 = 10080
    fake.TIMEFRAME_MN1 = 43200
    fake.COPY_TICKS_ALL = 700
    # other bridge constants (carry-over for cache-safe re-import)
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.TRADE_ACTION_SLTP = 30
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    fake.ACCOUNT_TRADE_MODE_CONTEST = 1
    fake.ACCOUNT_TRADE_MODE_REAL = 2
    fake.ORDER_TIME_GTC = 1000
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name.startswith("mt5_universal.bridge") or name.startswith("mt5_universal.rates"):
            sys.modules.pop(name, None)


def _bar(time_epoch=1700000000, open_=150.0, high=150.1, low=149.9, close=150.05,
         tick_volume=100, spread=2, real_volume=0):
    return MagicMock(time=time_epoch, open=open_, high=high, low=low, close=close,
                     tick_volume=tick_volume, spread=spread, real_volume=real_volume)


def test_fetch_returns_envelope_with_bars(mocked_mt5):
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_rates_from_pos.return_value = [_bar(), _bar(open_=150.05)]
    from mt5_universal.rates import fetch
    env = fetch("USDJPY", "M5", 2)
    assert env["ok"] is True
    assert len(env["data"]) == 2
    assert "open" in env["data"][0]
    assert "close" in env["data"][0]
    assert "T" in env["data"][0]["time"]  # ISO-8601


def test_fetch_unknown_timeframe_fails(mocked_mt5):
    from mt5_universal.rates import fetch
    env = fetch("USDJPY", "X9", 10)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_TIMEFRAME"


def test_fetch_resolves_M5_to_bridge_constant(mocked_mt5):
    """Verify the string 'M5' is resolved to mt5.TIMEFRAME_M5 (value=5 in fixture)."""
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_rates_from_pos.return_value = [_bar()]
    from mt5_universal.rates import fetch
    fetch("USDJPY", "M5", 1)
    # First call args: symbol, timeframe, start_pos, count
    args, _kw = mocked_mt5.copy_rates_from_pos.call_args
    assert args[1] == 5  # TIMEFRAME_M5


def test_latest_uses_start_pos_1(mocked_mt5):
    """latest() returns the most-recently-closed bar — start_pos=1 (skip the open current bar)."""
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_rates_from_pos.return_value = [_bar()]
    from mt5_universal.rates import latest
    env = latest("USDJPY", "H1")
    assert env["ok"] is True
    args, _kw = mocked_mt5.copy_rates_from_pos.call_args
    # signature: symbol, timeframe, start_pos, count
    assert args[2] == 1  # start_pos must be 1 (skip current open bar)
    assert args[3] == 1  # count


def test_range_passes_datetime(mocked_mt5):
    """range() takes datetime objects; legacy enforces datetime types."""
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_rates_range.return_value = [_bar()]
    from mt5_universal.rates import range as rates_range
    df = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dt = datetime(2026, 1, 31, tzinfo=timezone.utc)
    env = rates_range("USDJPY", "M5", df, dt)
    assert env["ok"] is True
    args, _kw = mocked_mt5.copy_rates_range.call_args
    assert isinstance(args[2], datetime)
    assert isinstance(args[3], datetime)


def test_ticks_returns_envelope(mocked_mt5):
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_ticks_from.return_value = [
        MagicMock(time=1700000000, bid=150.0, ask=150.005, last=150.002, volume=10, time_msc=1700000000000, flags=2, volume_real=10.0),
    ]
    from mt5_universal.rates import ticks
    env = ticks("USDJPY", 1)
    assert env["ok"] is True
    assert env["data"][0]["bid"] == 150.0
    assert "T" in env["data"][0]["time"]


def test_fetch_fails_when_mt5_returns_none(mocked_mt5):
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.copy_rates_from_pos.return_value = None
    from mt5_universal.rates import fetch
    env = fetch("USDJPY", "M5", 10)
    assert env["ok"] is False
