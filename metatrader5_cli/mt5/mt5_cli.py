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

from metatrader5_cli.mt5.core import account, analyze, chart, ea, ehukai, history, indicator, market, order, position, project, rates, screenshot
from metatrader5_cli.mt5.utils import mt5_backend as bridge

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
    """Launch the interactive REPL."""
    from metatrader5_cli.mt5.utils.repl_skin import ReplSkin  # noqa: PLC0415 (lazy)
    obj = ctx.obj
    ReplSkin(obj["cfg"]).run()


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


@market_group.command("depth")
@click.argument("symbol")
@click.option("--levels", default=0, show_default=True, type=int,
              help="Price levels per side to return. 0 returns all available levels.")
@click.pass_context
def market_depth_cmd(ctx, symbol, levels):
    """Depth of Market snapshot for SYMBOL."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(market.depth(symbol, levels=levels), obj["as_json"])


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
    """Technical indicators: EMA, ATR, FVG."""
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


@indicator_group.command("fvg")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", default=300, show_default=True, type=int, help="Bars to fetch.")
@click.option("--min-points", default=0.0, show_default=True, type=float, help="Minimum gap size in points.")
@click.option("--min-atr-multiple", default=0.0, show_default=True, type=float,
              help="Minimum gap size as a multiple of local ATR. 0 disables.")
@click.option("--direction", default="both", show_default=True,
              type=click.Choice(["both", "bullish", "bearish"]), help="Gap direction filter.")
@click.option("--state", default="all", show_default=True,
              type=click.Choice(["all", "open", "partial", "filled"]), help="Mitigation state filter.")
@click.option("--mitigation", default="body", show_default=True,
              type=click.Choice(["wick", "body"]), help="Use wick or body prices for fill detection.")
@click.option("--limit", default=20, show_default=True, type=int, help="Maximum zones to return. 0 disables.")
@click.pass_context
def indicator_fvg_cmd(ctx, symbol, timeframe, bars, min_points, min_atr_multiple, direction, state, mitigation, limit):
    """Fair Value Gap zones for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        indicator.fvg(
            symbol,
            timeframe,
            bars=bars,
            min_points=min_points,
            min_atr_multiple=min_atr_multiple,
            direction=direction,
            state=state,
            mitigation=mitigation,
            limit=limit or None,
        ),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Ehukai command group
# ---------------------------------------------------------------------------

@main.group("ehukai")
@click.pass_context
def ehukai_group(ctx):
    """Ehukai visual-TDA indicators: FVG, Market Structure, and Liquidity."""
    ctx.ensure_object(dict)


@ehukai_group.command("fvg")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", default=100, show_default=True, type=int,
              help="Lookback bars. Matches EhukaiFVG default.")
@click.option("--min-gap-pips", default=1.0, show_default=True, type=float,
              help="Minimum FVG size in pips.")
@click.option("--max-zones", default=4, show_default=True, type=int,
              help="Maximum visible open/partial zones. Capped at 4.")
@click.option("--max-distance-pips", default=120.0, show_default=True, type=float,
              help="Maximum distance from current price. 0 disables.")
@click.pass_context
def ehukai_fvg_cmd(ctx, symbol, timeframe, bars, min_gap_pips, max_zones, max_distance_pips):
    """EhukaiFVG-compatible visible zones for SYMBOL / TIMEFRAME."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        ehukai.fvg(
            symbol,
            timeframe,
            bars=bars,
            min_gap_pips=min_gap_pips,
            max_zones=max_zones,
            max_distance_pips=max_distance_pips,
        ),
        obj["as_json"],
    )


@ehukai_group.command("structure")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", default=300, show_default=True, type=int,
              help="Lookback bars. Matches EhukaiMarketStructure default.")
@click.option("--pivot-bars", default=8, show_default=True, type=int,
              help="Swing pivot bars. Canonical elite-v1 default matches Pine 8/3/1.")
@click.option("--max-swings", default=10, show_default=True, type=int,
              help="Maximum latest swing labels to return.")
@click.pass_context
def ehukai_structure_cmd(ctx, symbol, timeframe, bars, pivot_bars, max_swings):
    """EhukaiMarketStructure-compatible bias, swings, and levels."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        ehukai.market_structure(
            symbol,
            timeframe,
            bars=bars,
            pivot_bars=pivot_bars,
            max_swings=max_swings,
        ),
        obj["as_json"],
    )


