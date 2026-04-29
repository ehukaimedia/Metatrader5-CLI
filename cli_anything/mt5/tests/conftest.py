"""
pytest configuration — MT5 mock installed at module level so that
`import MetaTrader5 as mt5` inside mt5_backend.py picks up the mock
before any test module imports the bridge.
"""
import os
import sys
import threading
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Install the MetaTrader5 stub BEFORE any test module imports the bridge.
# This must be module-level (not inside a fixture) so that
# `import MetaTrader5 as mt5` in mt5_backend.py resolves to the mock.
# ---------------------------------------------------------------------------
_USE_REAL_MT5 = os.environ.get("MT5_DEMO_INTEGRATION") == "1"

if _USE_REAL_MT5:
    _mt5_mock = None
else:
    _mt5_mock = MagicMock(name="MetaTrader5")
    _mt5_mock.initialize.return_value = True
    _mt5_mock.last_error.return_value = (1, "Success")
    sys.modules["MetaTrader5"] = _mt5_mock

import pytest  # noqa: E402  (must come after sys.modules injection)

from cli_anything.mt5.utils import mt5_backend as bridge  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mt5m():
    """Yield the MT5 mock, reset before and after each test."""
    if _USE_REAL_MT5:
        pytest.skip("mt5m mock fixture is unavailable during live MT5 integration runs.")
    _mt5_mock.reset_mock()
    _mt5_mock.initialize.return_value = True
    _mt5_mock.last_error.return_value = (1, "Success")
    yield _mt5_mock
    _mt5_mock.reset_mock()


@pytest.fixture
def cfg():
    """Return the default effective config dict (matches spec §5 defaults)."""
    return {
        "login": None,
        "password": None,
        "server": "Trading.com-Demo",
        "timeout": 10000,
        "live": False,
        "magic": 88888,
        "deviation": 20,
        "filling": "auto",
        "max_positions": 5,
        "max_daily_loss": 50.0,
        "max_lot_per_order": 1.0,
        "min_sl_distance_points": 50,
        "max_orders_per_minute": 10,
        "max_spread_points": 30,
        "symbol_allowlist": [],
        "min_free_margin_pct": 20,
        "screenshot_path": "~/mt5-screenshots",
        "screenshot_monitor": 0,
        "allow_hedging": False,
        "strategy_ids": {},
    }


@pytest.fixture(autouse=True)
def reset_bridge():
    """Autouse: reset bridge connection state between tests."""
    bridge._initialized = False
    yield
    bridge._initialized = False


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Autouse: clear sliding-window rate limiter between tests."""
    from cli_anything.mt5.core import risk
    risk._rate_limiter.clear()
    yield
    risk._rate_limiter.clear()
