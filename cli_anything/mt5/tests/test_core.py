"""
Unit tests for the MT5 CLI core and bridge layers.
All tests use the MagicMock MetaTrader5 stub installed by conftest.py.
No real MT5 terminal is required.
"""
import threading

import pytest

from cli_anything.mt5.utils import mt5_backend as bridge


# ===========================================================================
# Task 1 — Package scaffold
# ===========================================================================

class TestPackageImports:
    def test_bridge_importable(self):
        """Proves package layout + conftest mock are wired correctly."""
        from cli_anything.mt5.utils import mt5_backend  # noqa: F401

    def test_project_importable(self):
        from cli_anything.mt5.core import project  # noqa: F401


# ===========================================================================
# Task 2 — Bridge (mt5_backend.py)
# ===========================================================================

class TestBridge:
    def test_connect_idempotent(self, mt5m):
        bridge.connect("u", "p", "srv")
        bridge.connect("u", "p", "srv")
        assert mt5m.initialize.call_count == 1

    def test_connect_failure_raises(self, mt5m):
        mt5m.initialize.return_value = False
        with pytest.raises(ConnectionError):
            bridge.connect("u", "p", "srv")

    def test_mt5_call_dispatches_under_lock(self, mt5m):
        bridge.connect("u", "p", "srv")
        bridge.mt5_call("account_info")
        mt5m.account_info.assert_called_once()

    def test_ensure_symbol_calls_symbol_select_true(self, mt5m):
        mt5m.symbol_select.return_value = True
        bridge.connect("u", "p", "srv")
        result = bridge.ensure_symbol("USDJPY")
        mt5m.symbol_select.assert_called_with("USDJPY", True)
        assert result is True

    def test_lock_is_threading_lock(self):
        assert isinstance(bridge._lock, type(threading.Lock()))

    def test_constants_exported(self):
        assert hasattr(bridge, "ORDER_TYPE_BUY")
        assert hasattr(bridge, "ORDER_TYPE_SELL")
        assert hasattr(bridge, "TRADE_ACTION_DEAL")
        assert hasattr(bridge, "ORDER_FILLING_FOK")
        assert hasattr(bridge, "ACCOUNT_TRADE_MODE_DEMO")
        assert hasattr(bridge, "ACCOUNT_TRADE_MODE_REAL")
        assert hasattr(bridge, "TIMEFRAME_M1")
        assert hasattr(bridge, "TIMEFRAME_MN1")
        assert hasattr(bridge, "COPY_TICKS_ALL")


# ===========================================================================
# Task 3 — Config (core/project.py)
# ===========================================================================

class TestProject:
    def test_load_returns_defaults_when_no_file_no_env(self, tmp_path, monkeypatch):
        from cli_anything.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        cfg = project.load()
        assert cfg["timeout"] == 10000
        assert cfg["magic"] == 88888
        assert cfg["live"] is False
        assert cfg["login"] is None

    def test_load_file_overrides_defaults(self, tmp_path, monkeypatch):
        import json
        from cli_anything.mt5.core import project
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps({"login": 99999, "server": "Demo"}))
        monkeypatch.setattr(project, "CONFIG_PATH", cfg_file)
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        cfg = project.load()
        assert cfg["login"] == 99999
        assert cfg["server"] == "Demo"
        assert cfg["timeout"] == 10000  # still defaulted

    def test_load_env_overrides_file(self, tmp_path, monkeypatch):
        import json
        from cli_anything.mt5.core import project
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps({"login": 12345678}))
        monkeypatch.setattr(project, "CONFIG_PATH", cfg_file)
        monkeypatch.setenv("MT5_LOGIN", "99")
        monkeypatch.delenv("MT5_PASSWORD", raising=False)
        monkeypatch.delenv("MT5_SERVER", raising=False)
        monkeypatch.delenv("MT5_LIVE", raising=False)
        cfg = project.load()
        assert cfg["login"] == 99

    def test_load_overrides_win(self, tmp_path, monkeypatch):
        from cli_anything.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        cfg = project.load(overrides={"server": "X"})
        assert cfg["server"] == "X"

    def test_load_live_env_truthy_values(self, tmp_path, monkeypatch):
        from cli_anything.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setenv("MT5_LIVE", "1")
        cfg = project.load()
        assert cfg["live"] is True

        monkeypatch.setenv("MT5_LIVE", "0")
        cfg = project.load()
        assert cfg["live"] is False

        monkeypatch.delenv("MT5_LIVE")
        cfg = project.load()
        assert cfg["live"] is False

    def test_save_round_trip(self, tmp_path, monkeypatch):
        from cli_anything.mt5.core import project
        target = tmp_path / "cfg.json"
        monkeypatch.setattr(project, "CONFIG_PATH", target)
        data = {**project.DEFAULTS, "login": 777, "server": "TestSrv"}
        project.save(data)
        assert target.exists()
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        loaded = project.load()
        assert loaded["login"] == 777
        assert loaded["server"] == "TestSrv"

    def test_mask_secrets_replaces_password(self):
        from cli_anything.mt5.core import project
        cfg = {**project.DEFAULTS, "password": "super-secret"}
        masked = project.mask_secrets(cfg)
        assert masked["password"] == "***"
        assert cfg["password"] == "super-secret"  # original unchanged

    def test_strategy_ids_round_trips_through_save_load(self, tmp_path, monkeypatch):
        import json
        from cli_anything.mt5.core import project
        target = tmp_path / "cfg.json"
        monkeypatch.setattr(project, "CONFIG_PATH", target)
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        data = {**project.DEFAULTS, "strategy_ids": {"gopher-gate": 12001}}
        project.save(data)
        loaded = project.load()
        assert loaded["strategy_ids"] == {"gopher-gate": 12001}