@ehukai_group.command("liquidity")
@click.argument("symbol")
@click.argument("timeframe")
@click.option("--bars", default=300, show_default=True, type=int,
              help="Lookback bars for liquidity swing detection.")
@click.option("--length", default=14, show_default=True, type=int,
              help="Pivot lookback bars left/right.")
@click.option("--area", default="wick", show_default=True,
              type=click.Choice(["wick", "full-range"], case_sensitive=False),
              help="Swing zone area: wick extremity or full candle range.")
@click.option("--filter-by", default="count", show_default=True,
              type=click.Choice(["count", "volume"], case_sensitive=False),
              help="Filter pools by interaction count or tick volume.")
@click.option("--filter-value", default=0.0, show_default=True, type=float,
              help="Minimum count or volume threshold.")
@click.option("--max-pools", default=10, show_default=True, type=int,
              help="Maximum latest pools to return.")
@click.pass_context
def ehukai_liquidity_cmd(ctx, symbol, timeframe, bars, length, area, filter_by, filter_value, max_pools):
    """EhukaiLiquiditySwings-compatible buy/sell-side liquidity pools."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        ehukai.liquidity(
            symbol,
            timeframe,
            bars=bars,
            length=length,
            area=area,
            filter_by=filter_by,
            filter_value=filter_value,
            max_pools=max_pools,
        ),
        obj["as_json"],
    )


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
@click.option("--timeframes", multiple=True, default=("D1,H4,H1",), show_default=True,
              help="Timeframes to analyse.  Repeat (--timeframes D1 --timeframes H4) or "
                   "pass comma/space-separated in one value (--timeframes D1,H4,H1).")
@click.option("--bars", default=200, show_default=True, type=int, help="Bars to fetch per timeframe.")
@click.pass_context
def analyze_topdown_cmd(ctx, symbol, timeframes, bars):
    """Multi-TF market-structure summary for SYMBOL."""
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


@analyze_group.command("sniper-poc")
@click.argument("symbol")
@click.option("--direction", default="auto", show_default=True,
              type=click.Choice(["auto", "buy", "sell"], case_sensitive=False),
              help="Trade direction. auto derives from H4/H1/M15/M5 structure majority.")
@click.option("--bars", default=300, show_default=True, type=int,
              help="Bars per timeframe for Ehukai context.")
@click.option("--max-spread-points", default=30, show_default=True, type=int,
              help="Reject candidate when current bid/ask spread is wider than this.")
@click.option("--min-rr", default=1.5, show_default=True, type=float,
              help="Minimum reward:risk for candidate output.")
@click.option("--entry-buffer-points", default=5, show_default=True, type=int,
              help="Limit entry must be this many points beyond the correct quote side.")
@click.option("--min-stop-points", default=50, show_default=True, type=int,
              help="Minimum entry-to-SL distance in points for the suggested setup.")
@click.option("--stop-buffer-pips", default=1.0, show_default=True, type=float,
              help="Buffer beyond structural/FVG invalidation for SL.")
@click.option("--max-fvg-age-bars", default=20, show_default=True, type=int,
              help="Reject FVGs older than this many bars on their timeframe.")
@click.option("--max-sweep-age-bars", default=12, show_default=True, type=int,
              help="Require the enabling liquidity sweep to be this recent.")
@click.option("--max-entry-distance-pips", default=15.0, show_default=True, type=float,
              help="Reject FVG midpoints farther than this from the trigger quote.")
@click.option("--include-partial-fvg", is_flag=True,
              help="Allow PARTIAL FVGs. Default sniper mode requires OPEN FVGs.")
@click.option("--allow-rollover", is_flag=True,
              help="Allow candidates during the FX 21:00-22:59 UTC rollover window.")
@click.option("--summary", is_flag=True,
              help="Omit the full per-timeframe frames payload from JSON output.")
@click.pass_context
def analyze_sniper_poc_cmd(
    ctx,
    symbol,
    direction,
    bars,
    max_spread_points,
    min_rr,
    entry_buffer_points,
    min_stop_points,
    stop_buffer_pips,
    max_fvg_age_bars,
    max_sweep_age_bars,
    max_entry_distance_pips,
    include_partial_fvg,
    allow_rollover,
    summary,
):
    """Non-mutating M1 sniper point-of-confluence limit plan."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        analyze.sniper_poc(
            symbol,
            direction=direction,
            bars=bars,
            max_spread_points=max_spread_points,
            min_rr=min_rr,
            entry_buffer_points=entry_buffer_points,
            min_stop_points=min_stop_points,
            stop_buffer_pips=stop_buffer_pips,
            max_fvg_age_bars=max_fvg_age_bars,
            max_sweep_age_bars=max_sweep_age_bars,
            max_entry_distance_pips=max_entry_distance_pips,
            include_partial_fvg=include_partial_fvg,
            avoid_rollover=not allow_rollover,
            include_frames=not summary,
        ),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# EA command group
