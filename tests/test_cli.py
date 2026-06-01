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
import re
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
    for group in ("account", "alert", "chart", "config", "connect", "history",
                  "market", "order", "position", "rates", "screenshot",
                  "status"):
        assert group in result.output


def test_json_flag_works_after_subcommand(runner):
    """Agents and shell wrappers naturally append --json AFTER the subcommand
    (mt5 config retcode 10009 --json), the dominant CLI convention. It must work
    in any position, not only as a leading group flag."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["config", "retcode", "10009", "--json"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["retcode"] == 10009


def test_json_flag_still_works_as_leading_group_flag(runner):
    """The documented leading form must keep working unchanged."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "config", "retcode", "10009"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["retcode"] == 10009


def test_version_flag_prints_version_and_exits_0(runner):
    """`mt5 --version` is the universal CLI convention; it must work and exit 0."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "mt5" in result.output
    assert re.search(r"\d+\.\d+", result.output)


def test_unexpected_exception_still_emits_envelope_with_exit_0(runner):
    """An unexpected library-level exception must surface as a fail envelope on
    stdout with exit 0 — the always-exit-0/always-envelope contract that agents
    rely on (parse the envelope, never the exit code or stderr)."""
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected mt5 surprise")
    mp.setattr(cli_mod._market_mod, "info", boom)

    result = cli_runner.invoke(main, ["--json", "market", "info", "EURUSD"])

    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INTERNAL_ERROR"
    assert env["error"]["data"]["type"] == "RuntimeError"


# ---------------------------------------------------------------------------
# alert
# ---------------------------------------------------------------------------


def test_alert_list_threads_terminal_data_path_from_bridge(runner, tmp_path):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    connected_data_path = str(tmp_path / "connected_terminal")
    _stub(mp, cli_mod._alert_mod, "list_alerts",
          {"ok": True, "data": {"count": 0, "alerts": []}}, captured)
    mp.setattr(cli_mod, "_terminal_data_path", lambda cfg: connected_data_path)

    result = cli_runner.invoke(main, ["--json", "alert", "list"])

    env = json.loads(result.output)
    assert result.exit_code == 0
    assert env["ok"] is True
    assert captured["kwargs"]["alerts_path"] is None
    assert captured["kwargs"]["data_path"] == connected_data_path
    assert isinstance(captured["kwargs"]["cfg"], dict)


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
    """Invalid Click Choice must surface as a MT5_INVALID_PARAMS envelope
    via emit(), exit 0 — not as Click's default stderr usage + nonzero exit.
    The CLI contract is "always exit 0 with structured envelope" so agents
    can parse failures without reading exit codes."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "order", "market", "EURUSD",
                                      "junk", "--volume", "0.01", "--sl", "1.09"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    assert "junk" in env["error"]["message"]


