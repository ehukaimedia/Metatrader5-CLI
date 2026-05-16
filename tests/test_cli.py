"""Smoke tests for the mt5 CLI (mt5/cli.py).

Strategy: monkeypatch the library functions at the mt5.cli module level
so the CLI is exercised in isolation - we verify plumbing (arg parsing,
envelope formatting, --json/--live threading) not library behavior.
The library functions have their own unit tests in test_*.py.

For each command:
- json mode: assert JSON envelope shape on stdout
- human mode: assert stdout/stderr contains expected human text
- arg threading: assert the stubbed library function received the right kwargs
"""
import json
import sys

import pytest
from click.testing import CliRunner


def _purge_cli_cache():
    for name in list(sys.modules):
        if name == "mt5.cli" or name == "mt5.emit":
            sys.modules.pop(name, None)


@pytest.fixture
def runner(monkeypatch):
    """Returns a CliRunner with the bridge stubbed to skip MT5 connection."""
    _purge_cli_cache()

    # Stub bridge.connect so commands that call _autoconnect() don't try
    # to talk to a real MT5. is_connected() returns True so _autoconnect
    # is a no-op for the test.
    from mt5_cli.bridge import mt5_backend as _bridge
    monkeypatch.setattr(_bridge, "_initialized", True)

    from mt5.cli import main
    yield CliRunner(), main, monkeypatch
    _purge_cli_cache()


def _stub(monkeypatch, target_module, attr: str, returned: dict, captured=None):
    """Replace target_module.attr with a stub that captures kwargs.

    captured is a dict that gets populated with kwargs the stub received.
    """
    def stub(*args, **kwargs):
        if captured is not None:
            captured["args"] = args
            captured["kwargs"] = kwargs
        return returned
    monkeypatch.setattr(target_module, attr, stub)


# ---------------------------------------------------------------------------
# Top-level group / help / --json plumbing
# ---------------------------------------------------------------------------


def test_mt5_help_shows_all_groups(runner):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for group in ("account", "chart", "config", "connect", "history",
                  "market", "order", "position", "rates", "screenshot",
                  "status"):
        assert group in result.output


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_config_show_emits_envelope_with_cfg(runner, monkeypatch):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "config", "show"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert "filling" in env["data"]


def test_config_show_masks_secrets_by_default(runner, monkeypatch):
    cli_runner, main, _ = runner
    # Inject a cfg with a password via load() stub
    import mt5.cli as cli_mod
    monkeypatch.setattr(
        cli_mod, "_config_load",
        lambda: {"login": 12345, "password": "secret123", "server": "X", "live": False},
    )
    result = cli_runner.invoke(main, ["--json", "config", "show"])
    env = json.loads(result.output)
    assert env["data"]["password"] == "***"
    assert env["data"]["login"] == "***"


def test_config_show_no_mask_secrets_keeps_password(runner, monkeypatch):
    cli_runner, main, _ = runner
    import mt5.cli as cli_mod
    monkeypatch.setattr(
        cli_mod, "_config_load",
        lambda: {"login": 12345, "password": "secret123", "server": "X"},
    )
    result = cli_runner.invoke(main, ["--json", "config", "show", "--no-mask-secrets"])
    env = json.loads(result.output)
    assert env["data"]["password"] == "secret123"


def test_config_retcode_lookup_known(runner):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "config", "retcode", "10030"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["retcode"] == 10030
    assert "FOK" in env["data"]["help"]


def test_config_retcode_unknown_falls_back(runner):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "config", "retcode", "99999"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert "99999" in env["data"]["help"]


# ---------------------------------------------------------------------------
# account
# ---------------------------------------------------------------------------


def test_account_info_routes_to_library(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._account_mod, "info",
          {"ok": True, "data": {"balance": 100.0}}, captured)
    result = cli_runner.invoke(main, ["--json", "account", "info"])
    env = json.loads(result.output)
    assert env["data"]["balance"] == 100.0


def test_account_risk_passes_cfg(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._account_mod, "risk",
          {"ok": True, "data": {"safe_to_trade": True}}, captured)
    cli_runner.invoke(main, ["--json", "account", "risk"])
    # account.risk(cfg) — cfg passed positionally
    assert captured["args"]  # cfg was passed


# ---------------------------------------------------------------------------
# market
# ---------------------------------------------------------------------------


def test_market_info_passes_symbol(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._market_mod, "info",
          {"ok": True, "data": {"bid": 1.1}}, captured)
    cli_runner.invoke(main, ["--json", "market", "info", "EURUSD"])
    assert captured["args"] == ("EURUSD",)


