"""
mt5_cli.py — Root Click group and config commands for the MT5 CLI.

CLI layer only: Click groups, context passing, output formatting, config
commands. No business logic or MT5 API calls except through the bridge.
"""
from __future__ import annotations

import json
import os
import sys

import click

from cli_anything.mt5.core import account, analyze, indicator, market, order, project, rates
from cli_anything.mt5.utils import mt5_backend as bridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONNECTION_ERROR_CODE = "MT5_CONNECTION_ERROR"
_CONNECTION_EXIT_CODE = 2
_DEFAULT_EXIT_CODE = 1


def _compose_live_intent(cfg: dict, cli_live_flag: bool) -> bool:
    """Return True iff all three live-trading gates are simultaneously active.

    Gates (must ALL be True):
    1. cfg["live"]                        — config file + env resolution
    2. cli_live_flag                      — --live CLI flag was passed
    3. MT5_LIVE env var equals "1"        — checked directly (belt-and-suspenders)
    """
    return bool(cfg.get("live")) and cli_live_flag and os.environ.get("MT5_LIVE") == "1"


def _ensure_connected(cfg: dict):
    """Return None on success, or a structured error envelope on failure."""
    try:
        bridge.connect(
            login=cfg.get("login"),
            password=cfg.get("password"),
            server=cfg.get("server", ""),
            timeout=cfg.get("timeout", 10000),
        )
        return None
    except ConnectionError as exc:
        return {
            "ok": False,
            "error": {
                "code": _CONNECTION_ERROR_CODE,
                "message": str(exc) or "Cannot connect to MT5 terminal.",
                "mt5_retcode": None,
            },
        }


def _exit_code_for(error_code: str) -> int:
    """Map an error code string to a CLI exit code per spec §6."""
    if error_code == _CONNECTION_ERROR_CODE:
        return _CONNECTION_EXIT_CODE
    return _DEFAULT_EXIT_CODE


def output(data: dict, as_json: bool) -> None:
    """Dual-mode output emitter.

    JSON mode: prints the full envelope and exits non-zero on error.
    Human mode: pretty-prints data on success; red error line + non-zero exit on failure.
    """
    if as_json:
        click.echo(json.dumps(data, default=str))
        if not data.get("ok"):
            sys.exit(_exit_code_for(data["error"]["code"]))
        return

    if data.get("ok"):
        payload = data.get("data", {})
        if isinstance(payload, (dict, list)):
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            click.echo(str(payload))
    else:
        err = data["error"]
        click.secho(f"Error [{err['code']}]: {err['message']}", fg="red", err=True)
        sys.exit(_exit_code_for(err["code"]))


def _launch_repl(ctx) -> None:
    """Launch the interactive REPL (implemented in Task 15)."""
    click.echo("REPL not yet implemented (Task 15).")


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--login", default=None, type=int, help="MT5 account login number.")
@click.option("--password", default=None, help="MT5 account password.")
@click.option("--server", default=None, help="MT5 broker server name.")
@click.option("--live", "cli_live", is_flag=True, default=False, help="Enable live trading gate.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit machine-readable JSON.")
@click.pass_context
def main(ctx, login, password, server, cli_live, as_json):
    """MT5 CLI — MetaTrader 5 shell interface."""
    ctx.ensure_object(dict)

    overrides: dict = {}
    if login is not None:
        overrides["login"] = login
    if password is not None:
        overrides["password"] = password
    if server is not None:
        overrides["server"] = server

    cfg = project.load(overrides=overrides or None)
    live_intent = _compose_live_intent(cfg, cli_live)

    ctx.obj = {"cfg": cfg, "as_json": as_json, "live_intent": live_intent}

    if ctx.invoked_subcommand is None:
        _launch_repl(ctx)


# ---------------------------------------------------------------------------
# Config command group
# ---------------------------------------------------------------------------

@main.group("config")
@click.pass_context
def config_group(ctx):
    """View or update CLI configuration."""
    ctx.ensure_object(dict)