# ---------------------------------------------------------------------------

@main.group("ea")
@click.pass_context
def ea_group(ctx):
    """Expert Advisor local preset helpers."""
    ctx.ensure_object(dict)


@ea_group.group("adaptive-trail")
@click.pass_context
def adaptive_trail_group(ctx):
    """AdaptiveTrailEA preset helpers."""
    ctx.ensure_object(dict)


@adaptive_trail_group.group("magics")
@click.pass_context
def adaptive_trail_magics_group(ctx):
    """View or update AdaptiveTrailEA MagicNumbers presets."""
    ctx.ensure_object(dict)


@adaptive_trail_group.group("tp-runner")
@click.pass_context
def adaptive_trail_tp_runner_group(ctx):
    """Configure optional TP removal for winner-runner mode."""
    ctx.ensure_object(dict)


@adaptive_trail_group.group("manual")
@click.pass_context
def adaptive_trail_manual_group(ctx):
    """Configure scoped manual magic-0 management."""
    ctx.ensure_object(dict)


def _parse_cli_magics(values):
    try:
        return ea.parse_magic_values(values)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


def _parse_cli_symbols(values):
    try:
        return ea.parse_symbol_values(values)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


@adaptive_trail_magics_group.command("show")
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to read.")
@click.pass_context
def adaptive_trail_magics_show_cmd(ctx, experts_dir, preset_name):
    """Show the current AdaptiveTrailEA MagicNumbers preset."""
    obj = ctx.obj
    output(ea.current_magics(experts_dir=experts_dir, preset_name=preset_name), obj["as_json"])


@adaptive_trail_magics_group.command("set")
@click.argument("magics", nargs=-1, required=True)
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to write.")
@click.pass_context
def adaptive_trail_magics_set_cmd(ctx, magics, experts_dir, preset_name):
    """Replace MagicNumbers. Accepts spaces and/or comma-separated values."""
    obj = ctx.obj
    parsed = _parse_cli_magics(magics)
    output(ea.set_magics(parsed, experts_dir=experts_dir, preset_name=preset_name), obj["as_json"])


@adaptive_trail_magics_group.command("add")
@click.argument("magics", nargs=-1, required=True)
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to update.")
@click.pass_context
def adaptive_trail_magics_add_cmd(ctx, magics, experts_dir, preset_name):
    """Add one or more magic numbers to the preset."""
    obj = ctx.obj
    parsed = _parse_cli_magics(magics)
    output(ea.add_magics(parsed, experts_dir=experts_dir, preset_name=preset_name), obj["as_json"])


@adaptive_trail_magics_group.command("remove")
@click.argument("magics", nargs=-1, required=True)
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to update.")
@click.pass_context
def adaptive_trail_magics_remove_cmd(ctx, magics, experts_dir, preset_name):
    """Remove one or more magic numbers from the preset."""
    obj = ctx.obj
    parsed = _parse_cli_magics(magics)
    output(ea.remove_magics(parsed, experts_dir=experts_dir, preset_name=preset_name), obj["as_json"])


