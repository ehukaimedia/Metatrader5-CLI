"""mt5 CLI - thin wrappers around the mt5_cli library surface.

Structure: top-level group `main` with --json/--live globals; subgroups
per concern; one click command per library function. Every command:

  1. Parses args
  2. Calls the underlying mt5_cli function with the parsed args
  3. Passes the returned envelope to emit() with the global --json flag

The CLI does not contain business logic. If a command has logic beyond
arg parsing and envelope routing, that logic belongs in the library.

Connection lifecycle: most data-read commands call bridge.connect()
before dispatching to allow zero-config use against a running MT5
terminal. The connect command exists for explicit re-connects with
overrides.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from mt5.emit import emit

# Library imports — done at module level so test fixtures that mock
# MetaTrader5 via sys.modules work cleanly.
from mt5_cli import __version__ as _mt5_cli_version
from mt5_cli import account as _account_mod
from mt5_cli import alert as _alert_mod
from mt5_cli import history as _history_mod
from mt5_cli import market as _market_mod
from mt5_cli import orders as _orders_mod
from mt5_cli import positions as _positions_mod
from mt5_cli import rates as _rates_mod
from mt5_cli.bridge import connect as _bridge_connect
from mt5_cli.bridge import is_connected as _bridge_is_connected
from mt5_cli.bridge import mt5_call as _bridge_mt5_call
from mt5_cli.bridge import reconnect_once as _bridge_reconnect_once
from mt5_cli.mql5 import (
    compiler as _mql5_compiler,
    deployer as _mql5_deployer,
    discovery as _mql5_discovery,
    scaffold as _mql5_scaffold,
)
from mt5_cli.chart import (
    attach as _chart_attach,
    attach_ea as _chart_attach_ea,
    close_chart as _chart_close,
    current_title as _chart_current_title,
    cycle_chart as _chart_cycle,
    ensure_chart as _chart_ensure,
    find_window as _chart_find_window,
    list_charts as _chart_list,
    new_chart as _chart_new,
    switch_tf as _chart_switch_tf,
    symbol as _chart_symbol,
)
from mt5_cli.config import load as _config_load
from mt5_cli.config import mask_secrets as _config_mask
from mt5_cli.config import retcode_help as _config_retcode_help
from mt5_cli.reports import fail, ok
from mt5_cli.screenshot import (
    annotate as _screenshot_annotate,
    dom as _screenshot_dom,
    list_screenshots as _screenshot_list,
    take as _screenshot_take,
)
from mt5_cli.tester import (
    cache as _tester_cache,
    ea as _tester_ea,
    indicator as _tester_indicator,
    results as _tester_results,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _autoconnect(cfg: dict) -> dict | None:
    """Idempotently bring the bridge up. Returns a fail envelope on error,
    or None on success. Commands that need MT5 call this first."""
    if _bridge_is_connected():
        return None
    try:
        _bridge_connect(
            login=cfg.get("login"),
            password=cfg.get("password"),
            server=cfg.get("server"),
        )
    except Exception as exc:  # noqa: BLE001
        return fail("MT5_CONNECTION_ERROR", f"Could not connect to MT5: {exc}")
    return None


def _terminal_data_path(cfg: dict) -> str | None:
    """Query the connected MT5 terminal's data_path for `mt5 ea/indicator deploy`.

    Returns the path string when the bridge can reach the running
    terminal, or None when the bridge isn't connected and can't be
    brought up (in which case the deployer falls back to its own
    resolution chain).

    Keeping this lookup in the CLI keeps mt5_cli/mql5/ bridge-free per
    the locked bridge-isolation rule.
    """
    if _autoconnect(cfg) is not None:
        return None
    try:
        info = _bridge_mt5_call("terminal_info")
    except Exception:  # noqa: BLE001
        return None
    if info is None:
        return None
    data_path = getattr(info, "data_path", None)
    return data_path or None


def _parse_date(value: str | None) -> datetime | None:
    """Parse a YYYY-MM-DD or ISO 8601 date string to UTC datetime."""
    if not value:
        return None
    # Try ISO 8601 first
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
# Top-level group
# ---------------------------------------------------------------------------


class EnvelopeGroup(click.Group):
    """Click Group that catches parser/usage errors (invalid Choice, missing
    required option, bad int) and emits them as a MT5_INVALID_PARAMS envelope
    via emit(), preserving the CLI contract that every invocation exits 0
    with a structured envelope instead of leaking Click's usage text to
    stderr with a nonzero exit code."""

    def main(self, args=None, prog_name=None, complete_var=None,
             standalone_mode=True, **extra):
        # Force standalone_mode=False internally so Click does not write
        # its usage block to stderr before we get a chance to emit().
        # Preserve the caller's original standalone_mode semantics for
        # exit-vs-return: sys.exit(0) when True (real CLI), return when
        # False (CliRunner under test).
        try:
            rv = super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                **extra,
            )
        except click.UsageError as exc:
            json_mode = self._infer_json_mode(args)
            emit(fail("MT5_INVALID_PARAMS", exc.format_message()), json_mode)
            if standalone_mode:
                sys.exit(0)
            return
        except Exception as exc:  # noqa: BLE001
            # Contract guarantee: ANY unexpected library/runtime error still
            # surfaces as a structured envelope on stdout with exit 0, never a
            # bare traceback + nonzero exit. Agents parse the envelope, not the
            # exit code (see emit.py / README). UsageError is handled above with
            # its own MT5_INVALID_PARAMS code; everything else lands here.
            json_mode = self._infer_json_mode(args)
            emit(
                fail(
                    "MT5_INTERNAL_ERROR",
                    str(exc),
                    data={"type": type(exc).__name__},
                ),
                json_mode,
            )
            if standalone_mode:
                sys.exit(0)
            return
        if standalone_mode:
            # Click already converted ctx.exit() / --help Exit to an int
            # return value when standalone_mode=False; honor it but cap
            # at 0 since the CLI contract is "always exit 0".
            sys.exit(0)
        return rv

    @staticmethod
    def _infer_json_mode(args) -> bool:
        """Best-effort detection of --json from raw args when the ctx
        never got built (parser error)."""
        if args is None:
            args = sys.argv[1:]
        try:
            return "--json" in list(args)
        except Exception:  # noqa: BLE001
            return False


@click.group(cls=EnvelopeGroup)
@click.option("--json", "json_mode", is_flag=True,
              help="Emit JSON envelopes (for agents / scripts).")
@click.version_option(_mt5_cli_version, "--version", prog_name="mt5",
                      message="%(prog)s %(version)s")
@click.pass_context
def main(ctx: click.Context, json_mode: bool) -> None:
    """mt5 - agent-native control of the MetaTrader 5 terminal."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    # Load config once per invocation; commands read from ctx.obj["cfg"].
    ctx.obj["cfg"] = _config_load()