def test_market_tick_human_output_format(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    _stub(mp, cli_mod._market_mod, "tick",
          {"ok": True, "data": {"symbol": "EURUSD", "bid": 1.1, "ask": 1.1001}})
    result = cli_runner.invoke(main, ["market", "tick", "EURUSD"])
    assert "symbol: EURUSD" in result.output
    assert "bid: 1.1" in result.output


def test_market_failure_emits_fail_envelope_in_human_mode(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    _stub(mp, cli_mod._market_mod, "depth",
          {"ok": False, "error": {"code": "MT5_NO_DATA", "message": "no DOM"}})
    # Click's CliRunner combines stdout + stderr into .output by default.
    result = cli_runner.invoke(main, ["market", "depth", "EURUSD"],
                               catch_exceptions=False)
    assert "FAIL" in result.output
    assert "MT5_NO_DATA" in result.output


# ---------------------------------------------------------------------------
# rates
# ---------------------------------------------------------------------------


def test_rates_fetch_passes_bars_kwarg(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._rates_mod, "fetch",
          {"ok": True, "data": []}, captured)
    cli_runner.invoke(main, ["--json", "rates", "fetch", "EURUSD", "H1", "--bars", "50"])
    assert captured["args"] == ("EURUSD", "H1", 50)


# ---------------------------------------------------------------------------
# order — focus on --live plumbing and arg threading
# ---------------------------------------------------------------------------


def test_order_market_routes_with_default_no_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_market",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "market", "EURUSD", "buy",
                             "--volume", "0.01", "--sl", "1.09"])
    kw = captured["kwargs"]
    assert kw["symbol"] == "EURUSD"
    assert kw["side"] == "buy"
    assert kw["volume"] == 0.01
    assert kw["sl"] == 1.09
    assert kw["is_live_intent"] is False  # --live not passed


def test_order_market_routes_with_live_flag(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_market",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "market", "EURUSD", "buy",
                             "--volume", "0.01", "--sl", "1.09", "--live"])
    assert captured["kwargs"]["is_live_intent"] is True


def test_order_limit_threads_price_to_library(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_limit",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "limit", "EURUSD", "buy",
                             "--price", "1.05", "--volume", "0.01",
                             "--sl", "1.04"])
    assert captured["kwargs"]["price"] == 1.05


def test_order_stop_threads_price_to_library(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_stop",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "stop", "EURUSD", "buy",
                             "--price", "1.20", "--volume", "0.01",
                             "--sl", "1.19"])
    assert captured["kwargs"]["price"] == 1.20


def test_order_dryrun_threads_order_type(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "dryrun",
          {"ok": True, "data": {"dry_run": True}}, captured)
    cli_runner.invoke(main, ["--json", "order", "dryrun", "EURUSD", "buy",
                             "--type", "limit", "--price", "1.10",
                             "--volume", "0.01", "--sl", "1.09"])
    kw = captured["kwargs"]
    assert kw["order_type"] == "limit"
    assert kw["price"] == 1.10


def test_order_cancel_routes_with_cfg(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "cancel",
          {"ok": True, "data": {"cancelled": True}}, captured)
    cli_runner.invoke(main, ["--json", "order", "cancel", "12345"])
    assert captured["args"] == (12345,)
    assert "cfg" in captured["kwargs"]
    assert captured["kwargs"]["is_live_intent"] is False


def test_order_cancel_all_threads_cfg(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "cancel_all_pending",
          {"ok": True, "data": {"per_ticket": []}}, captured)
    cli_runner.invoke(main, ["--json", "order", "cancel-all", "--live"])
    assert "cfg" in captured["kwargs"]
    assert captured["kwargs"]["is_live_intent"] is True


def test_order_modify_threads_cfg(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "modify",
          {"ok": True, "data": {"ticket": 1, "action": "SLTP"}}, captured)
    cli_runner.invoke(main, ["--json", "order", "modify", "12345",
                             "--sl", "1.10", "--live"])
    kw = captured["kwargs"]
    assert kw["sl"] == 1.10
    assert "cfg" in kw
    assert kw["is_live_intent"] is True


def test_order_rejects_invalid_side_at_cli_layer(runner):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["order", "market", "EURUSD", "junk",
                                      "--volume", "0.01", "--sl", "1.09"])
    assert result.exit_code != 0  # click choice-validation error
    assert "junk" in result.output or "junk" in (result.stderr_bytes or b"").decode()


# ---------------------------------------------------------------------------
# position
# ---------------------------------------------------------------------------