@adaptive_trail_tp_runner_group.command("set")
@click.option("--enabled/--disabled", default=True, show_default=True,
              help="Enable or disable TP removal.")
@click.option("--distance-points", default=10, show_default=True, type=int,
              help="Remove TP when current exit price is this close to TP.")
@click.option("--require-be/--no-require-be", default=True, show_default=True,
              help="Require BE/chandelier stage before removing TP.")
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to update.")
@click.pass_context
def adaptive_trail_tp_runner_set_cmd(ctx, enabled, distance_points, require_be, experts_dir, preset_name):
    """Update TP runner inputs in AdaptiveTrailEA.set."""
    obj = ctx.obj
    output(
        ea.set_tp_runner(
            enabled=enabled,
            distance_points=distance_points,
            require_be=require_be,
            experts_dir=experts_dir,
            preset_name=preset_name,
        ),
        obj["as_json"],
    )


@adaptive_trail_manual_group.command("set")
@click.option("--enabled/--disabled", default=True, show_default=True,
              help="Enable or disable magic-0 management.")
@click.option("--symbols", required=True,
              help="Comma-separated symbol whitelist for manual magic 0.")
@click.option("--experts-dir", default=None, help="MT5 MQL5\\Experts directory. Auto-detected by default.")
@click.option("--preset-name", default=ea.DEFAULT_PRESET_FILENAME, show_default=True,
              help="Preset filename to update.")
@click.pass_context
def adaptive_trail_manual_set_cmd(ctx, enabled, symbols, experts_dir, preset_name):
    """Update manual magic-0 whitelist inputs in AdaptiveTrailEA.set."""
    obj = ctx.obj
    parsed_symbols = _parse_cli_symbols(symbols)
    output(
        ea.set_manual_magic0(
            enabled=enabled,
            symbols=parsed_symbols,
            experts_dir=experts_dir,
            preset_name=preset_name,
        ),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Order command group
# ---------------------------------------------------------------------------

@main.group("order")
@click.pass_context
def order_group(ctx):
    """Order placement, modification, cancellation and fill-polling."""
    ctx.ensure_object(dict)


@order_group.command("list")
@click.option("--symbol", default=None, help="Filter by symbol.")
@click.option("--strategy-id", "strategy_id", default=None, help="Filter by strategy identifier.")
@click.pass_context
def order_list_cmd(ctx, symbol, strategy_id):
    """List currently pending orders."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(order.list_pending(symbol, strategy_id=strategy_id, cfg=obj["cfg"]), obj["as_json"])


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
    output(order.cancel(ticket, is_live_intent=obj["live_intent"]), obj["as_json"])


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
@click.option("--order-type", "order_type", default="market", show_default=True,
              type=click.Choice(["market", "limit", "stop"], case_sensitive=False),
              help="Validate a market, limit, or stop order.")
@click.option("--price", type=float, default=None,
              help="Pending entry price. Required when --order-type is limit or stop.")
@click.option("--strategy-id", "strategy_id", default=None, help="Strategy identifier.")
@click.option("--magic", type=int, default=None, help="Magic number override.")
@click.option("--deviation", default=20, show_default=True, type=int, help="Max price deviation in points.")
@click.option("--filling", default="auto", show_default=True, help="Filling mode: auto/FOK/IOC/RETURN.")
@click.pass_context
def order_dryrun_cmd(ctx, symbol, side, volume, risk_pct, sl, tp, order_type, price, strategy_id, magic, deviation, filling):
    """Validate an order without placing it (calls order_check, not order_send)."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    result = order.dryrun(
        symbol, side,
        order_type=order_type,
        price=price,
        volume=volume, risk_pct=risk_pct,
        sl=sl, tp=tp,
        strategy_id=strategy_id, magic=magic,
        deviation=deviation, filling=filling,
        cfg=obj["cfg"],
        is_live_intent=obj["live_intent"],
    )
    output(result, obj["as_json"])