@main.command()
@click.option("--login", type=int, default=None,
              help="MT5 account login (overrides config).")
@click.option("--password", default=None,
              help="MT5 account password (overrides config).")
@click.option("--server", default=None,
              help="MT5 server name (overrides config).")
@click.pass_context
def connect(ctx: click.Context, login: int | None, password: str | None,
            server: str | None) -> None:
    """Explicitly (re)connect to the MT5 terminal."""
    cfg = dict(ctx.obj["cfg"])
    has_overrides = (
        login is not None or password is not None or server is not None
    )
    if login is not None:
        cfg["login"] = login
    if password is not None:
        cfg["password"] = password
    if server is not None:
        cfg["server"] = server

    # When the caller explicitly passed overrides AND the bridge is
    # already up against a different account/server, _autoconnect would
    # silently no-op and we'd report a reconnect that did not happen.
    # Force a shutdown + initialize via reconnect_once(cfg) instead so
    # the overrides actually take effect.
    if has_overrides and _bridge_is_connected():
        try:
            reconnected = _bridge_reconnect_once(cfg)
        except Exception as exc:  # noqa: BLE001
            emit(fail("MT5_CONNECTION_ERROR",
                      f"Could not reconnect to MT5: {exc}"),
                 ctx.obj["json"])
            return
        if not reconnected:
            emit(fail("MT5_CONNECTION_ERROR",
                      "MT5 reconnect_once returned False; initialize failed."),
                 ctx.obj["json"])
            return
    else:
        err = _autoconnect(cfg)
        if err is not None:
            emit(err, ctx.obj["json"])
            return
    emit(ok({"connected": True, "server": cfg.get("server")}), ctx.obj["json"])


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show connection + account summary."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    env = _account_mod.info()
    if env.get("ok"):
        env["data"]["connected"] = True
        env["data"]["version"] = _mt5_cli_version
    emit(env, ctx.obj["json"])


# ---------------------------------------------------------------------------
# alert  (alerts.dat-backed terminal alerts)
# ---------------------------------------------------------------------------


@main.group()
def alert() -> None:
    """List MT5 terminal alerts.

    Read-only. Writing alerts (set/delete) is deferred until the alerts.dat
    record layout is validated against a live terminal.
    """


@alert.command("list")
@click.option("--alerts-path", default=None,
              help="Override alerts.dat path; default is the connected/workspace MT5 path.")
@click.pass_context
def alert_list_cmd(ctx: click.Context, alerts_path: str | None) -> None:
    """List all defined MT5 alerts."""
    emit(_alert_mod.list_alerts(alerts_path=alerts_path, cfg=ctx.obj["cfg"],
                                data_path=_terminal_data_path(ctx.obj["cfg"])),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# account
# ---------------------------------------------------------------------------


@main.group()
def account() -> None:
    """Account info / balance / risk."""


@account.command("info")
@click.pass_context
def account_info(ctx: click.Context) -> None:
    """Account snapshot (balance, equity, margin, mode)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_account_mod.info(), ctx.obj["json"])


@account.command("balance")
@click.pass_context
def account_balance(ctx: click.Context) -> None:
    """Just the balance / equity / free margin fields."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_account_mod.balance(), ctx.obj["json"])


@account.command("risk")
@click.pass_context
def account_risk(ctx: click.Context) -> None:
    """Live risk snapshot (daily loss, exposure, positions count)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_account_mod.risk(ctx.obj["cfg"]), ctx.obj["json"])


# ---------------------------------------------------------------------------
# market
# ---------------------------------------------------------------------------


@main.group()
def market() -> None:
    """Symbol info / ticks / DOM / search."""


@market.command("info")
@click.argument("symbol")
@click.pass_context
def market_info(ctx: click.Context, symbol: str) -> None:
    """Symbol info (bid/ask/point/digits/spread/volume bounds)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_market_mod.info(symbol), ctx.obj["json"])