def test_cli_missing_required_option_emits_envelope(runner):
    """Missing required --volume must also emit MT5_INVALID_PARAMS envelope."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "order", "market", "EURUSD",
                                      "buy", "--sl", "1.09"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"


def test_cli_bad_int_option_emits_envelope(runner):
    """Click int parser failure must emit MT5_INVALID_PARAMS envelope."""
    cli_runner, main, _ = runner
    result = cli_runner.invoke(main, ["--json", "order", "cancel", "not-an-int"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"


def test_order_poll_fill_converts_timeout_to_ms(runner, monkeypatch):
    """CLI --timeout is in seconds; library wants timeout_ms. Verify the
    boundary converts cleanly so the command does not crash with
    TypeError: poll_fill() got an unexpected keyword argument 'timeout'."""
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "poll_fill",
          {"ok": True, "data": {"filled": True, "ticket": 12345}}, captured)
    result = cli_runner.invoke(main, ["--json", "order", "poll-fill", "12345",
                                      "--timeout", "1.5"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is True
    assert captured["args"] == (12345,)
    assert captured["kwargs"] == {"timeout_ms": 1500}


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
    # cfg must be threaded so the real-account triple lock can read cfg["live"].
    assert isinstance(captured["kwargs"]["cfg"], dict)


def test_position_close_all_threads_symbol(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._positions_mod, "close_all",
          {"ok": True, "data": {"per_ticket": []}}, captured)
    cli_runner.invoke(main, ["--json", "position", "close-all",
                             "--symbol", "EURUSD", "--live"])
    assert captured["kwargs"]["symbol"] == "EURUSD"
    assert isinstance(captured["kwargs"]["cfg"], dict)


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


def test_history_orders_validates_dates_before_autoconnect(monkeypatch):
    """Local arg validation must run BEFORE any MT5 connection attempt.
    Previously a malformed date with no MT5 available returned
    MT5_CONNECTION_ERROR instead of MT5_INVALID_PARAMS, hiding the real
    issue and triggering an unwanted side-effect (connect attempt)."""
    _purge_cli_cache()
    from mt5_cli.bridge import mt5_backend as _bridge
    # Force bridge unconnected so _autoconnect would call _bridge_connect.
    monkeypatch.setattr(_bridge, "_initialized", False)

    from mt5.cli import main as cli_main
    import mt5.cli as cli_mod
    calls = {"count": 0}

    def fake_connect(**_kw):
        calls["count"] += 1
        raise RuntimeError("connect attempted")

    monkeypatch.setattr(cli_mod, "_bridge_connect", fake_connect)

    cli_runner = CliRunner()
    result = cli_runner.invoke(cli_main, ["--json", "history", "orders",
                                          "--from", "garbage"])
    assert result.exit_code == 0
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    # The critical assertion: _bridge_connect must NOT have been called.
    assert calls["count"] == 0, "history validate-then-connect: connect ran before validation"
    _purge_cli_cache()


def test_history_deals_validates_dates_before_autoconnect(monkeypatch):
    _purge_cli_cache()
    from mt5_cli.bridge import mt5_backend as _bridge
    monkeypatch.setattr(_bridge, "_initialized", False)

    from mt5.cli import main as cli_main
    import mt5.cli as cli_mod
    calls = {"count": 0}

    def fake_connect(**_kw):
        calls["count"] += 1
        raise RuntimeError("connect attempted")

    monkeypatch.setattr(cli_mod, "_bridge_connect", fake_connect)

    cli_runner = CliRunner()
    result = cli_runner.invoke(cli_main, ["--json", "history", "deals",
                                          "--to", "not-a-date"])
    env = json.loads(result.output)
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    assert calls["count"] == 0
    _purge_cli_cache()


def test_history_stats_validates_dates_before_autoconnect(monkeypatch):
    _purge_cli_cache()
    from mt5_cli.bridge import mt5_backend as _bridge
    monkeypatch.setattr(_bridge, "_initialized", False)

    from mt5.cli import main as cli_main
    import mt5.cli as cli_mod
    calls = {"count": 0}

    def fake_connect(**_kw):
        calls["count"] += 1
        raise RuntimeError("connect attempted")

    monkeypatch.setattr(cli_mod, "_bridge_connect", fake_connect)

    cli_runner = CliRunner()
    result = cli_runner.invoke(cli_main, ["--json", "history", "stats",
                                          "--from", "bad"])
    env = json.loads(result.output)
    assert env["error"]["code"] == "MT5_INVALID_PARAMS"
    assert calls["count"] == 0
    _purge_cli_cache()


# ---------------------------------------------------------------------------
# connect — override semantics (P2 #6)
# ---------------------------------------------------------------------------


def test_connect_overrides_reconnect_when_already_connected(runner, monkeypatch):
    """When --login/--password/--server are given AND bridge is already
    connected, the command must call reconnect_once(cfg) (shutdown +
    initialize). _autoconnect's idempotent-no-op path would otherwise
    silently ignore the overrides and report a reconnect that did not
    happen."""
    cli_runner, main, mp = runner  # fixture leaves _initialized=True
    import mt5.cli as cli_mod

    reconnect_calls = []

    def fake_reconnect_once(cfg):
        reconnect_calls.append(dict(cfg))
        return True

    monkeypatch.setattr(cli_mod, "_bridge_reconnect_once", fake_reconnect_once)

    connect_calls = []

    def fake_connect(**kw):
        connect_calls.append(kw)

    monkeypatch.setattr(cli_mod, "_bridge_connect", fake_connect)

    result = cli_runner.invoke(main, ["--json", "connect",
                                      "--login", "999", "--password", "pw",
                                      "--server", "NewServer"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert env["data"]["connected"] is True
    assert env["data"]["server"] == "NewServer"
    assert len(reconnect_calls) == 1
    assert reconnect_calls[0]["login"] == 999
    assert reconnect_calls[0]["password"] == "pw"
    assert reconnect_calls[0]["server"] == "NewServer"
    # _autoconnect-style _bridge_connect must NOT have been called
    assert connect_calls == []


def test_connect_no_overrides_short_circuits_through_autoconnect(runner, monkeypatch):
    """No overrides + already connected: stay on _autoconnect's idempotent
    no-op. reconnect_once must NOT fire — a shutdown+initialize cycle is
    expensive and the current session is fine."""
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod

    reconnect_calls = []

    def fake_reconnect_once(cfg):
        reconnect_calls.append(dict(cfg))
        return True

    monkeypatch.setattr(cli_mod, "_bridge_reconnect_once", fake_reconnect_once)

    result = cli_runner.invoke(main, ["--json", "connect"])
    env = json.loads(result.output)
    assert env["ok"] is True
    assert reconnect_calls == []


def test_connect_overrides_reports_failure_when_reconnect_returns_false(
    runner, monkeypatch,
):
    """reconnect_once can return False (initialize failed without raising).
    The CLI must surface that as a fail envelope, not claim success."""
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod

    monkeypatch.setattr(cli_mod, "_bridge_reconnect_once", lambda cfg: False)

    result = cli_runner.invoke(main, ["--json", "connect",
                                      "--server", "NewServer"])
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_CONNECTION_ERROR"


def test_connect_overrides_reports_failure_when_reconnect_raises(
    runner, monkeypatch,
):
    """reconnect_once can raise (e.g. mt5.shutdown raised). Surface that
    as MT5_CONNECTION_ERROR, not a Python traceback."""
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod

    def boom(cfg):
        raise RuntimeError("shutdown blew up")

    monkeypatch.setattr(cli_mod, "_bridge_reconnect_once", boom)

    result = cli_runner.invoke(main, ["--json", "connect", "--server", "X"])
    env = json.loads(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "MT5_CONNECTION_ERROR"
    assert "shutdown blew up" in env["error"]["message"]


# ---------------------------------------------------------------------------
# P3 bonus: order limit/stop/dryrun --live plumbing
# ---------------------------------------------------------------------------


def test_order_limit_threads_cfg_and_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_limit",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "limit", "EURUSD", "buy",
                             "--price", "1.05", "--volume", "0.01",
                             "--sl", "1.04", "--live"])
    kw = captured["kwargs"]
    assert "cfg" in kw
    assert kw["is_live_intent"] is True


def test_order_stop_threads_cfg_and_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "place_stop",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "order", "stop", "EURUSD", "buy",
                             "--price", "1.20", "--volume", "0.01",
                             "--sl", "1.19", "--live"])
    kw = captured["kwargs"]
    assert "cfg" in kw
    assert kw["is_live_intent"] is True


def test_order_dryrun_threads_cfg_and_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._orders_mod, "dryrun",
          {"ok": True, "data": {"dry_run": True}}, captured)
    cli_runner.invoke(main, ["--json", "order", "dryrun", "EURUSD", "buy",
                             "--volume", "0.01", "--sl", "1.09", "--live"])
    kw = captured["kwargs"]
    assert "cfg" in kw
    assert kw["is_live_intent"] is True


def test_position_move_sl_threads_is_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._positions_mod, "move_sl",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "position", "move-sl", "12345",
                             "--sl", "1.10", "--live"])
    kw = captured["kwargs"]
    assert kw["sl"] == 1.10
    assert kw["is_live_intent"] is True
    assert isinstance(kw["cfg"], dict)


def test_position_breakeven_threads_is_live(runner, monkeypatch):
    cli_runner, main, mp = runner
    import mt5.cli as cli_mod
    captured = {}
    _stub(mp, cli_mod._positions_mod, "breakeven",
          {"ok": True, "data": {"ticket": 1}}, captured)
    cli_runner.invoke(main, ["--json", "position", "breakeven", "12345",
                             "--buffer-points", "5", "--live"])
    kw = captured["kwargs"]
    assert kw["buffer_points"] == 5
    assert kw["is_live_intent"] is True
    assert isinstance(kw["cfg"], dict)


# ---------------------------------------------------------------------------
# P3 bonus: emit() edge cases (ok(None), list-of-dicts, nested, datetime, bytes)
# ---------------------------------------------------------------------------


def test_emit_ok_none_prints_OK_in_human_mode(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": None}, json_mode=False)
    captured = capsys.readouterr()
    assert "OK" in captured.out


def test_emit_list_of_dicts_uses_separator_in_human_mode(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": [{"a": 1}, {"b": 2}]}, json_mode=False)
    captured = capsys.readouterr()
    assert "---" in captured.out
    assert "a: 1" in captured.out
    assert "b: 2" in captured.out


def test_emit_empty_list_prints_empty_marker(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": []}, json_mode=False)
    captured = capsys.readouterr()
    assert "(empty)" in captured.out


def test_emit_nested_dict_in_human_mode_renders_as_json(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": {"outer": {"inner": 42}}}, json_mode=False)
    captured = capsys.readouterr()
    # _render JSON-encodes nested dicts so the line is parseable
    assert '"inner"' in captured.out
    assert "42" in captured.out


def test_emit_datetime_json_serializes_via_default(capsys):
    _purge_cli_cache()
    from datetime import datetime, timezone
    from mt5.emit import emit
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    emit({"ok": True, "data": {"dt": dt}}, json_mode=True)
    captured = capsys.readouterr()
    env = json.loads(captured.out)
    assert "2026-01-01" in env["data"]["dt"]


def test_emit_bytes_payload_renders_via_default(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": {"blob": b"abc"}}, json_mode=False)
    captured = capsys.readouterr()
    assert "blob:" in captured.out


def test_emit_scalar_payload_in_human_mode(capsys):
    _purge_cli_cache()
    from mt5.emit import emit
    emit({"ok": True, "data": "scalar-payload"}, json_mode=False)
    captured = capsys.readouterr()
    assert "scalar-payload" in captured.out


# ---------------------------------------------------------------------------
# P3 bonus: config show --no-mask-secrets exposes BOTH login AND password
# ---------------------------------------------------------------------------


def test_config_show_no_mask_secrets_keeps_login(runner, monkeypatch):
    """--no-mask-secrets is intentional opt-in to expose sensitive fields.
    Login is treated as sensitive in mask_secrets(); the un-masked path
    must surface it (otherwise the test boundary masks a regression where
    login secretly stays redacted)."""
    cli_runner, main, _ = runner
    import mt5.cli as cli_mod
    monkeypatch.setattr(
        cli_mod, "_config_load",
        lambda: {"login": 12345, "password": "secret123", "server": "X"},
    )
    result = cli_runner.invoke(main, ["--json", "config", "show",
                                      "--no-mask-secrets"])
    env = json.loads(result.output)
    assert env["data"]["login"] == 12345
    assert env["data"]["password"] == "secret123"


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