# ---------------------------------------------------------------------------
# Position command group
# ---------------------------------------------------------------------------

@main.group("position")
@click.pass_context
def position_group(ctx):
    """Open position management: list, show, close, move SL, breakeven."""
    ctx.ensure_object(dict)


@position_group.command("list")
@click.option("--symbol", default=None, help="Filter by symbol.")
@click.pass_context
def position_list_cmd(ctx, symbol):
    """List all open positions (optionally filtered by --symbol)."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.list(symbol), obj["as_json"])


@position_group.command("show")
@click.argument("ticket", type=int)
@click.pass_context
def position_show_cmd(ctx, ticket):
    """Show detail for a single open position TICKET."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.show(ticket), obj["as_json"])


@position_group.command("close")
@click.argument("ticket", type=int)
@click.option("--volume", type=float, default=None, help="Partial close volume (default: full).")
@click.pass_context
def position_close_cmd(ctx, ticket, volume):
    """Close (fully or partially) the open position TICKET."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.close(ticket, volume, is_live_intent=obj["live_intent"]), obj["as_json"])


@position_group.command("close-all")
@click.option("--symbol", default=None, help="Close only positions for SYMBOL.")
@click.pass_context
def position_close_all_cmd(ctx, symbol):
    """Close all open positions (optionally restricted to --symbol)."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.close_all(symbol, is_live_intent=obj["live_intent"]), obj["as_json"])


@position_group.command("move-sl")
@click.argument("ticket", type=int)
@click.option("--sl", required=True, type=float, help="New stop-loss price.")
@click.pass_context
def position_move_sl_cmd(ctx, ticket, sl):
    """Move the stop-loss for open position TICKET to --sl."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.move_sl(ticket, sl, is_live_intent=obj["live_intent"]), obj["as_json"])


@position_group.command("breakeven")
@click.argument("ticket", type=int)
@click.option("--buffer-points", "buffer_points", default=0, show_default=True, type=int,
              help="Extra points beyond open price in the trade's favour.")
@click.pass_context
def position_breakeven_cmd(ctx, ticket, buffer_points):
    """Move SL to breakeven (open price ± buffer) for position TICKET."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(position.breakeven(ticket, buffer_points, is_live_intent=obj["live_intent"]), obj["as_json"])


# ---------------------------------------------------------------------------
# History command group
# ---------------------------------------------------------------------------

@main.group("history")
@click.pass_context
def history_group(ctx):
    """Trade history: orders, deals, and performance statistics."""
    ctx.ensure_object(dict)


@history_group.command("orders")
@click.option("--from", "date_from", required=True, help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--to", "date_to", required=True, help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--symbol", default=None, help="Filter by symbol.")
@click.option("--strategy-id", "strategy_id", default=None, help="Filter by strategy identifier.")
@click.pass_context
def history_orders_cmd(ctx, date_from, date_to, symbol, strategy_id):
    """Historical orders in [--from, --to], optionally filtered."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        history.orders(_parse_date(date_from), _parse_date(date_to), symbol=symbol,
                       strategy_id=strategy_id, cfg=obj["cfg"]),
        obj["as_json"],
    )


@history_group.command("deals")
@click.option("--from", "date_from", required=True, help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--to", "date_to", required=True, help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--symbol", default=None, help="Filter by symbol.")
@click.option("--strategy-id", "strategy_id", default=None, help="Filter by strategy identifier.")
@click.pass_context
def history_deals_cmd(ctx, date_from, date_to, symbol, strategy_id):
    """Historical deals in [--from, --to], optionally filtered."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        history.deals(_parse_date(date_from), _parse_date(date_to), symbol=symbol,
                      strategy_id=strategy_id, cfg=obj["cfg"]),
        obj["as_json"],
    )