@market.command("tick")
@click.argument("symbol")
@click.pass_context
def market_tick(ctx: click.Context, symbol: str) -> None:
    """Latest tick (bid/ask/last/time/volume)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_market_mod.tick(symbol), ctx.obj["json"])


@market.command("depth")
@click.argument("symbol")
@click.pass_context
def market_depth(ctx: click.Context, symbol: str) -> None:
    """Depth of Market structured data (bids/asks/spread/imbalance)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_market_mod.depth(symbol), ctx.obj["json"])


@market.command("search")
@click.argument("pattern")
@click.pass_context
def market_search(ctx: click.Context, pattern: str) -> None:
    """Search Market Watch by glob pattern."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_market_mod.search(pattern), ctx.obj["json"])


@market.command("sessions")
@click.argument("symbol")
@click.pass_context
def market_sessions(ctx: click.Context, symbol: str) -> None:
    """Trading session schedule for symbol."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_market_mod.sessions(symbol), ctx.obj["json"])


# ---------------------------------------------------------------------------
# rates
# ---------------------------------------------------------------------------


@main.group()
def rates() -> None:
    """OHLCV / tick history fetch."""


@rates.command("fetch")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", type=int, default=100, help="Number of bars (default 100).")
@click.pass_context
def rates_fetch(ctx: click.Context, symbol: str, timeframe: str, bars: int) -> None:
    """Fetch N most recent OHLCV bars."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_rates_mod.fetch(symbol, timeframe, bars), ctx.obj["json"])


@rates.command("latest")
@click.argument("symbol")
@click.argument("timeframe")
@click.pass_context
def rates_latest(ctx: click.Context, symbol: str, timeframe: str) -> None:
    """Single most recent closed bar."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_rates_mod.latest(symbol, timeframe), ctx.obj["json"])


@rates.command("ticks")
@click.argument("symbol")
@click.option("--count", type=int, default=100, help="Number of ticks (default 100).")
@click.pass_context
def rates_ticks(ctx: click.Context, symbol: str, count: int) -> None:
    """Most recent N ticks."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_rates_mod.ticks(symbol, count), ctx.obj["json"])


# ---------------------------------------------------------------------------
# order
# ---------------------------------------------------------------------------


@main.group()
def order() -> None:
    """Order placement / cancel / modify."""


def _order_common_opts(f):
    """Decorator stack for order-placement commands (volume/sl/tp/strategy/magic)."""
    f = click.option("--volume", type=float, required=True, help="Lot size.")(f)
    f = click.option("--sl", type=float, required=True, help="Stop-loss price.")(f)
    f = click.option("--tp", type=float, default=None, help="Take-profit price.")(f)
    f = click.option("--strategy-id", default=None,
                     help="Strategy identifier (auto-derives magic).")(f)
    f = click.option("--magic", type=int, default=None,
                     help="Override magic number.")(f)
    f = click.option("--live", "is_live", is_flag=True,
                     help="Required on REAL accounts (third gate of triple lock).")(f)
    return f


@order.command("market")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@_order_common_opts
@click.option("--deviation", type=int, default=20)
@click.option("--filling", default="auto")
@click.pass_context
def order_market(ctx: click.Context, symbol: str, side: str,
                 volume: float, sl: float, tp: float | None,
                 strategy_id: str | None, magic: int | None, is_live: bool,
                 deviation: int, filling: str) -> None:
    """Place a market order."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.place_market(
        symbol=symbol, side=side, volume=volume, sl=sl, tp=tp,
        strategy_id=strategy_id, magic=magic, deviation=deviation,
        filling=filling, cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("limit")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--price", type=float, required=True, help="Limit trigger price.")
@_order_common_opts
@click.option("--filling", default="auto")
@click.pass_context
def order_limit(ctx: click.Context, symbol: str, side: str, price: float,
                volume: float, sl: float, tp: float | None,
                strategy_id: str | None, magic: int | None, is_live: bool,
                filling: str) -> None:
    """Place a limit (pending) order."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.place_limit(
        symbol=symbol, side=side, price=price, volume=volume, sl=sl, tp=tp,
        strategy_id=strategy_id, magic=magic, filling=filling,
        cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("stop")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--price", type=float, required=True, help="Stop trigger price.")
@_order_common_opts
@click.option("--filling", default="auto")
@click.pass_context
def order_stop(ctx: click.Context, symbol: str, side: str, price: float,
               volume: float, sl: float, tp: float | None,
               strategy_id: str | None, magic: int | None, is_live: bool,
               filling: str) -> None:
    """Place a stop (pending) order."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.place_stop(
        symbol=symbol, side=side, price=price, volume=volume, sl=sl, tp=tp,
        strategy_id=strategy_id, magic=magic, filling=filling,
        cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("dryrun")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--type", "order_type",
              type=click.Choice(["market", "limit", "stop"]), default="market")
