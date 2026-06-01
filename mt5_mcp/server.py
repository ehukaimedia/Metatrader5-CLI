"""MCP server exposing the read + dry-run surface of metatrader5-cli.

Each tool loads the effective config, ensures the bridge is connected to the
running MetaTrader 5 terminal, calls the underlying library function, and
returns its ok/fail envelope unchanged — so an MCP client sees exactly the same
{ok, data} / {ok, error} contract the CLI emits.

Run it with the ``mt5-mcp`` console script (stdio transport), or
``python -m mt5_mcp.server``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from mt5_cli import account as _account
from mt5_cli import history as _history
from mt5_cli import market as _market
from mt5_cli import orders as _orders
from mt5_cli import positions as _positions
from mt5_cli import rates as _rates
from mt5_cli.bridge import connect as _bridge_connect
from mt5_cli.bridge import is_connected as _bridge_is_connected
from mt5_cli.config import load as _load_config
from mt5_cli.reports import fail


# ---------------------------------------------------------------------------
# Connection / helpers
# ---------------------------------------------------------------------------

def _prepare() -> tuple[dict, dict | None]:
    """Return (cfg, None) once the bridge is up, or (cfg, fail_envelope).

    cfg (the loaded config) is always returned; the second element is a
    fail envelope only when the connection could not be established.
    Zero-config: connects to the already-running terminal using config
    credentials when present. A connection failure becomes an MT5_CONNECTION_ERROR
    envelope so every tool returns a structured result, never a raw exception.
    """
    cfg = _load_config()
    if not _bridge_is_connected():
        try:
            _bridge_connect(
                login=cfg.get("login"),
                password=cfg.get("password"),
                server=cfg.get("server"),
            )
        except Exception as exc:  # noqa: BLE001
            return cfg, fail("MT5_CONNECTION_ERROR", f"Could not connect to MT5: {exc}")
    return cfg, None


def _parse_date(value: str) -> datetime | None:
    """Parse a YYYY-MM-DD or ISO 8601 string to a UTC datetime, or None."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Tools — connection / account
# ---------------------------------------------------------------------------

def status() -> dict:
    """Connection and account summary (balance, equity, margin, connected flag)."""
    cfg, err = _prepare()
    if err:
        return err
    env = _account.info()
    if env.get("ok"):
        env["data"]["connected"] = True
    return env


def account_info() -> dict:
    """Account info: login, currency, leverage, balance, equity, free margin."""
    cfg, err = _prepare()
    if err:
        return err
    return _account.info()


def account_risk() -> dict:
    """Risk snapshot: open exposure, margin level, and configured risk limits."""
    cfg, err = _prepare()
    if err:
        return err
    return _account.risk(cfg)


# ---------------------------------------------------------------------------
# Tools — market data
# ---------------------------------------------------------------------------

def market_info(symbol: str) -> dict:
    """Symbol info: bid, ask, spread, digits, point, pip size, volume limits."""
    cfg, err = _prepare()
    if err:
        return err
    return _market.info(symbol)


def market_tick(symbol: str) -> dict:
    """Latest tick for a symbol (bid, ask, last, volume, time)."""
    cfg, err = _prepare()
    if err:
        return err
    return _market.tick(symbol)


def market_search(pattern: str) -> dict:
    """Search available symbols by name pattern (e.g. 'EUR', 'USD')."""
    cfg, err = _prepare()
    if err:
        return err
    return _market.search(pattern)


# ---------------------------------------------------------------------------
# Tools — rates / history
# ---------------------------------------------------------------------------

def rates_fetch(symbol: str, timeframe: str, bars: int = 100) -> dict:
    """OHLCV bars for a symbol/timeframe (e.g. timeframe='H1', bars=100)."""
    cfg, err = _prepare()
    if err:
        return err
    return _rates.fetch(symbol, timeframe, bars)


def rates_latest(symbol: str, timeframe: str) -> dict:
    """The most recent completed OHLCV bar for a symbol/timeframe."""
    cfg, err = _prepare()
    if err:
        return err
    return _rates.latest(symbol, timeframe)


def history_deals(date_from: str, date_to: str, symbol: str | None = None) -> dict:
    """Closed deals between two dates (YYYY-MM-DD), optionally filtered by symbol."""
    cfg, err = _prepare()
    if err:
        return err
    dt_from, dt_to = _parse_date(date_from), _parse_date(date_to)
    if dt_from is None or dt_to is None:
        return fail("MT5_INVALID_PARAMS", "date_from/date_to must be YYYY-MM-DD or ISO 8601.")
    return _history.deals(dt_from, dt_to, symbol=symbol, cfg=cfg)


def history_stats(date_from: str, date_to: str) -> dict:
    """Aggregate trade stats (wins, losses, profit) between two dates (YYYY-MM-DD)."""
    cfg, err = _prepare()
    if err:
        return err
    dt_from, dt_to = _parse_date(date_from), _parse_date(date_to)
    if dt_from is None or dt_to is None:
        return fail("MT5_INVALID_PARAMS", "date_from/date_to must be YYYY-MM-DD or ISO 8601.")
    return _history.stats(dt_from, dt_to, cfg=cfg)


# ---------------------------------------------------------------------------
# Tools — positions / orders (READ + DRY-RUN ONLY)
# ---------------------------------------------------------------------------

def position_list(symbol: str | None = None) -> dict:
    """Open positions, optionally filtered to one symbol."""
    cfg, err = _prepare()
    if err:
        return err
    return _positions.list(symbol)


def order_list_pending(symbol: str | None = None) -> dict:
    """Pending (limit/stop) orders, optionally filtered to one symbol."""
    cfg, err = _prepare()
    if err:
        return err
    return _orders.list_pending(symbol=symbol, cfg=cfg)


def order_dryrun(
    symbol: str,
    side: str,
    volume: float,
    sl: float,
    tp: float | None = None,
    order_type: str = "market",
    price: float | None = None,
) -> dict:
    """Validate an order against the full risk gauntlet WITHOUT sending it.

    Returns the margin, computed lot, and MT5 retcode an equivalent live order
    would produce. This is pre-flight validation only — it never places an order
    and never arms the live-trade gate (is_live_intent is always False here).
    side is 'buy' or 'sell'; order_type is 'market', 'limit', or 'stop'.
    """
    cfg, err = _prepare()
    if err:
        return err
    return _orders.dryrun(
        symbol,
        side,
        order_type=order_type,
        price=price,
        volume=volume,
        sl=sl,
        tp=tp,
        cfg=cfg,
        is_live_intent=False,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Read + dry-run surface only. Live mutations stay behind the CLI triple-lock.
TOOLS = [
    status,
    account_info,
    account_risk,
    market_info,
    market_tick,
    market_search,
    rates_fetch,
    rates_latest,
    history_deals,
    history_stats,
    position_list,
    order_list_pending,
    order_dryrun,
]


def build_server():
    """Construct the FastMCP server with every tool registered.

    Imports `mcp` lazily so the tool functions above stay importable (and
    unit-testable) without the optional dependency installed.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("metatrader5-cli")
    for fn in TOOLS:
        server.tool()(fn)
    return server


def main() -> None:
    """Console entry point (`mt5-mcp`): run the server over stdio."""
    build_server().run()


if __name__ == "__main__":
    main()
