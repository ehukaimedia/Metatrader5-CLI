"""Tests for mt5_cli/chart/indicators_attach.py.

The attach/detach/list_attached primitives go through the MT5 SDK
bridge (mt5_call). Tests use the same cache-safe MagicMock pattern
as test_market / test_rates / etc.
"""
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mocked_mt5(monkeypatch):
    """Inject a fake MetaTrader5 module + purge bridge/chart caches."""
    for name in list(sys.modules):
        if name.startswith("mt5_cli.bridge") or name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)

    fake = MagicMock(name="MetaTrader5")
    fake.initialize.return_value = True
    # Bridge constant re-exports we touch
    fake.TIMEFRAME_M1 = 1
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_M30 = 30
    fake.TIMEFRAME_H1 = 60
    fake.TIMEFRAME_H4 = 240
    fake.TIMEFRAME_D1 = 1440
    fake.TIMEFRAME_W1 = 10080
    fake.TIMEFRAME_MN1 = 43200
    # Constants borrowed from other tests so bridge import doesn't break
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_PENDING = 5
    fake.TRADE_ACTION_SLTP = 6
    fake.TRADE_ACTION_MODIFY = 7
    fake.TRADE_ACTION_REMOVE = 8
    fake.TRADE_RETCODE_DONE = 10009
    fake.TRADE_RETCODE_PLACED = 10008
    fake.TRADE_RETCODE_INVALID_FILL = 10030
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.ORDER_TYPE_BUY_LIMIT = 2
    fake.ORDER_TYPE_SELL_LIMIT = 3
    fake.ORDER_TYPE_BUY_STOP = 4
    fake.ORDER_TYPE_SELL_STOP = 5
    fake.ORDER_TIME_GTC = 0
    fake.ORDER_FILLING_FOK = 0
    fake.ORDER_FILLING_IOC = 1
    fake.ORDER_FILLING_RETURN = 2
    fake.COPY_TICKS_ALL = -1
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    fake.ACCOUNT_TRADE_MODE_CONTEST = 1
    fake.ACCOUNT_TRADE_MODE_REAL = 2
    fake.POSITION_TYPE_BUY = 0
    fake.POSITION_TYPE_SELL = 1

    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    for name in list(sys.modules):
        if name.startswith("mt5_cli.bridge") or name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


def _mock_chart_lookup(monkeypatch, *, symbol="USDJPY", timeframe="H1", parent_hwnd=1000):
    """Stub mt5_cli.chart.current_title to return a known symbol/TF."""
    from mt5_cli.chart import indicators_attach

    def fake_current_title(window_substring="MT5", chart_id=None):
        return {
            "ok": True,
            "data": {
                "hwnd": chart_id or 2000,
                "title": f"[{symbol},{timeframe}]",
                "symbol": symbol,
                "timeframe": timeframe,
                "parent_hwnd": parent_hwnd,
            },
        }

    monkeypatch.setattr(indicators_attach, "current_title", fake_current_title)


# ---------------------------------------------------------------------------
# attach
# ---------------------------------------------------------------------------


def test_attach_loads_handle_and_calls_chart_indicator_add(mocked_mt5, monkeypatch):
    _mock_chart_lookup(monkeypatch, symbol="USDJPY", timeframe="H1")
    mocked_mt5.iCustom.return_value = 12345
    mocked_mt5.ChartIndicatorAdd.return_value = True

    from mt5_cli.chart.indicators_attach import attach
    env = attach(chart_id=2000, indicator_name="MyEMA", params=[20])
    assert env["ok"] is True
    assert env["data"]["handle"] == 12345
    assert env["data"]["chart_id"] == 2000
    assert env["data"]["sub_window"] == 0
    assert env["data"]["indicator_name"] == "MyEMA"

    mocked_mt5.iCustom.assert_called_once_with("USDJPY", 60, "MyEMA", 20)
    mocked_mt5.ChartIndicatorAdd.assert_called_once_with(2000, 0, 12345)


def test_attach_fails_when_icustom_returns_invalid_handle(mocked_mt5, monkeypatch):
    _mock_chart_lookup(monkeypatch)
    mocked_mt5.iCustom.return_value = -1  # INVALID_HANDLE

    from mt5_cli.chart.indicators_attach import attach
    env = attach(chart_id=2000, indicator_name="BadInd")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INDICATOR_LOAD_FAILED"
    mocked_mt5.ChartIndicatorAdd.assert_not_called()