@click.option("--price", type=float, default=None)
@click.option("--volume", type=float, required=True)
@click.option("--sl", type=float, required=True)
@click.option("--tp", type=float, default=None)
@click.option("--strategy-id", default=None)
@click.option("--filling", default="auto")
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def order_dryrun(ctx: click.Context, symbol: str, side: str, order_type: str,
                 price: float | None, volume: float, sl: float,
                 tp: float | None, strategy_id: str | None, filling: str,
                 is_live: bool) -> None:
    """Validate an order without placing it (runs check_order + order_check)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.dryrun(
        symbol=symbol, side=side, order_type=order_type, price=price,
        volume=volume, sl=sl, tp=tp, strategy_id=strategy_id,
        filling=filling, cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("list-pending")
@click.option("--symbol", default=None)
@click.pass_context
def order_list_pending(ctx: click.Context, symbol: str | None) -> None:
    """List pending orders, optionally filtered by symbol."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.list_pending(symbol=symbol, cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@order.command("cancel")
@click.argument("ticket", type=int)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def order_cancel(ctx: click.Context, ticket: int, is_live: bool) -> None:
    """Cancel a pending order by ticket."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.cancel(ticket, cfg=ctx.obj["cfg"], is_live_intent=is_live),
         ctx.obj["json"])


@order.command("modify")
@click.argument("ticket", type=int)
@click.option("--sl", type=float, default=None)
@click.option("--tp", type=float, default=None)
@click.option("--price", type=float, default=None)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def order_modify(ctx: click.Context, ticket: int, sl: float | None,
                 tp: float | None, price: float | None, is_live: bool) -> None:
    """Modify position SL/TP or pending order price/SL/TP."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.modify(
        ticket, sl=sl, tp=tp, price=price,
        cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("cancel-all")