@config_group.command("show")
@click.pass_context
def config_show(ctx):
    """Print the current effective configuration (password masked)."""
    obj = ctx.obj
    output({"ok": True, "data": project.mask_secrets(obj["cfg"])}, obj["as_json"])


@config_group.command("save")
@click.pass_context
def config_save(ctx):
    """Write the current effective configuration to the config file."""
    obj = ctx.obj
    project.save(obj["cfg"])
    output(
        {"ok": True, "data": {"saved": True, "path": str(project.CONFIG_PATH)}},
        obj["as_json"],
    )


@config_group.command("test")
@click.pass_context
def config_test(ctx):
    """Verify MT5 connection using the current credentials."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        {"ok": True, "data": {"connected": True, "server": obj["cfg"].get("server")}},
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Account command group
# ---------------------------------------------------------------------------

@main.group("account")
@click.pass_context
def account_group(ctx):
    """Account information and risk status."""
    ctx.ensure_object(dict)


@account_group.command("info")
@click.pass_context
def account_info_cmd(ctx):
    """Full account snapshot."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(account.info(), obj["as_json"])


@account_group.command("balance")
@click.pass_context
def account_balance_cmd(ctx):
    """Quick balance check."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(account.balance(), obj["as_json"])


@account_group.command("risk")
@click.pass_context
def account_risk_cmd(ctx):
    """Risk envelope status."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(account.risk(obj["cfg"]), obj["as_json"])


# ---------------------------------------------------------------------------
# Market command group
# ---------------------------------------------------------------------------

@main.group("market")
@click.pass_context
def market_group(ctx):
    """Market data: symbol info, ticks, search, sessions."""
    ctx.ensure_object(dict)


@market_group.command("info")
@click.argument("symbol")
@click.pass_context
def market_info_cmd(ctx, symbol):
    """Symbol specification (bid/ask, pip size, volumes, etc.)."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(market.info(symbol), obj["as_json"])


@market_group.command("tick")
@click.argument("symbol")
@click.pass_context
def market_tick_cmd(ctx, symbol):
    """Latest tick for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(market.tick(symbol), obj["as_json"])


@market_group.command("search")
@click.option("--pattern", required=True, help="Symbol search pattern (bare term auto-wrapped as *PATTERN*).")
@click.pass_context
def market_search_cmd(ctx, pattern):
    """Search for symbols matching PATTERN."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(market.search(pattern), obj["as_json"])


@market_group.command("session")
@click.argument("symbol")
@click.pass_context
def market_session_cmd(ctx, symbol):
    """Current trading session window for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(market.session(symbol), obj["as_json"])


@market_group.command("sessions")
@click.argument("symbol")
@click.pass_context
def market_sessions_cmd(ctx, symbol):
    """Named FX session boundaries (UTC) for SYMBOL from the static table."""
    obj = ctx.obj
    output(market.sessions(symbol), obj["as_json"])


# ---------------------------------------------------------------------------
# Rates command group
# ---------------------------------------------------------------------------

def _parse_date(date_str: str):
    """Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS to UTC-aware datetime."""
    from datetime import datetime, timezone
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise click.BadParameter(f"Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, got {date_str!r}.")


@main.group("rates")
@click.pass_context
def rates_group(ctx):
    """OHLCV bar and tick data."""
    ctx.ensure_object(dict)


@rates_group.command("fetch")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", required=True, type=int, help="Number of bars to fetch.")
@click.pass_context
def rates_fetch_cmd(ctx, symbol, timeframe, bars):
    """Fetch the last --bars OHLCV bars for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(rates.fetch(symbol, timeframe, bars), obj["as_json"])


@rates_group.command("latest")
@click.argument("symbol")
@click.argument("timeframe")
@click.pass_context
def rates_latest_cmd(ctx, symbol, timeframe):
    """Most-recently closed bar for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(rates.latest(symbol, timeframe), obj["as_json"])