def test_attach_fails_when_chart_indicator_add_returns_false(mocked_mt5, monkeypatch):
    _mock_chart_lookup(monkeypatch)
    mocked_mt5.iCustom.return_value = 99
    mocked_mt5.ChartIndicatorAdd.return_value = False

    from mt5_cli.chart.indicators_attach import attach
    env = attach(chart_id=2000, indicator_name="MyInd")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INDICATOR_ATTACH_FAILED"


def test_attach_fails_when_chart_lookup_fails(mocked_mt5, monkeypatch):
    from mt5_cli.chart import indicators_attach

    def fake_current_title(window_substring="MT5", chart_id=None):
        return {"ok": False, "error": {"code": "CHART_ID_NOT_FOUND", "message": "X"}}
    monkeypatch.setattr(indicators_attach, "current_title", fake_current_title)

    env = indicators_attach.attach(chart_id=999, indicator_name="MyInd")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_ID_NOT_FOUND"


def test_attach_handles_no_params(mocked_mt5, monkeypatch):
    _mock_chart_lookup(monkeypatch)
    mocked_mt5.iCustom.return_value = 1
    mocked_mt5.ChartIndicatorAdd.return_value = True

    from mt5_cli.chart.indicators_attach import attach
    env = attach(chart_id=2000, indicator_name="Plain")
    assert env["ok"] is True
    mocked_mt5.iCustom.assert_called_once_with("USDJPY", 60, "Plain")


def test_attach_resolves_unknown_timeframe_as_fail(mocked_mt5, monkeypatch):
    _mock_chart_lookup(monkeypatch, timeframe="Q1")  # invalid TF

    from mt5_cli.chart.indicators_attach import attach
    env = attach(chart_id=2000, indicator_name="MyInd")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INVALID_TIMEFRAME"


# ---------------------------------------------------------------------------
# detach
# ---------------------------------------------------------------------------


def test_detach_calls_chart_indicator_delete(mocked_mt5):
    mocked_mt5.ChartIndicatorDelete.return_value = True

    from mt5_cli.chart.indicators_attach import detach
    env = detach(chart_id=2000, indicator_short_name="MyEMA")
    assert env["ok"] is True
    assert env["data"]["removed"] is True
    assert env["data"]["indicator_short_name"] == "MyEMA"
    mocked_mt5.ChartIndicatorDelete.assert_called_once_with(2000, 0, "MyEMA")


def test_detach_fails_when_mt5_returns_false(mocked_mt5):
    mocked_mt5.ChartIndicatorDelete.return_value = False

    from mt5_cli.chart.indicators_attach import detach
    env = detach(chart_id=2000, indicator_short_name="Ghost")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INDICATOR_DETACH_FAILED"


def test_detach_respects_sub_window(mocked_mt5):
    mocked_mt5.ChartIndicatorDelete.return_value = True

    from mt5_cli.chart.indicators_attach import detach
    detach(chart_id=2000, indicator_short_name="OSC", sub_window=1)
    mocked_mt5.ChartIndicatorDelete.assert_called_once_with(2000, 1, "OSC")


# ---------------------------------------------------------------------------
# list_attached
# ---------------------------------------------------------------------------


def test_list_attached_returns_names(mocked_mt5):
    mocked_mt5.ChartIndicatorsTotal.return_value = 3
    mocked_mt5.ChartIndicatorName.side_effect = lambda chart_id, sub_window, idx: f"Ind{idx}"

    from mt5_cli.chart.indicators_attach import list_attached
    env = list_attached(chart_id=2000)
    assert env["ok"] is True
    assert env["data"]["chart_id"] == 2000
    assert env["data"]["sub_window"] == 0
    assert env["data"]["indicators"] == ["Ind0", "Ind1", "Ind2"]


def test_list_attached_empty_when_total_zero(mocked_mt5):
    mocked_mt5.ChartIndicatorsTotal.return_value = 0

    from mt5_cli.chart.indicators_attach import list_attached
    env = list_attached(chart_id=2000)
    assert env["ok"] is True
    assert env["data"]["indicators"] == []
    mocked_mt5.ChartIndicatorName.assert_not_called()