@click.option("--symbol", default=None)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def order_cancel_all(ctx: click.Context, symbol: str | None, is_live: bool) -> None:
    """Cancel all pending orders (optionally scoped to one symbol)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_orders_mod.cancel_all_pending(
        symbol=symbol, cfg=ctx.obj["cfg"], is_live_intent=is_live,
    ), ctx.obj["json"])


@order.command("poll-fill")
@click.argument("ticket", type=int)
@click.option("--timeout", type=float, default=10.0,
              help="Max wait in seconds (converted to ms for the library).")
@click.pass_context
def order_poll_fill(ctx: click.Context, ticket: int, timeout: float) -> None:
    """Poll for an order's fill state (deal_id / position_id) up to timeout."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    # Library signature is poll_fill(ticket, timeout_ms=...). Keep the CLI
    # flag in seconds (more natural for shells) and convert at the boundary.
    emit(_orders_mod.poll_fill(ticket, timeout_ms=int(timeout * 1000)),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# position
# ---------------------------------------------------------------------------


@main.group()
def position() -> None:
    """Open position list / close / move SL / breakeven."""


@position.command("list")
@click.option("--symbol", default=None)
@click.pass_context
def position_list(ctx: click.Context, symbol: str | None) -> None:
    """List open positions, optionally filtered by symbol."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_positions_mod.list(symbol=symbol), ctx.obj["json"])


@position.command("close")
@click.argument("ticket", type=int)
@click.option("--volume", type=float, default=None,
              help="Partial close volume (default: full close).")
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def position_close(ctx: click.Context, ticket: int, volume: float | None,
                   is_live: bool) -> None:
    """Close a position by ticket (full or partial)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_positions_mod.close(ticket, volume=volume, is_live_intent=is_live,
                              cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@position.command("close-all")
@click.option("--symbol", default=None)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def position_close_all(ctx: click.Context, symbol: str | None,
                       is_live: bool) -> None:
    """Close all open positions (optionally scoped to one symbol)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_positions_mod.close_all(symbol=symbol, is_live_intent=is_live,
                                  cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@position.command("move-sl")
@click.argument("ticket", type=int)
@click.option("--sl", type=float, required=True)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def position_move_sl(ctx: click.Context, ticket: int, sl: float,
                     is_live: bool) -> None:
    """Move a position's stop-loss to a new price."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_positions_mod.move_sl(ticket, sl=sl, is_live_intent=is_live,
                                cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@position.command("breakeven")
@click.argument("ticket", type=int)
@click.option("--buffer-points", type=int, default=0)
@click.option("--live", "is_live", is_flag=True)
@click.pass_context
def position_breakeven(ctx: click.Context, ticket: int, buffer_points: int,
                       is_live: bool) -> None:
    """Move SL to open price (± buffer points)."""
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_positions_mod.breakeven(ticket, buffer_points=buffer_points,
                                  is_live_intent=is_live, cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


@main.group()
def history() -> None:
    """Closed orders / deals / equity stats."""


@history.command("orders")
@click.option("--from", "date_from", default=None, help="YYYY-MM-DD or ISO 8601.")
@click.option("--to", "date_to", default=None, help="YYYY-MM-DD or ISO 8601.")
@click.option("--strategy-id", default=None)
@click.pass_context
def history_orders(ctx: click.Context, date_from: str | None, date_to: str | None,
                   strategy_id: str | None) -> None:
    """Closed order history."""
    # Local validation is side-effect-free; run it BEFORE _autoconnect so a
    # malformed date never triggers an MT5 connection attempt.
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if (date_from and df is None) or (date_to and dt is None):
        emit(fail("MT5_INVALID_PARAMS",
                  "--from / --to must be YYYY-MM-DD or ISO 8601 datetime."),
             ctx.obj["json"])
        return
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_history_mod.orders(date_from=df, date_to=dt, strategy_id=strategy_id,
                             cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@history.command("deals")
@click.option("--from", "date_from", default=None)
@click.option("--to", "date_to", default=None)
@click.option("--strategy-id", default=None)
@click.pass_context
def history_deals(ctx: click.Context, date_from: str | None, date_to: str | None,
                  strategy_id: str | None) -> None:
    """Trade deal history."""
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if (date_from and df is None) or (date_to and dt is None):
        emit(fail("MT5_INVALID_PARAMS",
                  "--from / --to must be YYYY-MM-DD or ISO 8601 datetime."),
             ctx.obj["json"])
        return
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_history_mod.deals(date_from=df, date_to=dt, strategy_id=strategy_id,
                            cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@history.command("stats")
@click.option("--from", "date_from", default=None)
@click.option("--to", "date_to", default=None)
@click.option("--strategy-id", default=None)
@click.pass_context
def history_stats(ctx: click.Context, date_from: str | None, date_to: str | None,
                  strategy_id: str | None) -> None:
    """Aggregated stats (wins/losses/profit factor) over a date range."""
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if (date_from and df is None) or (date_to and dt is None):
        emit(fail("MT5_INVALID_PARAMS",
                  "--from / --to must be YYYY-MM-DD or ISO 8601 datetime."),
             ctx.obj["json"])
        return
    err = _autoconnect(ctx.obj["cfg"])
    if err is not None:
        emit(err, ctx.obj["json"])
        return
    emit(_history_mod.stats(date_from=df, date_to=dt, strategy_id=strategy_id,
                            cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# chart  (pure Win32 - no MT5 SDK / no _autoconnect needed)
# ---------------------------------------------------------------------------


@main.group()
def chart() -> None:
    """Chart UI control (Win32 + GUI menu pokes)."""


@chart.command("find-window")
@click.option("--substring", default="MT5")
@click.pass_context
def chart_find_window(ctx: click.Context, substring: str) -> None:
    """Find the MT5 top-level window."""
    match = _chart_find_window(substring)
    if match is None:
        emit(fail("CHART_WINDOW_NOT_FOUND",
                  f"No MT5 window matched {substring!r}."), ctx.obj["json"])
        return
    emit(ok({"hwnd": match.hwnd, "title": match.title}), ctx.obj["json"])


@chart.command("list")
@click.option("--substring", default="MT5")
@click.pass_context
def chart_list_cmd(ctx: click.Context, substring: str) -> None:
    """List MT5 MDI chart children."""
    emit(_chart_list(substring), ctx.obj["json"])


@chart.command("current-title")
@click.option("--substring", default="MT5")
@click.option("--chart-id", type=int, default=None)
@click.pass_context
def chart_current(ctx: click.Context, substring: str, chart_id: int | None) -> None:
    """Read the active chart's title + parsed symbol/timeframe."""
    emit(_chart_current_title(substring, chart_id=chart_id), ctx.obj["json"])


@chart.command("switch-tf")
@click.argument("timeframe")
@click.option("--substring", default="MT5")
@click.option("--chart-id", type=int, default=None)
@click.pass_context
def chart_switch_tf_cmd(ctx: click.Context, timeframe: str, substring: str,
                        chart_id: int | None) -> None:
    """Switch the active chart's timeframe (M1/M5/M15/M30/H1/H4/D1/W1/MN)."""
    emit(_chart_switch_tf(timeframe, window_substring=substring,
                          chart_id=chart_id), ctx.obj["json"])


@chart.command("symbol")
@click.argument("symbol_name")
@click.option("--substring", default="MT5")
@click.option("--chart-id", type=int, default=None)
@click.pass_context
def chart_symbol_cmd(ctx: click.Context, symbol_name: str, substring: str,
                     chart_id: int | None) -> None:
    """Switch the active chart's symbol (types into existing chart)."""
    emit(_chart_symbol(symbol_name, window_substring=substring,
                       chart_id=chart_id), ctx.obj["json"])


@chart.command("ensure")
@click.argument("symbol_name")
@click.option("--timeframe", default="M15")
@click.option("--substring", default="MT5")
@click.option("--chart-id", type=int, default=None)
@click.pass_context
def chart_ensure_cmd(ctx: click.Context, symbol_name: str, timeframe: str,
                     substring: str, chart_id: int | None) -> None:
    """Ensure a chart for symbol+tf exists (opens new if missing)."""
    emit(_chart_ensure(symbol_name, timeframe=timeframe,
                       window_substring=substring, chart_id=chart_id),
         ctx.obj["json"])


@chart.command("new")
@click.argument("symbol_name")
@click.option("--timeframe", default=None)
@click.option("--substring", default="MT5")
@click.pass_context
def chart_new_cmd(ctx: click.Context, symbol_name: str, timeframe: str | None,
                  substring: str) -> None:
    """Open a new chart via File > New Chart > <symbol>."""
    emit(_chart_new(symbol_name, timeframe=timeframe,
                    window_substring=substring), ctx.obj["json"])


@chart.command("close")
@click.argument("chart_id", type=int)
@click.option("--substring", default="MT5")
@click.pass_context
def chart_close_cmd(ctx: click.Context, chart_id: int, substring: str) -> None:
    """Close a chart by MDI child hwnd."""
    emit(_chart_close(chart_id, window_substring=substring), ctx.obj["json"])


@chart.command("cycle")
@click.option("--direction", type=click.Choice(["next", "prev"]), default="next")
@click.option("--substring", default="MT5")
@click.pass_context
def chart_cycle_cmd(ctx: click.Context, direction: str, substring: str) -> None:
    """Activate the next/prev chart in MDI tab order."""
    emit(_chart_cycle(direction=direction, window_substring=substring),
         ctx.obj["json"])


@chart.command("attach")
@click.argument("indicator_name")
@click.option("--chart-id", type=int, default=None)
@click.option("--substring", default="MT5")
@click.option("--no-confirm", is_flag=True, default=False,
              help="Skip the Enter post that accepts default indicator inputs.")
@click.pass_context
def chart_attach_cmd(ctx: click.Context, indicator_name: str,
                     chart_id: int | None, substring: str,
                     no_confirm: bool) -> None:
    """Attach a deployed .ex5 indicator via Insert > Indicators > Custom."""
    emit(_chart_attach(indicator_name, chart_id=chart_id,
                       window_substring=substring,
                       auto_confirm=not no_confirm),
         ctx.obj["json"])


@chart.command("attach-ea")
@click.argument("expert_name")
@click.option("--chart-id", type=int, default=None)
@click.option("--substring", default="MT5")
@click.option("--no-confirm", is_flag=True, default=False,
              help="Skip the Enter post that accepts default EA inputs.")
@click.pass_context
def chart_attach_ea_cmd(ctx: click.Context, expert_name: str,
                        chart_id: int | None, substring: str,
                        no_confirm: bool) -> None:
    """Attach a deployed .ex5 Expert Advisor via Insert > Experts."""
    emit(_chart_attach_ea(expert_name, chart_id=chart_id,
                          window_substring=substring,
                          auto_confirm=not no_confirm),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------


@main.group()
def screenshot() -> None:
    """Capture / annotate / list screenshots."""


@screenshot.command("take")
@click.option("--output", default=None,
              help="Output path; default: ~/.local/share/metatrader5-cli/screenshots/")
@click.option("--window", "window_substring", default="MT5",
              help="Window-bounds substring; '' for full monitor.")
@click.option("--monitor", type=int, default=None)
@click.pass_context
def screenshot_take(ctx: click.Context, output: str | None,
                    window_substring: str, monitor: int | None) -> None:
    """Capture the MT5 window (or a monitor) as PNG."""
    emit(_screenshot_take(output_path=output, window_substring=window_substring,
                          monitor=monitor, cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@screenshot.command("dom")
@click.argument("symbol")
@click.option("--output", default=None)
@click.option("--open-panel/--no-open-panel", default=True)
@click.option("--close-panel/--no-close-panel", default=True)
@click.pass_context
def screenshot_dom(ctx: click.Context, symbol: str, output: str | None,
                   open_panel: bool, close_panel: bool) -> None:
    """Capture the Depth of Market window for symbol as PNG."""
    emit(_screenshot_dom(symbol=symbol, output_path=output,
                         open_panel=open_panel, close_panel=close_panel,
                         cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


@screenshot.command("annotate")
@click.argument("input_path")
@click.argument("output_path")
@click.argument("text")
@click.option("--xy", default="10,10", help="Overlay anchor as 'x,y' (default 10,10).")
@click.pass_context
def screenshot_annotate(ctx: click.Context, input_path: str, output_path: str,
                        text: str, xy: str) -> None:
    """Add a text overlay to an existing PNG."""
    try:
        x_str, y_str = xy.split(",", 1)
        xy_tuple = (int(x_str), int(y_str))
    except (ValueError, AttributeError):
        emit(fail("MT5_INVALID_PARAMS", f"--xy must be 'X,Y' integers, got {xy!r}"),
             ctx.obj["json"])
        return
    emit(_screenshot_annotate(input_path, output_path, text, xy=xy_tuple),
         ctx.obj["json"])


@screenshot.command("list")
@click.option("--directory", default=None)
@click.pass_context
def screenshot_list_cmd(ctx: click.Context, directory: str | None) -> None:
    """List captured PNGs (newest first)."""
    emit(_screenshot_list(directory=directory, cfg=ctx.obj["cfg"]),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@main.group()
def config() -> None:
    """Show effective config / look up MT5 retcodes."""


@config.command("show")
@click.option("--mask-secrets/--no-mask-secrets", default=True,
              help="Redact password and login fields (default: on).")
@click.pass_context
def config_show(ctx: click.Context, mask_secrets: bool) -> None:
    """Print the effective configuration (DEFAULTS+file+env+overrides)."""
    cfg = ctx.obj["cfg"]
    if mask_secrets:
        cfg = _config_mask(cfg)
    emit(ok(cfg), ctx.obj["json"])


@config.command("retcode")
@click.argument("code", type=int)
@click.pass_context
def config_retcode(ctx: click.Context, code: int) -> None:
    """Look up an MT5 trade retcode (10004 / 10008 / 10030 etc)."""
    emit(ok({"retcode": code, "help": _config_retcode_help(code)}),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# ea (MQL5 Expert Advisors — Phase 3b plugin host)
# ---------------------------------------------------------------------------


@main.group()
def ea() -> None:
    """MQL5 Expert Advisor authoring (scaffold / list / compile / deploy)."""


@ea.command("list")
@click.pass_context
def ea_list(ctx: click.Context) -> None:
    """List EAs discovered in ./ea/ and the user data dir."""
    emit({"ok": True, "data": _mql5_discovery.list_eas()}, ctx.obj["json"])


@ea.command("new")
@click.argument("name")
@click.option("--template", default="minimal",
              help="Template name (only 'minimal' ships).")
@click.option("--target-dir", default="ea",
              type=click.Path(file_okay=False),
              help="Where to write <name>.mq5 (default: ./ea/).")
@click.pass_context
def ea_new(ctx: click.Context, name: str, template: str,
           target_dir: str) -> None:
    """Scaffold a new EA from the minimal MQL5 skeleton."""
    emit(_mql5_scaffold.create_ea(
        name, target_dir=Path(target_dir), template=template,
    ), ctx.obj["json"])


@ea.command("compile")
@click.argument("name")
@click.pass_context
def ea_compile(ctx: click.Context, name: str) -> None:
    """Compile a discovered EA via metaeditor64.exe."""
    found = _mql5_discovery.get_ea(name)
    if not found:
        emit(fail("EA_NOT_FOUND",
                  f"No EA named {name!r} in any search path. "
                  "Run `mt5 ea list` to see what's available."),
             ctx.obj["json"])
        return
    emit(_mql5_compiler.compile_source(Path(found["source"])),
         ctx.obj["json"])


@ea.command("deploy")
@click.argument("name")
@click.pass_context
def ea_deploy(ctx: click.Context, name: str) -> None:
    """Copy a discovered EA's .mq5 + .ex5 into the MT5 terminal's Experts/."""
    found = _mql5_discovery.get_ea(name)
    if not found:
        emit(fail("EA_NOT_FOUND",
                  f"No EA named {name!r} in any search path. "
                  "Run `mt5 ea list` to see what's available."),
             ctx.obj["json"])
        return
    # Prefer the data_path of the CURRENTLY-CONNECTED terminal so the
    # file lands in the right install when multiple MT5 hash dirs exist.
    # Falls back to env / newest-hash-dir resolution if the bridge isn't
    # reachable.
    data_path = _terminal_data_path(ctx.obj["cfg"])
    emit(_mql5_deployer.deploy_ea(Path(found["source"]),
                                  data_path=data_path),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# indicator (MQL5 custom indicators)
# ---------------------------------------------------------------------------


@main.group()
def indicator() -> None:
    """MQL5 indicator authoring (scaffold / list / compile / deploy)."""


@indicator.command("list")
@click.pass_context
def indicator_list(ctx: click.Context) -> None:
    """List indicators discovered in ./indicators/ and the user data dir."""
    emit({"ok": True, "data": _mql5_discovery.list_indicators()},
         ctx.obj["json"])


@indicator.command("new")
@click.argument("name")
@click.option("--template", default="minimal",
              help="Template name (only 'minimal' ships).")
@click.option("--target-dir", default="indicators",
              type=click.Path(file_okay=False),
              help="Where to write <name>.mq5 (default: ./indicators/).")
@click.pass_context
def indicator_new(ctx: click.Context, name: str, template: str,
                  target_dir: str) -> None:
    """Scaffold a new indicator from the minimal MQL5 skeleton."""
    emit(_mql5_scaffold.create_indicator(
        name, target_dir=Path(target_dir), template=template,
    ), ctx.obj["json"])


@indicator.command("compile")
@click.argument("name")
@click.pass_context
def indicator_compile(ctx: click.Context, name: str) -> None:
    """Compile a discovered indicator via metaeditor64.exe."""
    found = _mql5_discovery.get_indicator(name)
    if not found:
        emit(fail("INDICATOR_NOT_FOUND",
                  f"No indicator named {name!r} in any search path. "
                  "Run `mt5 indicator list` to see what's available."),
             ctx.obj["json"])
        return
    emit(_mql5_compiler.compile_source(Path(found["source"])),
         ctx.obj["json"])


@indicator.command("deploy")
@click.argument("name")
@click.pass_context
def indicator_deploy(ctx: click.Context, name: str) -> None:
    """Copy a discovered indicator's .mq5 + .ex5 into MT5's Indicators/."""
    found = _mql5_discovery.get_indicator(name)
    if not found:
        emit(fail("INDICATOR_NOT_FOUND",
                  f"No indicator named {name!r} in any search path. "
                  "Run `mt5 indicator list` to see what's available."),
             ctx.obj["json"])
        return
    data_path = _terminal_data_path(ctx.obj["cfg"])
    emit(_mql5_deployer.deploy_indicator(Path(found["source"]),
                                         data_path=data_path),
         ctx.obj["json"])


# ---------------------------------------------------------------------------
# tester (MT5 native Strategy Tester)
# ---------------------------------------------------------------------------


@main.group("tester")
def tester_group() -> None:
    """Drive the MT5 Strategy Tester."""


@tester_group.group("ea")
def tester_ea_group() -> None:
    """Backtest an Expert Advisor."""


@tester_ea_group.command("single")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option(
    "--modelling",
    default="real-ticks",
    type=click.Choice(["real-ticks", "every-tick", "ohlc-1m", "open-only", "math"]),
)
@click.option("--deposit", default=10000.0, type=float)
@click.option("--currency", default="USD")
@click.option("--leverage", default=50, type=int)
@click.option("--visual/--no-visual", default=False)
@click.pass_context
def tester_ea_single(ctx: click.Context, **kwargs) -> None:
    """Run a single EA backtest."""
    emit(_tester_ea.single(**kwargs), ctx.obj["json"])


@tester_ea_group.command("optimize")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--mode", default="complete", type=click.Choice(["complete", "genetic", "math"]))
@click.option("--forward", default=None)
@click.option("--set-file", default=None, type=click.Path(dir_okay=False))
@click.option(
    "--param",
    "params",
    multiple=True,
    help="EA input as Name=value or optimization range Name=value,start,step,stop.",
)
@click.pass_context
def tester_ea_optimize(ctx: click.Context, **kwargs) -> None:
    """Run EA optimization."""
    if kwargs.get("params") and kwargs.get("set_file"):
        emit(
            fail("MT5_INVALID_PARAMS", "Pass either --param or --set-file, not both."),
            ctx.obj["json"],
        )
        return
    emit(_tester_ea.optimize(**kwargs), ctx.obj["json"])


@tester_ea_group.command("scanner")
@click.option("--expert", required=True)
@click.option("--symbols", required=True, help="Comma-separated symbols, e.g. AUDUSD,EURUSD")
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.pass_context
def tester_ea_scanner(
    ctx: click.Context,
    expert: str,
    symbols: str,
    timeframe: str,
    from_date: str,
    to_date: str,
) -> None:
    """Run an EA across multiple symbols."""
    parsed_symbols = [item.strip() for item in symbols.split(",") if item.strip()]
    emit(
        _tester_ea.scanner(
            expert=expert,
            symbols=parsed_symbols,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
        ),
        ctx.obj["json"],
    )


@tester_ea_group.command("stress")
@click.option("--expert", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option("--delays-ms", default=50, type=int)
@click.pass_context
def tester_ea_stress(ctx: click.Context, **kwargs) -> None:
    """Run an EA stress backtest."""
    emit(_tester_ea.stress(**kwargs), ctx.obj["json"])


@tester_group.group("indicator")
def tester_indicator_group() -> None:
    """Visual-test an indicator."""


@tester_indicator_group.command("visual")
@click.option("--indicator", "indicator_name", required=True)
@click.option("--symbol", required=True)
@click.option("--tf", "timeframe", required=True)
@click.option("--from", "from_date", required=True)
@click.option("--to", "to_date", required=True)
@click.option(
    "--modelling",
    default="ohlc-1m",
    type=click.Choice(["real-ticks", "every-tick", "ohlc-1m", "open-only", "math"]),
)
@click.pass_context
def tester_indicator_visual(ctx: click.Context, **kwargs) -> None:
    """Run a visual indicator test."""
    emit(_tester_indicator.visual(**kwargs), ctx.obj["json"])


@tester_group.command("list")
@click.option("--limit", default=20, type=int)
@click.pass_context
def tester_list(ctx: click.Context, limit: int) -> None:
    """List recent Strategy Tester runs."""
    emit(ok(_tester_cache.list_recent(limit=limit)), ctx.obj["json"])


@tester_group.command("show")
@click.argument("run_id")
@click.pass_context
def tester_show(ctx: click.Context, run_id: str) -> None:
    """Show a parsed Strategy Tester run."""
    run = _tester_cache.get_run(run_id)
    if not run:
        emit(fail("RUN_NOT_FOUND", f"No run {run_id!r}"), ctx.obj["json"])
        return
    run_path = Path(run["path"])
    try:
        env = _tester_results.assemble(
            run_id=run_id,
            html_path=run_path / "report.html",
            journal_path=run_path / "journal.csv",
            optimization_path=run_path / "optimization.xml",
        )
    except Exception as exc:  # noqa: BLE001
        env = fail("TESTER_PARSE_ERROR", f"Could not parse run {run_id!r}: {exc}")
    emit(env, ctx.obj["json"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