@rates_group.command("range")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--from", "date_from", required=True, help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--to", "date_to", required=True, help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.pass_context
def rates_range_cmd(ctx, symbol, timeframe, date_from, date_to):
    """OHLCV bars for SYMBOL / TIMEFRAME in [--from, --to]."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(rates.range(symbol, timeframe, _parse_date(date_from), _parse_date(date_to)), obj["as_json"])


@rates_group.command("ticks")
@click.argument("symbol")
@click.option("--bars", required=True, type=int, help="Number of ticks to return.")
@click.pass_context
def rates_ticks_cmd(ctx, symbol, bars):
    """Last --bars ticks for SYMBOL using a 24-hour lookback."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(rates.ticks(symbol, bars), obj["as_json"])


@rates_group.command("ticks-range")
@click.argument("symbol")
@click.option("--from", "date_from", required=True, help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--to", "date_to", required=True, help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.pass_context
def rates_ticks_range_cmd(ctx, symbol, date_from, date_to):
    """All ticks for SYMBOL in [--from, --to]."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(rates.ticks_range(symbol, _parse_date(date_from), _parse_date(date_to)), obj["as_json"])


# ---------------------------------------------------------------------------
# Indicator command group
# ---------------------------------------------------------------------------

@main.group("indicator")
@click.pass_context
def indicator_group(ctx):
    """Technical indicators: EMA, SMA, RSI, MACD, BB, ATR."""
    ctx.ensure_object(dict)


@indicator_group.command("list")
@click.pass_context
def indicator_list_cmd(ctx):
    """List all available indicators."""
    obj = ctx.obj
    output(indicator.list_available(), obj["as_json"])


@indicator_group.command("ema")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--period", required=True, type=int, help="EMA period.")
@click.option("--bars", default=100, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_ema_cmd(ctx, symbol, timeframe, period, bars):
    """Exponential Moving Average for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.ema(symbol, timeframe, period, bars), obj["as_json"])


@indicator_group.command("sma")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--period", required=True, type=int, help="SMA period.")
@click.option("--bars", default=100, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_sma_cmd(ctx, symbol, timeframe, period, bars):
    """Simple Moving Average for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.sma(symbol, timeframe, period, bars), obj["as_json"])


@indicator_group.command("rsi")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--period", required=True, type=int, help="RSI period.")
@click.option("--bars", default=100, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_rsi_cmd(ctx, symbol, timeframe, period, bars):
    """Relative Strength Index for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.rsi(symbol, timeframe, period, bars), obj["as_json"])


@indicator_group.command("macd")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--fast", default=12, show_default=True, type=int, help="Fast period.")
@click.option("--slow", default=26, show_default=True, type=int, help="Slow period.")
@click.option("--signal", default=9, show_default=True, type=int, help="Signal period.")
@click.option("--bars", default=200, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_macd_cmd(ctx, symbol, timeframe, fast, slow, signal, bars):
    """MACD for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.macd(symbol, timeframe, fast, slow, signal, bars), obj["as_json"])


@indicator_group.command("bb")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--period", default=20, show_default=True, type=int, help="BB period.")
@click.option("--std", default=2.0, show_default=True, type=float, help="Standard deviations.")
@click.option("--bars", default=100, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_bb_cmd(ctx, symbol, timeframe, period, std, bars):
    """Bollinger Bands for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.bb(symbol, timeframe, period, std, bars), obj["as_json"])


@indicator_group.command("atr")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--period", default=14, show_default=True, type=int, help="ATR period.")
@click.option("--bars", default=100, show_default=True, type=int, help="Bars to fetch.")
@click.pass_context
def indicator_atr_cmd(ctx, symbol, timeframe, period, bars):
    """Average True Range for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(indicator.atr(symbol, timeframe, period, bars), obj["as_json"])


# ---------------------------------------------------------------------------
# Analyze command group
# ---------------------------------------------------------------------------

@main.group("analyze")
@click.pass_context
def analyze_group(ctx):
    """Multi-timeframe analysis and price structure."""
    ctx.ensure_object(dict)


@analyze_group.command("topdown")
@click.argument("symbol")
@click.option("--timeframes", multiple=True, required=True,
              help="Timeframes to analyse.  Repeat (--timeframes D1 --timeframes H4) or "
                   "pass comma/space-separated in one value (--timeframes D1,H4,H1).")
@click.option("--bars", default=200, show_default=True, type=int, help="Bars to fetch per timeframe.")
@click.pass_context
def analyze_topdown_cmd(ctx, symbol, timeframes, bars):
    """Multi-TF trend + momentum summary for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    tf_list = [t for v in timeframes for t in v.replace(",", " ").split() if t]
    output(analyze.topdown(symbol, tf_list, bars), obj["as_json"])


