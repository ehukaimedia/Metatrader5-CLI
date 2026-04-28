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

from cli_anything.mt5.core import account, project
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
