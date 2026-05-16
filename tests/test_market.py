import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    for name in list(sys.modules):
        if name.startswith("mt5_cli.bridge") or name.startswith("mt5_cli.market"):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    # bridge constants (carry-over from previous fixtures)
    fake.ORDER_FILLING_FOK = 1
    fake.ORDER_FILLING_IOC = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.TRADE_ACTION_SLTP = 30
    fake.TIMEFRAME_M5 = 500
    fake.COPY_TICKS_ALL = 700
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    fake.ACCOUNT_TRADE_MODE_CONTEST = 1
    fake.ACCOUNT_TRADE_MODE_REAL = 2
    fake.ORDER_TIME_GTC = 1000
    # SYMBOL_TRADE_MODE_* used by info()
    fake.SYMBOL_TRADE_MODE_DISABLED = 0
    fake.SYMBOL_TRADE_MODE_FULL = 4
    # BOOK_TYPE_* used by DOM normalization
    fake.BOOK_TYPE_SELL = 1
    fake.BOOK_TYPE_BUY = 2
    fake.BOOK_TYPE_SELL_MARKET = 3
    fake.BOOK_TYPE_BUY_MARKET = 4
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name.startswith("mt5_cli.bridge") or name.startswith("mt5_cli.market"):
            sys.modules.pop(name, None)


def test_info_returns_envelope(mocked_mt5):
    mocked_mt5.symbol_info.return_value = MagicMock(
        name_="USDJPY", bid=150.0, ask=150.005, point=0.001, digits=3,
        spread=5, volume_min=0.01, volume_max=100.0, volume_step=0.01,
        trade_mode=4,  # SYMBOL_TRADE_MODE_FULL
        filling_mode=1, time=1700000000,
    )
    mocked_mt5.symbol_select.return_value = True
    from mt5_cli.market import info
    env = info("USDJPY")
    assert env["ok"] is True
    assert env["data"]["bid"] == 150.0
    assert env["data"]["ask"] == 150.005


def test_tick_returns_iso_timestamp(mocked_mt5):
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.symbol_info_tick.return_value = MagicMock(
        bid=150.0, ask=150.005, last=150.002, time=1700000000, volume=10,
    )
    from mt5_cli.market import tick
    env = tick("USDJPY")
    assert env["ok"] is True
    assert env["data"]["bid"] == 150.0
    assert "T" in env["data"]["time"]  # ISO-8601


def test_depth_releases_subscription(mocked_mt5):
    """DOM read must call market_book_release after market_book_get."""
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.market_book_add.return_value = True
    mocked_mt5.market_book_get.return_value = [
        MagicMock(type=1, price=150.010, volume=10),  # SELL
        MagicMock(type=1, price=150.008, volume=5),
        MagicMock(type=2, price=150.000, volume=8),   # BUY
        MagicMock(type=2, price=149.998, volume=12),
    ]
    mocked_mt5.market_book_release.return_value = True
    from mt5_cli.market import depth
    env = depth("USDJPY", levels=2)
    assert env["ok"] is True
    mocked_mt5.market_book_release.assert_called_once_with("USDJPY")


def test_depth_returns_nearest_first(mocked_mt5):
    """Bids descending (highest first), asks ascending (lowest first)."""
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.market_book_add.return_value = True
    mocked_mt5.market_book_get.return_value = [
        MagicMock(type=1, price=150.012, volume=10),  # SELL (asks)
        MagicMock(type=1, price=150.008, volume=5),
        MagicMock(type=2, price=149.995, volume=12),  # BUY (bids)
        MagicMock(type=2, price=150.000, volume=8),
    ]
    mocked_mt5.market_book_release.return_value = True
    from mt5_cli.market import depth
    env = depth("USDJPY")
    bids = env["data"]["bids"]
    asks = env["data"]["asks"]
    # nearest-first: bids descending by price, asks ascending
    assert bids[0]["price"] >= bids[-1]["price"]
    assert asks[0]["price"] <= asks[-1]["price"]


def test_depth_computes_spread_midpoint_imbalance(mocked_mt5):
    mocked_mt5.symbol_select.return_value = True
    mocked_mt5.symbol_info.return_value = MagicMock(point=0.001, digits=3)
    mocked_mt5.market_book_add.return_value = True
    mocked_mt5.market_book_get.return_value = [
        MagicMock(type=1, price=150.005, volume=10),
        MagicMock(type=2, price=150.000, volume=20),  # bigger bid volume
    ]
    mocked_mt5.market_book_release.return_value = True
    from mt5_cli.market import depth
    env = depth("USDJPY")
    d = env["data"]
    assert d["midpoint"] == pytest.approx(150.0025)
    # spread_points: (ask - bid) / point = (150.005 - 150.000) / 0.001 = 5
    assert d["spread_points"] == pytest.approx(5, rel=1e-3)
    # imbalance: bids heavier → positive
    assert d["imbalance"] > 0


def test_search_auto_wraps_bare_pattern(mocked_mt5):
    mocked_mt5.symbols_get.return_value = [
        MagicMock(name_="USDJPY"), MagicMock(name_="EURUSD"),
    ]
    from mt5_cli.market import search
    env = search("USD")
    assert env["ok"] is True
    # Verify the wildcard was applied. Legacy wraps bare → *USD*
    args, kwargs = mocked_mt5.symbols_get.call_args
    assert "*USD*" in str(args) + str(kwargs)


def test_sessions_returns_envelope(mocked_mt5):
    from mt5_cli.market import sessions
    env = sessions("USDJPY")
    assert env["ok"] is True
    # static table — at minimum a symbol field and some session info
    assert "symbol" in env["data"]