@analyze_group.command("structure")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", default=200, show_default=True, type=int, help="Bars to fetch.")
@click.option("--pivot-n", "pivot_n", default=5, show_default=True, type=int,
              help="N-bar pivot neighbourhood size.")
@click.pass_context
def analyze_structure_cmd(ctx, symbol, timeframe, bars, pivot_n):
    """N-bar pivot swing highs/lows, support and resistance for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(analyze.structure(symbol, timeframe, bars, pivot_n), obj["as_json"])


@analyze_group.command("bias")
@click.argument("symbol")
@click.pass_context
def analyze_bias_cmd(ctx, symbol):
    """Quick directional bias for SYMBOL using D1, H4, H1."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(analyze.bias(symbol), obj["as_json"])


# ---------------------------------------------------------------------------
# Order command group
# ---------------------------------------------------------------------------

@main.group("order")
@click.pass_context
def order_group(ctx):
    """Order placement, modification, cancellation and fill-polling."""
    ctx.ensure_object(dict)


@order_group.command("market")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--volume", type=float, default=None, help="Lot size.")
@click.option("--risk-pct", "risk_pct", type=float, default=None, help="Risk as % of equity.")
@click.option("--sl", required=True, type=float, help="Stop-loss price.")
@click.option("--tp", type=float, default=None, help="Take-profit price.")
@click.option("--comment", default=None, help="Order comment.")
@click.option("--strategy-id", "strategy_id", default=None, help="Strategy identifier.")
@click.option("--magic", type=int, default=None, help="Magic number override.")
@click.option("--deviation", default=20, show_default=True, type=int, help="Max price deviation in points.")
@click.option("--filling", default="auto", show_default=True, help="Filling mode: auto/FOK/IOC/RETURN.")
@click.pass_context
def order_market_cmd(ctx, symbol, side, volume, risk_pct, sl, tp, comment, strategy_id, magic, deviation, filling):
    """Place a market order for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    result = order.place_market(
        symbol, side,
        volume=volume, risk_pct=risk_pct,
        sl=sl, tp=tp, comment=comment,
        strategy_id=strategy_id, magic=magic,
        deviation=deviation, filling=filling,
        cfg=obj["cfg"], is_live_intent=obj["live_intent"],
    )
    output(result, obj["as_json"])


@order_group.command("limit")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--price", required=True, type=float, help="Limit entry price.")
@click.option("--volume", type=float, default=None, help="Lot size.")
@click.option("--risk-pct", "risk_pct", type=float, default=None, help="Risk as % of equity.")
@click.option("--sl", required=True, type=float, help="Stop-loss price.")
@click.option("--tp", type=float, default=None, help="Take-profit price.")
@click.option("--expiry", default=None, help="Expiry datetime (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--strategy-id", "strategy_id", default=None, help="Strategy identifier.")
@click.option("--magic", type=int, default=None, help="Magic number override.")
@click.option("--filling", default="auto", show_default=True, help="Filling mode: auto/FOK/IOC/RETURN.")
@click.pass_context
def order_limit_cmd(ctx, symbol, side, price, volume, risk_pct, sl, tp, expiry, strategy_id, magic, filling):
    """Place a limit order for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    expiry_dt = _parse_date(expiry) if expiry else None
    result = order.place_limit(
        symbol, side, price,
        volume=volume, risk_pct=risk_pct,
        sl=sl, tp=tp, expiry=expiry_dt,
        strategy_id=strategy_id, magic=magic, filling=filling,
        cfg=obj["cfg"], is_live_intent=obj["live_intent"],
    )
    output(result, obj["as_json"])