@history_group.command("stats")
@click.option("--from", "date_from", required=True, help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--to", "date_to", required=True, help="End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS).")
@click.option("--strategy-id", "strategy_id", default=None, help="Scope to one strategy identifier.")
@click.pass_context
def history_stats_cmd(ctx, date_from, date_to, strategy_id):
    """Performance statistics for [--from, --to], optionally scoped to one strategy."""
    obj = ctx.obj
    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return
    output(
        history.stats(_parse_date(date_from), _parse_date(date_to),
                      strategy_id=strategy_id, cfg=obj["cfg"]),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Chart command group
# ---------------------------------------------------------------------------

@main.group("chart")
@click.pass_context
def chart_group(ctx):
    """Chart controls and Depth of Market snapshots."""
    ctx.ensure_object(dict)


@chart_group.command("switch-tf")
@click.argument("timeframe", type=click.Choice(list(chart.TIMEFRAMES), case_sensitive=False))
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--chart-id", type=int, default=None,
              help="Target child chart HWND returned by 'chart list'.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after toolbar click before title verification.")
@click.pass_context
def chart_switch_tf_cmd(ctx, timeframe, window_substring, chart_id, settle_seconds):
    """Switch the active MT5 chart timeframe."""
    obj = ctx.obj
    output(
        chart.switch_tf(timeframe, window_substring=window_substring,
                        settle_seconds=settle_seconds, chart_id=chart_id),
        obj["as_json"],
    )


@chart_group.command("list")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.pass_context
def chart_list_cmd(ctx, window_substring):
    """List open MT5 child chart windows."""
    obj = ctx.obj
    output(chart.list_charts(window_substring=window_substring), obj["as_json"])


@chart_group.command("current")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--chart-id", type=int, default=None,
              help="Target child chart HWND returned by 'chart list'.")
@click.pass_context
def chart_current_cmd(ctx, window_substring, chart_id):
    """Show the currently matched MT5 chart window title."""
    obj = ctx.obj
    output(chart.current_title(window_substring=window_substring, chart_id=chart_id), obj["as_json"])


@chart_group.command("symbol")
@click.argument("symbol")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--chart-id", type=int, default=None,
              help="Target child chart HWND returned by 'chart list'.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after symbol change before title verification.")
@click.pass_context
def chart_symbol_cmd(ctx, symbol, window_substring, chart_id, settle_seconds):
    """Activate or switch an MT5 chart symbol and verify it in the child title."""
    obj = ctx.obj
    output(
        chart.symbol(symbol, window_substring=window_substring,
                     settle_seconds=settle_seconds, chart_id=chart_id),
        obj["as_json"],
    )


@chart_group.command("ensure")
@click.argument("symbol")
@click.option("--timeframe", default="M15", show_default=True,
              help="Timeframe to leave active. Use 'none' to only ensure symbol.")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--chart-id", type=int, default=None,
              help="Target child chart HWND returned by 'chart list'.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after symbol/timeframe changes before title verification.")
@click.pass_context
def chart_ensure_cmd(ctx, symbol, timeframe, window_substring, chart_id, settle_seconds):
    """Ensure the active MT5 chart is on SYMBOL and optional timeframe."""
    obj = ctx.obj
    output(
        chart.ensure_chart(
            symbol,
            timeframe=timeframe,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
            chart_id=chart_id,
        ),
        obj["as_json"],
    )


@chart_group.command("depth-of-market")
@click.argument("symbol")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after opening the DOM panel.")
@click.pass_context
def chart_depth_of_market_cmd(ctx, symbol, window_substring, settle_seconds):
    """Open Charts > Depth Of Market for SYMBOL."""
    obj = ctx.obj
    output(
        chart.open_depth_of_market(
            symbol,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
        ),
        obj["as_json"],
    )


@chart_group.command("dom")
@click.argument("symbol")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after opening the DOM panel.")
@click.pass_context
def chart_dom_cmd(ctx, symbol, window_substring, settle_seconds):
    """Alias for chart depth-of-market."""
    obj = ctx.obj
    output(
        chart.open_depth_of_market(
            symbol,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
        ),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Screenshot command group
# ---------------------------------------------------------------------------

@main.group("screenshot")
@click.pass_context
def screenshot_group(ctx):
    """Screen capture: take, annotate, and list screenshots."""
    ctx.ensure_object(dict)


@screenshot_group.command("take")
@click.option("--output", "output_path", default=None, help="Output file path.")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--monitor", type=int, default=None,
              help="Monitor index (0=primary). Overrides screenshot_monitor config.")
