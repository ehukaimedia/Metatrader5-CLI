"""
mt5_backend.py — Thread-safe MetaTrader5 bridge.

This is the ONLY module in the project that imports MetaTrader5.
All other modules interact with MT5 exclusively through this bridge.
"""
import atexit
import threading

import MetaTrader5 as mt5

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_lock: threading.Lock = threading.Lock()
_initialized: bool = False

# ---------------------------------------------------------------------------
# Re-exported MT5 constants (so no other module needs to import MetaTrader5)
# ---------------------------------------------------------------------------

TRADE_ACTION_DEAL = mt5.TRADE_ACTION_DEAL
TRADE_ACTION_PENDING = mt5.TRADE_ACTION_PENDING
TRADE_ACTION_SLTP = mt5.TRADE_ACTION_SLTP
TRADE_ACTION_MODIFY = mt5.TRADE_ACTION_MODIFY
TRADE_ACTION_REMOVE = mt5.TRADE_ACTION_REMOVE
TRADE_ACTION_CLOSE_BY = mt5.TRADE_ACTION_CLOSE_BY

ORDER_TYPE_BUY = mt5.ORDER_TYPE_BUY
ORDER_TYPE_SELL = mt5.ORDER_TYPE_SELL
ORDER_TYPE_BUY_LIMIT = mt5.ORDER_TYPE_BUY_LIMIT
ORDER_TYPE_SELL_LIMIT = mt5.ORDER_TYPE_SELL_LIMIT
ORDER_TYPE_BUY_STOP = mt5.ORDER_TYPE_BUY_STOP
ORDER_TYPE_SELL_STOP = mt5.ORDER_TYPE_SELL_STOP

ORDER_TIME_GTC = mt5.ORDER_TIME_GTC
ORDER_TIME_SPECIFIED = mt5.ORDER_TIME_SPECIFIED

ORDER_FILLING_FOK = mt5.ORDER_FILLING_FOK
ORDER_FILLING_IOC = mt5.ORDER_FILLING_IOC
ORDER_FILLING_RETURN = mt5.ORDER_FILLING_RETURN

COPY_TICKS_ALL = mt5.COPY_TICKS_ALL

ACCOUNT_TRADE_MODE_DEMO = mt5.ACCOUNT_TRADE_MODE_DEMO
ACCOUNT_TRADE_MODE_REAL = mt5.ACCOUNT_TRADE_MODE_REAL
ACCOUNT_TRADE_MODE_CONTEST = mt5.ACCOUNT_TRADE_MODE_CONTEST

TIMEFRAME_M1 = mt5.TIMEFRAME_M1
TIMEFRAME_M5 = mt5.TIMEFRAME_M5
TIMEFRAME_M15 = mt5.TIMEFRAME_M15
TIMEFRAME_M30 = mt5.TIMEFRAME_M30
TIMEFRAME_H1 = mt5.TIMEFRAME_H1
TIMEFRAME_H4 = mt5.TIMEFRAME_H4
TIMEFRAME_D1 = mt5.TIMEFRAME_D1
TIMEFRAME_W1 = mt5.TIMEFRAME_W1
TIMEFRAME_MN1 = mt5.TIMEFRAME_MN1

# Retcode constants — plain integers (broker-level values, not mt5 attributes)
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_REJECT = 10006
TRADE_RETCODE_INVALID_FILL = 10030
TRADE_RETCODE_NOT_ALLOWED = 10027
TRADE_RETCODE_INVALID_STOPS = 10013
TRADE_RETCODE_INVALID_VOLUME = 10016


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect(login, password, server, timeout: int = 10000) -> None:
    """Connect to the MT5 terminal.

    Idempotent — a second call while already connected is a no-op.
    Registers ``disconnect`` via ``atexit`` on first successful connection.
    Raises ``ConnectionError`` if ``mt5.initialize()`` returns False.
    """
    global _initialized
    if _initialized:
        return
    with _lock:
        # Double-checked locking: re-test inside the lock to be safe.
        if _initialized:
            return
        if login is not None and password is not None:
            ok = mt5.initialize(
                login=login,
                password=password,
                server=server,
                timeout=timeout,
            )
        else:
            ok = mt5.initialize()
        if not ok:
            raise ConnectionError("MT5 initialize failed")
        _initialized = True
        atexit.register(disconnect)


def disconnect() -> None:
    """Shut down the MT5 connection."""
    global _initialized
    with _lock:
        mt5.shutdown()
        _initialized = False


def is_connected() -> bool:
    """Return the current connection state."""
    return _initialized


def mt5_call(fn_name: str, *args, **kwargs):
    """Dispatch a single MT5 API call under the global lock.

    This is the single seam through which ALL mt5 calls flow in non-bridge
    code.  Core modules call this instead of touching mt5 directly.
    """
    with _lock:
        fn = getattr(mt5, fn_name)
        if kwargs:
            return fn(*args, **kwargs)
        return fn(*args)


def ensure_symbol(symbol: str) -> bool:
    """Make ``symbol`` visible in MarketWatch (idempotent).

    Returns the result of ``mt5.symbol_select(symbol, True)``.
    """
    with _lock:
        return mt5.symbol_select(symbol, True)


def reconnect_once(cfg: dict) -> bool:
    """Attempt a single reconnect after a detected disconnect.

    Calls ``mt5.shutdown()`` then ``mt5.initialize()`` with the credentials
    from *cfg*.  Updates ``_initialized`` accordingly.
    Returns ``True`` on success, ``False`` on failure.
    """
    global _initialized
    with _lock:
        mt5.shutdown()
        _initialized = False
        if cfg.get("login") is not None and cfg.get("password") is not None:
            ok = mt5.initialize(
                login=cfg.get("login"),
                password=cfg.get("password"),
                server=cfg.get("server"),
                timeout=cfg.get("timeout", 10000),
            )
        else:
            ok = mt5.initialize()
        if ok:
            _initialized = True
        return bool(ok)