@order_group.command("stop")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--price", required=True, type=float, help="Stop entry price.")
@click.option("--volume", type=float, default=None, help="Lot size.")
@click.option("--risk-pct", "risk_pct", type=float, default=None, help="Risk as % of equity.")
@click.option("--sl", required=True, type=float, help="Stop-loss price.")
@click.option("--tp", type=float, default=None, help="Take-profit price.")
@click.option("--expiry", default=None, help="Expiry datetime.")
@click.option("--strategy-id", "strategy_id", default=None, help="Strategy identifier.")
@click.option("--magic", type=int, default=None, help="Magic number override.")
@click.option("--filling", default="auto", show_default=True, help="Filling mode: auto/FOK/IOC/RETURN.")
@click.pass_context
def order_stop_cmd(ctx, symbol, side, price, volume, risk_pct, sl, tp, expiry, strategy_id, magic, filling):
    """Place a stop order for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    expiry_dt = _parse_date(expiry) if expiry else None
    result = order.place_stop(
        symbol, side, price,
        volume=volume, risk_pct=risk_pct,
        sl=sl, tp=tp, expiry=expiry_dt,
        strategy_id=strategy_id, magic=magic, filling=filling,
        cfg=obj["cfg"], is_live_intent=obj["live_intent"],
    )
    output(result, obj["as_json"])


@order_group.command("modify")
@click.argument("ticket", type=int)
@click.option("--sl", type=float, default=None, help="New stop-loss price.")
@click.option("--tp", type=float, default=None, help="New take-profit price.")
@click.option("--price", type=float, default=None, help="New entry price (pending orders only).")
@click.pass_context
def order_modify_cmd(ctx, ticket, sl, tp, price):
    """Modify SL/TP for a position or pending order TICKET."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(order.modify(ticket, sl=sl, tp=tp, price=price), obj["as_json"])


@order_group.command("cancel")
@click.argument("ticket", type=int)
@click.pass_context
def order_cancel_cmd(ctx, ticket):
    """Cancel a pending order by TICKET."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(order.cancel(ticket), obj["as_json"])


@order_group.command("poll-fill")
@click.argument("ticket", type=int)
@click.option("--timeout-ms", "timeout_ms", default=5000, show_default=True, type=int,
              help="Polling timeout in milliseconds.")
@click.pass_context
def order_poll_fill_cmd(ctx, ticket, timeout_ms):
    """Poll until TICKET is filled or timeout expires."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(order.poll_fill(ticket, timeout_ms), obj["as_json"])


@order_group.command("dryrun")
@click.argument("symbol")
@click.argument("side", type=click.Choice(["buy", "sell"], case_sensitive=False))
@click.option("--volume", type=float, default=None, help="Lot size.")
@click.option("--risk-pct", "risk_pct", type=float, default=None, help="Risk as % of equity.")
@click.option("--sl", required=True, type=float, help="Stop-loss price.")
@click.option("--tp", type=float, default=None, help="Take-profit price.")
@click.option("--strategy-id", "strategy_id", default=None, help="Strategy identifier.")
@click.option("--magic", type=int, default=None, help="Magic number override.")
@click.option("--deviation", default=20, show_default=True, type=int, help="Max price deviation in points.")
@click.option("--filling", default="auto", show_default=True, help="Filling mode: auto/FOK/IOC/RETURN.")
@click.pass_context
def order_dryrun_cmd(ctx, symbol, side, volume, risk_pct, sl, tp, strategy_id, magic, deviation, filling):
    """Validate an order without placing it (calls order_check, not order_send)."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    result = order.dryrun(
        symbol, side,
        volume=volume, risk_pct=risk_pct,
        sl=sl, tp=tp,
        strategy_id=strategy_id, magic=magic,
        deviation=deviation, filling=filling,
        cfg=obj["cfg"],
    )
    output(result, obj["as_json"])