def test_position_close_threads_is_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._positions_mod, "close",
          {"ok": True, "data": {"closed": True}}, captured)
    cli_runner.invoke(main, ["--json", "position", "close", "12345", "--live"])
    assert captured["kwargs"]["is_live_intent"] is True


def test_position_close_all_threads_symbol(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._positions_mod, "close_all",
          {"ok": True, "data": {"per_ticket": []}}, captured)
    cli_runner.invoke(main, ["--json", "position", "close-all",
                             "--symbol", "EURUSD", "--live"])
    assert captured["kwargs"]["symbol"] == "EURUSD"


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


def test_history_orders_parses_iso_dates(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._history_mod, "orders",
          {"ok": True, "data": []}, captured)
    cli_runner.invoke(main, ["--json", "history", "orders",
                             "--from", "2026-01-01", "--to", "2026-05-15"])
    # Verify the dates were parsed to UTC datetimes
    from datetime import datetime, timezone
    assert captured["kwargs"]["date_from"] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert captured["kwargs"]["date_to"] == datetime(2026, 5, 15, tzinfo=timezone.utc)


def test_history_orders_rejects_garbage_date(runner, monkeypatch):
    cli_runner, main, mp = runner
    result = cli_runner.invoke(main, ["--json", "history", "orders",
                                      "--from", "garbage"])
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"


# ---------------------------------------------------------------------------
# chart (Win32 — stub the library functions directly)
# ---------------------------------------------------------------------------


def test_chart_find_window_returns_match(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    from mt5_cli.chart.chart import WindowMatch
    monkeypatch.setattr(cli_mod, "_chart_find_window",
                        lambda sub: WindowMatch(hwnd=1234, title="MetaTrader 5"))
    result = cli_runner.invoke(main, ["--json", "chart", "find-window"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["hwnd"] == 1234


def test_chart_find_window_emits_fail_when_missing(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_chart_find_window", lambda sub: None)
    result = cli_runner.invoke(main, ["--json", "chart", "find-window"])
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"


def test_chart_new_threads_timeframe(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_chart_new",
          {"ok": True, "data": {"hwnd": 9001}}, captured)
    cli_runner.invoke(main, ["--json", "chart", "new", "USDJPY",
                             "--timeframe", "H4"])
    assert captured["args"] == ("USDJPY",)
    assert captured["kwargs"]["timeframe"] == "H4"


def test_chart_attach_passes_chart_id(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_chart_attach",
          {"ok": True, "data": {"command_id": 5001}}, captured)
    cli_runner.invoke(main, ["--json", "chart", "attach", "MyEMA",
                             "--chart-id", "2500"])
    assert captured["args"] == ("MyEMA",)
    assert captured["kwargs"]["chart_id"] == 2500


def test_chart_attach_ea_no_confirm_flag(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_chart_attach_ea",
          {"ok": True, "data": {"command_id": 8001}}, captured)
    cli_runner.invoke(main, ["--json", "chart", "attach-ea", "MyEA",
                             "--no-confirm"])
    assert captured["kwargs"]["auto_confirm"] is False


def test_chart_cycle_threads_direction(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_chart_cycle",
          {"ok": True, "data": {"hwnd": 2700}}, captured)
    cli_runner.invoke(main, ["--json", "chart", "cycle", "--direction", "prev"])
    assert captured["kwargs"]["direction"] == "prev"


def test_chart_close_passes_chart_id(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_chart_close",
          {"ok": True, "data": {"closed": True}}, captured)
    cli_runner.invoke(main, ["--json", "chart", "close", "2500"])
    assert captured["args"] == (2500,)


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------


def test_screenshot_take_threads_window_substring(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_screenshot_take",
          {"ok": True, "data": {"path": "/tmp/x.png"}}, captured)
    cli_runner.invoke(main, ["--json", "screenshot", "take", "--window", "MT5"])
    assert captured["kwargs"]["window_substring"] == "MT5"


def test_screenshot_annotate_parses_xy(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod, "_screenshot_annotate",
          {"ok": True, "data": {"path": "out.png"}}, captured)
    cli_runner.invoke(main, ["--json", "screenshot", "annotate",
                             "in.png", "out.png", "hello",
                             "--xy", "50,80"])
    assert captured["kwargs"]["xy"] == (50, 80)


def test_screenshot_annotate_rejects_bad_xy(runner, monkeypatch):
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "screenshot", "annotate",
                                      "in.png", "out.png", "hello",
                                      "--xy", "notanint"])
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
