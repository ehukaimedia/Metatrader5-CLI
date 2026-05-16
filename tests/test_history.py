import sys
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    for name in list(sys.modules):
        if name.startswith("mt5_universal.bridge") or name.startswith("mt5_universal.history"):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    # bridge constants from previous tasks
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
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name.startswith("mt5_universal.bridge") or name.startswith("mt5_universal.history"):
            sys.modules.pop(name, None)


def _deal(ticket=1, time_epoch=1700000000, symbol="USDJPY", type_=0, volume=0.1,
          price=150.0, profit=10.0, magic=88888, comment="test"):
    return MagicMock(ticket=ticket, time=time_epoch, symbol=symbol, type=type_,
                     volume=volume, price=price, profit=profit, magic=magic, comment=comment)


def test_orders_returns_envelope(mocked_mt5):
    mocked_mt5.history_orders_get.return_value = []
    from mt5_universal.history import orders
    env = orders(date_from="2026-01-01", date_to="2026-01-31")
    assert env["ok"] is True
    assert isinstance(env["data"], list)


def test_deals_filters_by_symbol(mocked_mt5):
    mocked_mt5.history_deals_get.return_value = [
        _deal(symbol="USDJPY", profit=10.0),
        _deal(symbol="EURUSD", profit=-5.0),
    ]
    from mt5_universal.history import deals
    env = deals(date_from="2026-01-01", date_to="2026-01-31", symbol="USDJPY")
    assert env["ok"] is True
    assert all(d["symbol"] == "USDJPY" for d in env["data"])
    assert len(env["data"]) == 1


def test_deals_filters_by_strategy_id_via_magic(mocked_mt5):
    """strategy_id filter resolves to a magic int and filters deals by that magic."""
    mocked_mt5.history_deals_get.return_value = [
        _deal(magic=88888, profit=10.0),
        _deal(magic=162538, profit=-3.0),
    ]
    cfg = {"strategy_ids": {"my_strategy": 162538}}
    from mt5_universal.history import deals
    env = deals(date_from="2026-01-01", date_to="2026-01-31",
                strategy_id="my_strategy", cfg=cfg)
    assert env["ok"] is True
    assert len(env["data"]) == 1
    assert env["data"][0]["magic"] == 162538


def test_deals_iso_timestamps(mocked_mt5):
    mocked_mt5.history_deals_get.return_value = [_deal(time_epoch=1700000000)]
    from mt5_universal.history import deals
    env = deals(date_from="2026-01-01", date_to="2026-01-31")
    assert env["ok"] is True
    # 1700000000 epoch → 2023-11-14T22:13:20+00:00 (UTC)
    t = env["data"][0]["time"]
    assert isinstance(t, str)
    assert "T" in t  # ISO-8601 format


def test_stats_computes_win_rate_and_pf(mocked_mt5):
    """5 deals, 3 wins ($30 total) + 2 losses ($-10 total) → win_rate=0.6, profit_factor=3.0."""
    mocked_mt5.history_deals_get.return_value = [
        _deal(profit=10), _deal(profit=10), _deal(profit=10),
        _deal(profit=-5), _deal(profit=-5),
    ]
    from mt5_universal.history import stats
    env = stats(date_from="2026-01-01", date_to="2026-01-31")
    assert env["ok"] is True
    assert env["data"]["win_rate"] == 0.6
    assert env["data"]["profit_factor"] == 3.0


def test_orders_fails_when_mt5_returns_none(mocked_mt5):
    mocked_mt5.history_orders_get.return_value = None
    from mt5_universal.history import orders
    env = orders(date_from="2026-01-01", date_to="2026-01-31")
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_CONNECTION_ERROR"