@click.pass_context
def screenshot_take_cmd(ctx, output_path, window_substring, monitor):
    """Capture the MT5 window and save as PNG."""
    obj = ctx.obj
    output(
        screenshot.take(output_path=output_path, window_substring=window_substring,
                        monitor=monitor, cfg=obj["cfg"]),
        obj["as_json"],
    )


@screenshot_group.command("annotate")
@click.option("--input", "input_path", required=True, help="Input PNG path.")
@click.option("--output", "output_path", required=True, help="Output PNG path.")
@click.option("--text", required=True, help="Text to overlay.")
@click.option("--xy", nargs=2, type=int, default=(10, 10), show_default=True,
              help="Text position as two integers: X Y.")
@click.pass_context
def screenshot_annotate_cmd(ctx, input_path, output_path, text, xy):
    """Add a text overlay to an existing screenshot."""
    obj = ctx.obj
    output(screenshot.annotate(input_path, output_path, text, tuple(xy)), obj["as_json"])


@screenshot_group.command("list")
@click.option("--dir", "directory", default=None,
              help="Directory to list (default: config screenshot_path).")
@click.pass_context
def screenshot_list_cmd(ctx, directory):
    """List saved screenshots sorted by newest first."""
    obj = ctx.obj
    output(screenshot.list(directory=directory, cfg=obj["cfg"]), obj["as_json"])


@screenshot_group.command("tda")
@click.argument("symbol")
@click.option("--timeframes", default="D1,H4,H1,M15,M5,M1", show_default=True,
              help="Comma-separated timeframe list.")
@click.option("--output-dir", default=None,
              help="Directory for generated PNGs. Defaults to screenshot.output_dir/config/temp.")
@click.option("--crop", type=click.Choice(["chart", "window", "none"]), default="chart",
              show_default=True, help="Post-capture crop mode.")
@click.option("--max-width", type=int, default=1280, show_default=True,
              help="Resize captures wider than this value. Use 0 to disable.")
@click.option("--window", "window_substring", default="MT5", show_default=True,
              help="Window title substring to target.")
@click.option("--chart-id", type=int, default=None,
              help="Target child chart HWND returned by 'chart list'.")
@click.option("--monitor", type=int, default=None,
              help="Monitor index (0=primary). Overrides screenshot_monitor config.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after each chart switch before capture.")
@click.option("--final-timeframe", default="M15", show_default=True,
              help="Timeframe to leave the chart on after capture. Use 'none' to leave the last captured TF.")
@click.option("--visual-manifest/--no-visual-manifest", default=True, show_default=True,
              help="Attach the Ehukai indicator visual legend/contract to the result.")
@click.option("--context/--no-context", "structured_context", default=True, show_default=True,
              help="Attach recomputed structure and FVG context for each frame.")
@click.option("--manifest/--no-manifest", "write_manifest", default=True, show_default=True,
              help="Write a sibling JSON manifest next to the PNG captures.")
@click.option("--context-bars", type=int, default=300, show_default=True,
              help="Bars used for structured TDA/FVG context.")
@click.option("--fvg-limit", type=int, default=8, show_default=True,
              help="Maximum open/partial FVG zones per frame in structured context.")
@click.pass_context
def screenshot_tda_cmd(ctx, symbol, timeframes, output_dir, crop, max_width,
                       window_substring, chart_id, monitor, settle_seconds, final_timeframe,
                       visual_manifest, structured_context, write_manifest,
                       context_bars, fvg_limit):
    """Capture visual top-down-analysis frames for SYMBOL."""
    obj = ctx.obj
    if structured_context:
        # Best-effort data-channel initialization. Screenshot capture should
        # still be able to run if the Python bridge cannot connect; per-frame
        # context will carry its own fail-soft error details in that case.
        _ensure_connected(obj["cfg"])
    output(
        screenshot.tda(
            symbol,
            timeframes=timeframes,
            output_dir=output_dir,
            crop=crop,
            max_width=max_width or None,
            monitor=monitor,
            cfg=obj["cfg"],
            window_substring=window_substring,
            settle_seconds=settle_seconds,
            final_timeframe=final_timeframe,
            visual_manifest=visual_manifest,
            structured_context=structured_context,
            write_manifest=write_manifest,
            context_bars=context_bars,
            fvg_limit=fvg_limit,
            chart_id=chart_id,
        ),
        obj["as_json"],
    )


