"""Tests for the mt5_mcp MCP server glue.

These exercise the tool wrappers in isolation: connection handling, envelope
pass-through, and argument threading. The MCP transport itself (FastMCP) is not
exercised here — build_server() construction is covered by an importorskip test
so the suite does not hard-depend on the optional `mcp` package.
"""
import pytest


@pytest.fixture
def srv(monkeypatch):
    import mt5_mcp.server as server
    # Pretend the bridge is already connected (no real MT5 contact) and give a
    # deterministic empty config so tools don't touch the filesystem.
    monkeypatch.setattr(server, "_bridge_is_connected", lambda: True)
    monkeypatch.setattr(server, "_load_config", lambda: {})
    return server


def test_market_info_passes_symbol_and_returns_envelope(srv, monkeypatch):
    monkeypatch.setattr(srv._market, "info", lambda s: {"ok": True, "data": {"symbol": s}})
    result = srv.market_info("EURUSD")
    assert result["ok"] is True
    assert result["data"]["symbol"] == "EURUSD"


def test_status_marks_connected(srv, monkeypatch):
    monkeypatch.setattr(srv._account, "info", lambda: {"ok": True, "data": {"balance": 100.0}})
    result = srv.status()
    assert result["ok"] is True
    assert result["data"]["connected"] is True


def test_position_list_threads_symbol(srv, monkeypatch):
    captured = {}
    def stub(symbol=None):
        captured["symbol"] = symbol
        return {"ok": True, "data": []}
    monkeypatch.setattr(srv._positions, "list", stub)
    srv.position_list(symbol="EURUSD")
    assert captured["symbol"] == "EURUSD"


def test_order_dryrun_threads_cfg_and_safe_non_live_intent(srv, monkeypatch):
    """The MCP dryrun tool must thread cfg and default is_live_intent=False —
    it validates intent without ever arming a live mutation."""
    captured = {}
    def stub(*args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return {"ok": True, "data": {"dry_run": True}}
    monkeypatch.setattr(srv._orders, "dryrun", stub)
    result = srv.order_dryrun("EURUSD", "buy", volume=0.01, sl=1.1600)
    assert result["ok"] is True
    assert captured["is_live_intent"] is False
    assert isinstance(captured["cfg"], dict)


def test_connection_failure_returns_fail_envelope(monkeypatch):
    import mt5_mcp.server as server
    monkeypatch.setattr(server, "_bridge_is_connected", lambda: False)
    monkeypatch.setattr(server, "_load_config", lambda: {})
    def boom(**kwargs):
        raise RuntimeError("no terminal")
    monkeypatch.setattr(server, "_bridge_connect", boom)
    result = server.market_info("EURUSD")
    assert result["ok"] is False
    assert result["error"]["code"] == "MT5_CONNECTION_ERROR"


def test_no_live_mutation_tools_exposed(srv):
    """Safety: the MCP surface is read + dry-run only. No live order/position
    mutation tools are registered."""
    tool_names = {fn.__name__ for fn in srv.TOOLS}
    for forbidden in ("order_place_market", "position_close", "order_cancel",
                      "position_close_all", "order_place_limit"):
        assert forbidden not in tool_names


def test_build_server_registers_all_tools():
    pytest.importorskip("mcp")
    import mt5_mcp.server as server
    built = server.build_server()
    assert built is not None
    # every TOOLS entry should be a plain callable with a docstring (its MCP description)
    for fn in server.TOOLS:
        assert callable(fn)
        assert fn.__doc__, f"{fn.__name__} needs a docstring for its MCP tool description"
