import sys
from unittest.mock import MagicMock
import pytest


_MODULES_TO_PURGE = (
    "mt5_universal.bridge",
    "mt5_universal.account",
    "mt5_universal.risk",
    "mt5_universal.risk.risk",
)


def _purge():
    for name in list(sys.modules):
        for prefix in _MODULES_TO_PURGE:
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)
                break


@pytest.fixture
def mocked_mt5(monkeypatch):
    # Same cache-safe pattern as tests/test_bridge.py — purge bridge submodules so
    # each test rebinds against this test's fake instead of a cached fake.
    _purge()

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
    # daily_loss() calls positions_get and history_deals_get — default empty.
    fake.positions_get.return_value = []
    fake.history_deals_get.return_value = []
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    yield fake
    _purge()


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


# ---------------------------------------------------------------------------
# risk()
# ---------------------------------------------------------------------------

_CFG = {
    "max_positions": 5,
    "max_daily_loss": 200.0,
    "min_free_margin_pct": 20.0,
}


def test_account_risk_returns_envelope(mocked_mt5):
    """risk() returns an ok envelope with the required keys."""
    from mt5_universal.account import risk
    env = risk(_CFG)
    assert env["ok"] is True
    data = env["data"]
    for key in ("positions_used", "daily_loss_used", "safe_to_trade",
                "max_positions", "max_daily_loss", "currency"):
        assert key in data, f"Missing key: {key}"


def test_account_risk_safe_to_trade_true_when_under_thresholds(mocked_mt5):
    """safe_to_trade is True when positions and daily loss are under limits."""
    # 0 open positions, 0 daily loss, equity=10012.5, margin_free=10012.5 → 100% free
    from mt5_universal.account import risk
    env = risk(_CFG)
    assert env["ok"] is True
    assert env["data"]["safe_to_trade"] is True
    assert env["data"]["positions_used"] == 0
    assert env["data"]["daily_loss_used"] == 0.0


def test_account_risk_safe_to_trade_false_when_daily_loss_exceeded(mocked_mt5):
    """safe_to_trade is False when daily loss exceeds max_daily_loss."""
    # Simulate a realized loss of -250 (exceeds max_daily_loss=200)
    losing_deal = MagicMock(profit=-250.0, commission=0.0, swap=0.0)
    mocked_mt5.history_deals_get.return_value = [losing_deal]

    from mt5_universal.account import risk
    env = risk(_CFG)
    assert env["ok"] is True
    assert env["data"]["safe_to_trade"] is False
    assert env["data"]["daily_loss_used"] == -250.0