@screenshot_group.command("dom")
@click.argument("symbol")
@click.option("--output", "output_path", default=None, help="Output file path.")
@click.option("--output-dir", default=None,
              help="Directory for generated PNG. Defaults to screenshot.output_dir/config/temp.")
@click.option("--crop", type=click.Choice(["window", "none"]), default="window",
              show_default=True, help="Post-capture crop mode.")
@click.option("--max-width", type=int, default=1280, show_default=True,
              help="Resize captures wider than this value. Use 0 to disable.")
@click.option("--window", "window_substring", default=None,
              help="MT5 window title substring. Defaults to MT5.")
@click.option("--monitor", type=int, default=None,
              help="Monitor index (0=primary). Overrides screenshot_monitor config.")
@click.option("--open/--no-open", "open_panel", default=True, show_default=True,
              help="Open Charts > Depth Of Market before capture.")
@click.option("--close/--no-close", "close_panel", default=True, show_default=True,
              help="Close the DOM panel after capture. Use --no-close to inspect it manually.")
@click.option("--settle-seconds", type=float, default=0.5, show_default=True,
              help="Delay after opening the DOM panel before capture.")
@click.pass_context
def screenshot_dom_cmd(ctx, symbol, output_path, output_dir, crop, max_width,
                       window_substring, monitor, open_panel, close_panel, settle_seconds):
    """Capture the GUI Depth of Market window for SYMBOL."""
    obj = ctx.obj
    output(
        screenshot.dom(
            symbol,
            output_path=output_path,
            output_dir=output_dir,
            crop=crop,
            max_width=max_width or None,
            monitor=monitor,
            cfg=obj["cfg"],
            window_substring=window_substring,
            open_panel=open_panel,
            close_panel=close_panel,
            settle_seconds=settle_seconds,
        ),
        obj["as_json"],
    )


# ---------------------------------------------------------------------------
# Kill-switch command (top-level, not a group)
# ---------------------------------------------------------------------------

@main.command("kill-switch")
@click.option("--symbol", default=None, help="Scope to one symbol.")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.pass_context
def kill_switch_cmd(ctx, symbol, yes):
    """Close ALL open positions and cancel ALL pending orders.

    Continues on per-ticket failure so the account is maximally flattened
    even when individual operations fail (spec §7.4).
    """
    obj = ctx.obj

    if not yes:
        scope = f" for {symbol}" if symbol else ""
        if not click.confirm(
            f"Close all positions and cancel all pending orders{scope}?",
            default=False,
        ):
            click.echo("Aborted.")
            return

    err = _ensure_connected(obj["cfg"])
    if err:
        output(err, obj["as_json"])
        return

    # --- Close positions -------------------------------------------------
    pos_result = position.close_all(symbol, is_live_intent=obj["live_intent"])
    if not pos_result.get("ok"):
        output(pos_result, obj["as_json"])
        return
    pos_entries: list[dict] = [
        {"ticket": e["ticket"], "ok": e["result"] != "error", **({"error": e["error"]} if e["result"] == "error" else {})}
        for e in pos_result["data"]
    ]

    # --- Cancel pending orders -------------------------------------------
    ord_result = order.cancel_all_pending(symbol, is_live_intent=obj["live_intent"])
    if not ord_result.get("ok"):
        output(ord_result, obj["as_json"])
        return
    ord_entries: list[dict] = [
        {"ticket": e["ticket"], "ok": e["result"] != "error", **({"error": e["error"]} if e["result"] == "error" else {})}
        for e in ord_result["data"]
    ]

    output({"ok": True, "data": pos_entries + ord_entries}, obj["as_json"])
