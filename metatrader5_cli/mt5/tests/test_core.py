"""
Unit tests for the MT5 CLI core and bridge layers.
All tests use the MagicMock MetaTrader5 stub installed by conftest.py.
No real MT5 terminal is required.
"""
import threading
from unittest.mock import MagicMock

import pytest

from metatrader5_cli.mt5.utils import mt5_backend as bridge


# ===========================================================================
# Task 1 — Package scaffold
# ===========================================================================

class TestPackageImports:
    def test_bridge_importable(self):
        """Proves package layout + conftest mock are wired correctly."""
        from metatrader5_cli.mt5.utils import mt5_backend  # noqa: F401

    def test_project_importable(self):
        from metatrader5_cli.mt5.core import project  # noqa: F401


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

    def test_connect_without_password_uses_bare_initialize(self, mt5m):
        """Regression: MT5 rejects password=None; logged-in terminals use bare initialize()."""
        bridge.connect(12345678, None, "Trading.comMarkets-MT5")
        mt5m.initialize.assert_called_once_with()

    def test_reconnect_without_password_uses_bare_initialize(self, mt5m):
        """Regression: reconnect_once follows the same bare-initialize path."""
        result = bridge.reconnect_once({
            "login": 12345678,
            "password": None,
            "server": "Trading.comMarkets-MT5",
            "timeout": 10000,
        })
        assert result is True
        mt5m.shutdown.assert_called_once()
        mt5m.initialize.assert_called_once_with()

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

    def test_disconnect_acquires_lock(self, mt5m):
        """Regression: disconnect() must serialize mt5.shutdown() under the lock."""
        from unittest.mock import MagicMock, patch
        lock_spy = MagicMock()
        lock_spy.__enter__ = MagicMock(return_value=None)
        lock_spy.__exit__ = MagicMock(return_value=False)
        with patch.object(bridge, "_lock", lock_spy):
            bridge.disconnect()
        lock_spy.__enter__.assert_called_once()
        mt5m.shutdown.assert_called_once()

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
        from metatrader5_cli.mt5.core import project
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
        from metatrader5_cli.mt5.core import project
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
        from metatrader5_cli.mt5.core import project
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
        from metatrader5_cli.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        cfg = project.load(overrides={"server": "X"})
        assert cfg["server"] == "X"

    def test_load_live_env_does_not_set_cfg_live(self, tmp_path, monkeypatch):
        """MT5_LIVE must NOT affect cfg["live"]; gate 3 checks it directly
        in _compose_live_intent so gates 1 and 3 stay independent (spec §7.1)."""
        from metatrader5_cli.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setenv("MT5_LIVE", "1")
        cfg = project.load()
        assert cfg["live"] is False  # env var alone must not satisfy gate 1

        monkeypatch.delenv("MT5_LIVE")
        cfg = project.load()
        assert cfg["live"] is False

    def test_save_round_trip(self, tmp_path, monkeypatch):
        from metatrader5_cli.mt5.core import project
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
        from metatrader5_cli.mt5.core import project
        cfg = {**project.DEFAULTS, "password": "super-secret"}
        masked = project.mask_secrets(cfg)
        assert masked["password"] == "***"
        assert cfg["password"] == "super-secret"  # original unchanged

    def test_strategy_ids_round_trips_through_save_load(self, tmp_path, monkeypatch):
        import json
        from metatrader5_cli.mt5.core import project
        target = tmp_path / "cfg.json"
        monkeypatch.setattr(project, "CONFIG_PATH", target)
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        data = {**project.DEFAULTS, "strategy_ids": {"gopher-gate": 12001}}
        project.save(data)
        loaded = project.load()
        assert loaded["strategy_ids"] == {"gopher-gate": 12001}


class TestEAHelpers:
    def test_adaptive_trail_add_magics_creates_preset(self, tmp_path):
        from metatrader5_cli.mt5.core import ea

        experts = tmp_path / "Experts"
        (experts / ea.EA_FILENAME).parent.mkdir(parents=True)
        (experts / ea.EA_FILENAME).write_text(
            'input string                  MagicNumbers                 = "113054";\n',
            encoding="utf-8",
        )

        result = ea.add_magics([162538], experts_dir=str(experts))

        assert result["ok"] is True
        assert result["data"]["magic_numbers"] == "113054,162538"
        preset = experts / ea.DEFAULT_PRESET_FILENAME
        assert preset.exists()
        assert "MagicNumbers=113054,162538" in preset.read_text(encoding="utf-16")

    def test_adaptive_trail_rejects_manual_magic_zero(self):
        from metatrader5_cli.mt5.core import ea

        with pytest.raises(ValueError, match="Magic 0"):
            ea.parse_magic_values("113054,0")

    def test_cli_adaptive_trail_magics_set_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        experts = tmp_path / "Experts"
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        result = CliRunner().invoke(
            mt5_cli.main,
            [
                "--json",
                "ea",
                "adaptive-trail",
                "magics",
                "set",
                "113054,162538",
                "--experts-dir",
                str(experts),
            ],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["magic_numbers"] == "113054,162538"

    def test_cli_adaptive_trail_tp_runner_set_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        experts = tmp_path / "Experts"
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        result = CliRunner().invoke(
            mt5_cli.main,
            [
                "--json",
                "ea",
                "adaptive-trail",
                "tp-runner",
                "set",
                "--enabled",
                "--distance-points",
                "15",
                "--experts-dir",
                str(experts),
            ],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        preset = experts / "AdaptiveTrailEA.set"
        text = preset.read_text(encoding="utf-16")
        assert "Allow_TP_Removal=true" in text
        assert "TP_Removal_Distance_Points=15" in text

    def test_cli_adaptive_trail_manual_magic0_set_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        experts = tmp_path / "Experts"
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        result = CliRunner().invoke(
            mt5_cli.main,
            [
                "--json",
                "ea",
                "adaptive-trail",
                "manual",
                "set",
                "--enabled",
                "--symbols",
                "USDJPY,EURUSD,GBPUSD,AUDUSD",
                "--experts-dir",
                str(experts),
            ],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        preset = experts / "AdaptiveTrailEA.set"
        text = preset.read_text(encoding="utf-16")
        assert "Allow_Manual_Magic_0=true" in text
        assert "Manual_Magic_0_Symbols=USDJPY,EURUSD,GBPUSD,AUDUSD" in text


# ===========================================================================
# Task 4 — Risk (core/risk.py)
# ===========================================================================

class TestRisk:
    # --- resolve_magic ---
    def test_resolve_magic_uses_config_map(self, cfg):
        from metatrader5_cli.mt5.core import risk
        cfg["strategy_ids"] = {"gopher-gate": 12001}
        assert risk.resolve_magic("gopher-gate", cfg) == 12001

    def test_resolve_magic_auto_derives_in_range_100k_180k(self, cfg):
        from metatrader5_cli.mt5.core import risk
        magic = risk.resolve_magic("my-strategy", cfg)
        assert 100000 <= magic < 180000

    def test_resolve_magic_deterministic(self, cfg):
        from metatrader5_cli.mt5.core import risk
        assert risk.resolve_magic("my-strategy", cfg) == risk.resolve_magic("my-strategy", cfg)

    def test_resolve_magic_default_when_no_id(self, cfg):
        from metatrader5_cli.mt5.core import risk
        assert risk.resolve_magic(None, cfg) == 88888

    def test_resolve_magic_rejects_configured_magic_out_of_range(self, cfg):
        from metatrader5_cli.mt5.core import risk
        cfg["strategy_ids"] = {"bad-strat": 150000}  # collides with auto-derived range
        with pytest.raises(ValueError, match="must be < 100000"):
            risk.resolve_magic("bad-strat", cfg)

    # --- compute_volume_from_risk_pct ---
    def test_compute_volume_from_risk_pct_basic(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        # equity=10000, risk_pct=1.0 → risk=$100
        # sl_distance = abs(155.00 - 154.50) / 0.001 = 500 points
        # volume = 100 / (500 * 0.9) = 0.222... → rounds to volume_step 0.01 → 0.22
        mt5m.account_info.return_value = MagicMock(equity=10000.0)
        mt5m.symbol_info.return_value = MagicMock(
            point=0.001, volume_min=0.01, volume_max=100.0,
            volume_step=0.01, trade_tick_value=0.9,
        )
        vol = risk.compute_volume_from_risk_pct("USDJPY", 1.0, 155.00, 154.50, cfg)
        assert isinstance(vol, float)
        assert vol == pytest.approx(0.22, abs=0.01)

    def test_compute_volume_rounds_to_volume_step(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(equity=10000.0)
        mt5m.symbol_info.return_value = MagicMock(
            point=0.0001, volume_min=0.01, volume_max=100.0,
            volume_step=0.05, trade_tick_value=1.0,
        )
        # sl_distance = abs(1.1000 - 1.0950) / 0.0001 = 50 points
        # volume = (10000*0.5/100) / (50 * 1.0) = 50/50 = 1.0 → multiple of 0.05
        vol = risk.compute_volume_from_risk_pct("EURUSD", 0.5, 1.1000, 1.0950, cfg)
        assert vol % 0.05 < 1e-9 or abs(vol % 0.05 - 0.05) < 1e-9

    def test_compute_volume_clamps_to_volume_min_max(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(equity=100.0)  # tiny account
        mt5m.symbol_info.return_value = MagicMock(
            point=0.001, volume_min=0.10, volume_max=100.0,
            volume_step=0.01, trade_tick_value=0.9,
        )
        vol = risk.compute_volume_from_risk_pct("USDJPY", 0.01, 155.00, 154.50, cfg)
        assert vol >= 0.10  # clamped up to volume_min

    # --- check_order guards (one per guard) ---
    def _happy_path_setup(self, mt5m, cfg):
        """Configure mt5m so check_order passes all guards."""
        mt5m.account_info.return_value = MagicMock(
            trade_mode=0, equity=10000.0, margin_free=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []

    def test_check_order_happy_path_passes(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result == {"ok": True}

    def test_check_order_rejects_strategy_id_too_long(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        long_id = "x" * 32
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, long_id, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_STRATEGY_ID_TOO_LONG"

    def test_check_order_rejects_live_gate(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(
            trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL,
            equity=10000.0, margin_free=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"

    def test_check_order_live_intent_true_passes_gate(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        # When is_live_intent=True, live gate should NOT fire even on real account
        mt5m.account_info.return_value = MagicMock(
            trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL,
            equity=10000.0, margin_free=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=True)
        assert result == {"ok": True}

    def test_check_order_rejects_symbol_not_allowed(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["symbol_allowlist"] = ["EURUSD"]
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_SYMBOL_NOT_ALLOWED"

    def test_check_order_rejects_max_lot_exceeded(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 3.0, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"

    def test_check_order_rejects_no_stop_loss(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 0.10, None, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_rejects_sl_too_close(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        # entry=155.00, sl=154.99 → distance = abs(155.00-154.99)/0.001 = 10 points < 50
        result = risk.check_order("USDJPY", "buy", 0.10, 154.99, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_rejects_spread_too_wide(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(
            trade_mode=0, equity=10000.0, margin_free=8000.0,
        )
        mt5m.positions_get.return_value = []
        # spread = (ask - bid) / point = (155.10 - 154.99) / 0.001 = 110 points > 30
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.10, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_SPREAD_TOO_WIDE"

    def test_check_order_rejects_hedge(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        # Existing BUY position on USDJPY; new order is also BUY so no hedge
        # Test: existing BUY, new SELL → hedge blocked
        existing = MM(symbol="USDJPY", type=0)  # type 0 = ORDER_TYPE_BUY
        mt5m.positions_get.return_value = [existing]
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "sell", 0.10, 155.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_HEDGE_BLOCKED"

    def test_check_order_rejects_max_positions(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        mt5m.positions_get.return_value = [MM(symbol="GBPUSD", type=0, profit=0)] * 5  # max_positions=5
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_POSITIONS"

    def test_check_order_rejects_insufficient_margin(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        # free_margin = 100, equity = 10000 → 1% < 20%
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=100.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INSUFFICIENT_MARGIN"

    def test_check_order_rejects_max_daily_loss(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        mt5m.positions_get.return_value = [MM(profit=-1500.0)]  # floating -1500
        # Realized deals: profit=-500, comm=-1, swap=-0.5 -> realized = -501.5
        # Total = -1500 + (-501.5) = -2001.5 <= -2000 -> fires
        deal = MM(profit=-500.0, commission=-1.0, swap=-0.5)
        mt5m.history_deals_get.return_value = [deal]
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_DAILY_LOSS"

    def test_check_order_rejects_rate_limit(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["max_orders_per_minute"] = 3
        for _ in range(3):
            r = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
            assert r == {"ok": True}
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_RATE_LIMIT"

    def test_rate_limiter_does_not_consume_slot_on_earlier_failure(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["max_orders_per_minute"] = 2
        # Make guard #4 (max lot) fail → slot should NOT be consumed
        for _ in range(5):
            r = risk.check_order("USDJPY", "buy", 99.0, 154.50, None, cfg, is_live_intent=False)
            assert r["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        assert len(risk._rate_limiter) == 0  # no slots consumed

    # --- daily_loss ---
    def test_daily_loss_includes_realized_and_floating(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.positions_get.return_value = [MM(profit=-20.0), MM(profit=-10.0)]  # floating -30
        deal = MM(profit=-15.0, commission=-2.0, swap=-0.5)
        mt5m.history_deals_get.return_value = [deal]
        result = risk.daily_loss(cfg)
        # realized = -15 + (-2) + (-0.5) = -17.5; floating = -30; total = -47.5
        assert result == pytest.approx(-47.5)

    def test_check_order_rejects_account_info_none(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        mt5m.account_info.return_value = None
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_tick_none(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = None
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_point_zero(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_equity_zero(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=0.0, margin_free=0.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INSUFFICIENT_MARGIN"

    # --- rate limiter sliding window ---
    def test_rate_limiter_sliding_window(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import risk
        import time
        self._happy_path_setup(mt5m, cfg)
        cfg["max_orders_per_minute"] = 10
        # Fill 10 slots successfully
        for _ in range(10):
            r = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
            assert r == {"ok": True}
        # 11th should fail
        r = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert r["error"]["code"] == "RISK_RATE_LIMIT"


# ===========================================================================
# Task 5 — CLI scaffold (mt5_cli.py)
# ===========================================================================

class TestCLI:
    def test_live_intent_requires_all_three(self, monkeypatch):
        from metatrader5_cli.mt5 import mt5_cli
        assert mt5_cli._compose_live_intent({"live": False}, True) is False
        assert mt5_cli._compose_live_intent({"live": True}, False) is False
        monkeypatch.delenv("MT5_LIVE", raising=False)
        assert mt5_cli._compose_live_intent({"live": True}, True) is False
        monkeypatch.setenv("MT5_LIVE", "1")
        assert mt5_cli._compose_live_intent({"live": True}, True) is True

    def test_live_gate_env_plus_flag_without_config_live_is_false(self, monkeypatch, tmp_path):
        """End-to-end: MT5_LIVE=1 + --live with no config live=true → live_intent False.
        Verifies gates 1 and 3 are independent (spec §7.1 P1 fix)."""
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("MT5_LIVE", "1")

        captured = {}

        def _fake_repl(ctx):
            captured["live_intent"] = ctx.obj["live_intent"]

        monkeypatch.setattr(mt5_cli, "_launch_repl", _fake_repl)
        runner = CliRunner()
        runner.invoke(mt5_cli.main, ["--live"])
        assert captured.get("live_intent") is False

    def test_exit_code_1_for_risk_error(self):
        from metatrader5_cli.mt5 import mt5_cli
        assert mt5_cli._exit_code_for("RISK_MAX_LOT_EXCEEDED") == 1
        assert mt5_cli._exit_code_for("MT5_INVALID_REQUEST") == 1

    def test_exit_code_2_for_connection_error(self):
        from metatrader5_cli.mt5 import mt5_cli
        assert mt5_cli._exit_code_for("MT5_CONNECTION_ERROR") == 2

    def test_output_human_mode_uses_red_for_error(self):
        import click
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli

        @click.command()
        def _cmd():
            mt5_cli.output(
                {"ok": False, "error": {"code": "RISK_MAX_LOT_EXCEEDED", "message": "too big"}},
                as_json=False,
            )

        runner = CliRunner()
        result = runner.invoke(_cmd, [])
        assert result.exit_code == 1
        assert "RISK_MAX_LOT_EXCEEDED" in result.output

    def test_main_no_args_invokes_repl_stub(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        called = []
        monkeypatch.setattr(mt5_cli, "_launch_repl", lambda ctx: called.append(True))
        runner = CliRunner()
        runner.invoke(mt5_cli.main, [])
        assert called, "REPL stub was not called when no subcommand is given"

    def test_config_show_masks_password(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps({"password": "secret123"}))
        monkeypatch.setattr(project, "CONFIG_PATH", cfg_file)
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["config", "show"])
        assert result.exit_code == 0
        assert "secret123" not in result.output
        assert "***" in result.output

    def test_config_show_json_mode_emits_envelope(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["--json", "config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "data" in data

    def test_config_test_success_envelope(self, mt5m, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["--json", "config", "test"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["connected"] is True


# ===========================================================================
# Task 6 — Account (core/account.py + CLI)
# ===========================================================================

class TestAccount:
    def _make_acc(self, **kwargs):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        defaults = dict(
            login=12345678, name="Test User", server="Trading.com-Demo",
            currency="USD", balance=10000.0, equity=10000.0,
            margin=0.0, margin_free=10000.0, margin_level=0.0,
            leverage=50, profit=0.0,
            trade_mode=bridge.ACCOUNT_TRADE_MODE_DEMO,
            trade_allowed=True,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    def test_account_info_happy_path(self, mt5m):
        from metatrader5_cli.mt5.core import account
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.account_info.return_value = self._make_acc(login=99999, currency="EUR")
        result = account.info()
        assert result["ok"] is True
        data = result["data"]
        assert data["login"] == 99999
        assert data["currency"] == "EUR"
        assert data["trade_mode"] == "demo"
        assert data["trade_allowed"] is True
        assert "free_margin" in data
        assert "leverage" in data

    def test_account_info_returns_connection_error_when_none(self, mt5m):
        from metatrader5_cli.mt5.core import account
        mt5m.account_info.return_value = None
        result = account.info()
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_CONNECTION_ERROR"

    def test_account_info_trade_mode_string_mapping(self, mt5m):
        from metatrader5_cli.mt5.core import account
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        cases = [
            (bridge.ACCOUNT_TRADE_MODE_DEMO, "demo"),
            (bridge.ACCOUNT_TRADE_MODE_CONTEST, "contest"),
            (bridge.ACCOUNT_TRADE_MODE_REAL, "real"),
        ]
        for raw_mode, expected_str in cases:
            mt5m.account_info.return_value = self._make_acc(trade_mode=raw_mode)
            result = account.info()
            assert result["data"]["trade_mode"] == expected_str, f"trade_mode={raw_mode!r}"

    def test_account_balance_subset_keys(self, mt5m):
        from metatrader5_cli.mt5.core import account
        mt5m.account_info.return_value = self._make_acc(
            balance=5000.0, equity=5100.0, currency="EUR"
        )
        result = account.balance()
        assert result["ok"] is True
        assert set(result["data"].keys()) == {"balance", "equity", "currency"}
        assert result["data"]["balance"] == 5000.0
        assert result["data"]["currency"] == "EUR"

    def test_account_risk_composes_envelope_correctly(self, mt5m, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import account
        mt5m.account_info.return_value = self._make_acc(
            equity=10000.0, margin_free=8000.0, currency="USD"
        )
        mt5m.positions_get.return_value = [MM(profit=10.0)]
        mt5m.history_deals_get.return_value = []
        result = account.risk(cfg)
        assert result["ok"] is True
        data = result["data"]
        assert set(data.keys()) == {
            "max_positions", "max_daily_loss", "daily_loss_used",
            "positions_used", "safe_to_trade", "currency",
        }
        assert data["positions_used"] == 1
        assert data["safe_to_trade"] is True
        assert data["currency"] == "USD"

    def test_cli_account_info_json_mode(self, mt5m, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        mt5m.account_info.return_value = self._make_acc(login=77777)
        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["--json", "account", "info"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["login"] == 77777


# ===========================================================================
# Task 7 — Market (core/market.py + CLI)
# ===========================================================================

class TestMarket:
    def _make_sym(self, **kwargs):
        from unittest.mock import MagicMock as MM
        defaults = dict(
            name="EURUSD", bid=1.08500, ask=1.08510, spread=10,
            digits=5, point=0.00001, trade_tick_value=1.0,
            volume_min=0.01, volume_step=0.01, volume_max=100.0,
            swap_long=-1.5, swap_short=0.5,
            filling_mode=1, trade_mode=0,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    def test_market_info_pip_size_eurusd_0_0001(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym(digits=5)
        result = market.info("EURUSD")
        assert result["ok"] is True
        assert result["data"]["pip_size"] == pytest.approx(0.0001)
        assert result["data"]["point"] == pytest.approx(0.00001)

    def test_market_info_pip_size_usdjpy_0_01(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym(name="USDJPY", digits=3)
        result = market.info("USDJPY")
        assert result["ok"] is True
        assert result["data"]["pip_size"] == pytest.approx(0.01)

    def test_market_info_calls_ensure_symbol(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym()
        market.info("EURUSD")
        mt5m.symbol_select.assert_called_with("EURUSD", True)

    def test_market_info_ensure_symbol_false_returns_error(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = False
        result = market.info("INVALID")
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_SYMBOL"

    def test_market_tick_calls_ensure_symbol(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(time=1700000000, bid=1.085, ask=1.086, last=0.0, volume=0)
        market.tick("EURUSD")
        mt5m.symbol_select.assert_called_with("EURUSD", True)

    def test_market_tick_iso8601(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(time=1700000000, bid=1.085, ask=1.086, last=0.0, volume=0)
        result = market.tick("EURUSD")
        assert result["ok"] is True
        time_str = result["data"]["time"]
        # Must parse as ISO-8601 without raising
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(time_str)
        assert dt.tzinfo is not None  # timezone-aware

    def test_market_depth_subscribes_reads_sorts_and_releases(self, mt5m):
        from collections import namedtuple
        from metatrader5_cli.mt5.core import market

        BookInfo = namedtuple("BookInfo", "type price volume volume_dbl")
        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = True
        mt5m.market_book_get.return_value = (
            BookInfo(1, 157.892, 25, 25.0),
            BookInfo(2, 157.889, 15, 15.0),
            BookInfo(1, 157.891, 10, 10.0),
            BookInfo(2, 157.890, 20, 20.0),
        )
        mt5m.market_book_release.return_value = True

        result = market.depth("USDJPY")

        assert result["ok"] is True
        data = result["data"]
        assert [row["price"] for row in data["asks"]] == [157.891, 157.892]
        assert [row["price"] for row in data["bids"]] == [157.890, 157.889]
        assert data["best_bid"] == pytest.approx(157.890)
        assert data["best_ask"] == pytest.approx(157.891)
        assert data["spread"] == pytest.approx(0.001)
        mt5m.symbol_select.assert_called_with("USDJPY", True)
        mt5m.market_book_add.assert_called_once_with("USDJPY")
        mt5m.market_book_get.assert_called_once_with("USDJPY")
        mt5m.market_book_release.assert_called_once_with("USDJPY")

    def test_market_depth_limits_levels_per_side(self, mt5m):
        from collections import namedtuple
        from metatrader5_cli.mt5.core import market

        BookInfo = namedtuple("BookInfo", "type price volume volume_dbl")
        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = True
        mt5m.market_book_get.return_value = (
            BookInfo(1, 1.1010, 1, 1.0),
            BookInfo(1, 1.1009, 1, 1.0),
            BookInfo(2, 1.1007, 1, 1.0),
            BookInfo(2, 1.1008, 1, 1.0),
        )

        result = market.depth("EURUSD", levels=1)

        assert result["ok"] is True
        assert len(result["data"]["asks"]) == 1
        assert len(result["data"]["bids"]) == 1
        assert result["data"]["asks"][0]["price"] == pytest.approx(1.1009)
        assert result["data"]["bids"][0]["price"] == pytest.approx(1.1008)

    def test_market_depth_subscribe_failure_returns_error(self, mt5m):
        from metatrader5_cli.mt5.core import market

        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = False
        mt5m.last_error.return_value = (4302, "Market book unavailable")

        result = market.depth("USDJPY")

        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_MARKET_BOOK_SUBSCRIBE_FAILED"
        assert result["error"]["mt5_retcode"] == 4302
        mt5m.market_book_get.assert_not_called()
        mt5m.market_book_release.assert_not_called()

    def test_market_depth_success_last_error_gets_broker_hint(self, mt5m):
        from metatrader5_cli.mt5.core import market

        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = False
        mt5m.last_error.return_value = (1, "Success")

        result = market.depth("USDJPY")

        assert result["ok"] is False
        assert "may not expose Depth of Market" in result["error"]["message"]

    def test_market_depth_get_failure_releases_subscription(self, mt5m):
        from metatrader5_cli.mt5.core import market

        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = True
        mt5m.market_book_get.return_value = None
        mt5m.last_error.return_value = (4303, "No market book data")

        result = market.depth("USDJPY")

        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_MARKET_BOOK_UNAVAILABLE"
        mt5m.market_book_release.assert_called_once_with("USDJPY")

    def test_cli_market_depth_json(self, mt5m, monkeypatch, tmp_path):
        import json
        from collections import namedtuple
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project

        BookInfo = namedtuple("BookInfo", "type price volume volume_dbl")
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        mt5m.symbol_select.return_value = True
        mt5m.market_book_add.return_value = True
        mt5m.market_book_get.return_value = (
            BookInfo(1, 1.1002, 10, 10.0),
            BookInfo(2, 1.1000, 20, 20.0),
        )

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "market", "depth", "EURUSD", "--levels", "1"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["symbol"] == "EURUSD"
        assert len(data["data"]["asks"]) == 1
        assert len(data["data"]["bids"]) == 1

    def test_cli_chart_depth_of_market_opens_gui_panel(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setattr(
            chart_module,
            "open_depth_of_market",
            lambda symbol, **kwargs: {
                "ok": True,
                "data": {"symbol": symbol, "menu": "Charts > Depth Of Market", "title": "[USDJPY,M1]"},
            },
        )

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "chart", "depth-of-market", "USDJPY"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["symbol"] == "USDJPY"
        assert data["data"]["menu"] == "Charts > Depth Of Market"

    def test_cli_chart_dom_alias_opens_gui_panel(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setattr(
            chart_module,
            "open_depth_of_market",
            lambda symbol, **kwargs: {
                "ok": True,
                "data": {"symbol": symbol, "menu": "Charts > Depth Of Market", "title": "[USDJPY,M1]"},
            },
        )

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "chart", "dom", "USDJPY"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["symbol"] == "USDJPY"
        assert data["data"]["menu"] == "Charts > Depth Of Market"

    def test_cli_chart_current_reports_title(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda **kwargs: {
                "ok": True,
                "data": {"hwnd": 101, "title": "12345678 - Trading.comMarkets-MT5 - [USDJPY,M15]"},
            },
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "chart", "current"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "[USDJPY,M15]" in data["data"]["title"]

    def test_cli_chart_list_reports_child_charts(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setattr(
            chart_module,
            "list_charts",
            lambda **kwargs: {
                "ok": True,
                "data": [
                    {"hwnd": 101, "symbol": "USDJPY", "timeframe": "M15", "title": "[USDJPY,M15]"},
                    {"hwnd": 202, "chart_id": 202, "symbol": "EURUSD", "timeframe": "H1", "title": "[EURUSD,H1]"},
                ],
            },
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "chart", "list"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert {chart["symbol"] for chart in data["data"]} == {"USDJPY", "EURUSD"}
        assert data["data"][1]["chart_id"] == 202

    def test_cli_chart_ensure_sets_symbol_and_timeframe(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        captured = {}

        def fake_ensure_chart(symbol, **kwargs):
            captured["symbol"] = symbol
            captured.update(kwargs)
            return {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "timeframe": kwargs["timeframe"],
                    "title": f"12345678 - Trading.comMarkets-MT5 - [{symbol},{kwargs['timeframe']}]",
                },
            }

        monkeypatch.setattr(chart_module, "ensure_chart", fake_ensure_chart)

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "chart", "ensure", "USDJPY", "--timeframe", "M15"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["symbol"] == "USDJPY"
        assert captured["symbol"] == "USDJPY"
        assert captured["timeframe"] == "M15"

    def test_cli_chart_ensure_forwards_chart_id(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        captured = {}

        def fake_ensure_chart(symbol, **kwargs):
            captured.update(kwargs)
            return {
                "ok": True,
                "data": {"symbol": symbol, "timeframe": kwargs["timeframe"], "hwnd": kwargs["chart_id"]},
            }

        monkeypatch.setattr(chart_module, "ensure_chart", fake_ensure_chart)

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "chart", "ensure", "EURUSD", "--timeframe", "M15", "--chart-id", "202"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert captured["chart_id"] == 202
        assert data["data"]["hwnd"] == 202

    def test_cli_chart_ensure_timeframe_none(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import chart as chart_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)

        captured = {}

        def fake_ensure_chart(symbol, **kwargs):
            captured["symbol"] = symbol
            captured.update(kwargs)
            return {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "timeframe": None,
                    "title": f"12345678 - Trading.comMarkets-MT5 - [{symbol},H1]",
                },
            }

        monkeypatch.setattr(chart_module, "ensure_chart", fake_ensure_chart)

        result = CliRunner().invoke(
            mt5_cli.main,
            ["--json", "chart", "ensure", "USDJPY", "--timeframe", "none"],
        )

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["timeframe"] is None
        assert captured["timeframe"] == "none"

    def test_cli_ehukai_fvg_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import ehukai as ehukai_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(
            ehukai_module,
            "fvg",
            lambda symbol, timeframe, **kw: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": "EhukaiFVG",
                    "zones": [{"visual_label": "BULL FVG OPEN 5p"}],
                },
            },
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "ehukai", "fvg", "USDJPY", "M15"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["source"] == "EhukaiFVG"
        assert data["data"]["zones"][0]["visual_label"] == "BULL FVG OPEN 5p"

    def test_cli_ehukai_structure_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import ehukai as ehukai_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(
            ehukai_module,
            "market_structure",
            lambda symbol, timeframe, **kw: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": "EhukaiMarketStructure",
                    "bias": "BULLISH HH/HL",
                    "panel_label": "MS M15: BULLISH HH/HL | H HH 158.000 | L HL 157.000",
                },
            },
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "ehukai", "structure", "USDJPY", "M15"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["source"] == "EhukaiMarketStructure"
        assert data["data"]["bias"] == "BULLISH HH/HL"

    def test_ehukai_liquidity_returns_buy_and_sell_side_pools(self, monkeypatch):
        from metatrader5_cli.mt5.core import ehukai
        from metatrader5_cli.mt5.core import rates as rates_module

        rows = []
        for i in range(40):
            rows.append({
                "time": f"2026-05-05T00:{i:02d}:00+00:00",
                "open": 1.1000,
                "high": 1.1050,
                "low": 1.0950,
                "close": 1.1000,
                "tick_volume": 10,
            })
        rows[12].update({"open": 1.1110, "high": 1.1200, "low": 1.1100, "close": 1.1120})
        rows[18].update({"open": 1.0890, "high": 1.0900, "low": 1.0800, "close": 1.0880})
        rows[24].update({"open": 1.1120, "high": 1.1260, "low": 1.1110, "close": 1.1180})
        rows[30].update({"open": 1.0910, "high": 1.0920, "low": 1.0740, "close": 1.0830})
        rows[-1]["close"] = 1.1000

        monkeypatch.setattr(rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": rows})

        result = ehukai.liquidity("EURUSD", "M5", bars=40, length=2, max_pools=6)

        assert result["ok"] is True
        data = result["data"]
        assert data["source"] == "EhukaiLiquiditySwings"
        assert data["object_prefix"] == "ELS_"
        assert data["visual_contract"]["indicator"] == "EhukaiLiquiditySwings"
        assert any(pool["side"] == "buy_side" for pool in data["pools"])
        assert any(pool["side"] == "sell_side" for pool in data["pools"])
        assert any(pool["status"] == "swept" for pool in data["pools"])
        swept = next(pool for pool in data["pools"] if pool["status"] == "swept")
        assert isinstance(swept["sweep_age_bars"], int)
        assert swept["sweep_age_bars"] < swept["age_bars"]
        assert swept["sweep_model"] == "wick_reclaim"
        assert swept["zone_width_pips"] > 0
        assert all(pool["visual_label"].startswith(("BSL LIQ", "SSL LIQ")) for pool in data["pools"])

    def test_ehukai_liquidity_close_through_marks_pool_broken_not_swept(self, monkeypatch):
        from metatrader5_cli.mt5.core import ehukai
        from metatrader5_cli.mt5.core import rates as rates_module

        rows = []
        for i in range(32):
            rows.append({
                "time": f"2026-05-05T01:{i:02d}:00+00:00",
                "open": 1.1000,
                "high": 1.1050,
                "low": 1.0950,
                "close": 1.1000,
                "tick_volume": 10,
            })
        rows[12].update({"open": 1.1110, "high": 1.1200, "low": 1.1100, "close": 1.1120})
        rows[24].update({"open": 1.1120, "high": 1.1260, "low": 1.1110, "close": 1.1260})

        monkeypatch.setattr(rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": rows})

        result = ehukai.liquidity("EURUSD", "M5", bars=32, length=2, max_pools=6)

        assert result["ok"] is True
        data = result["data"]
        assert any(pool["status"] == "broken" for pool in data["broken_pools"])
        assert not any(pool["status"] == "swept" and pool["level"] == 1.1200 for pool in data["pools"])

    def test_ehukai_liquidity_min_penetration_does_not_delay_close_through_breaks(self, monkeypatch):
        from metatrader5_cli.mt5.core import ehukai
        from metatrader5_cli.mt5.core import rates as rates_module

        rows = []
        for i in range(36):
            rows.append({
                "time": f"2026-05-05T02:{i:02d}:00+00:00",
                "open": 1.1000,
                "high": 1.1050,
                "low": 1.0950,
                "close": 1.1000,
                "tick_volume": 10,
            })
        rows[12].update({"open": 1.1110, "high": 1.1200, "low": 1.1100, "close": 1.1120})
        rows[20].update({"open": 1.1200, "high": 1.1220, "low": 1.1190, "close": 1.1206})
        rows[24].update({"open": 1.1120, "high": 1.1260, "low": 1.1110, "close": 1.1180})

        monkeypatch.setattr(rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": rows})

        result = ehukai.liquidity(
            "EURUSD",
            "M5",
            bars=36,
            length=2,
            max_pools=6,
            min_pen_atr=0.25,
            pool_half_atr=0.0,
        )

        assert result["ok"] is True
        data = result["data"]
        broken = next(pool for pool in data["broken_pools"] if pool["level"] == 1.1200)
        assert broken["swept_at"] == "2026-05-05T02:20:00+00:00"
        assert not any(pool["status"] == "swept" and pool["level"] == 1.1200 for pool in data["pools"])

    def test_cli_ehukai_liquidity_json(self, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import ehukai as ehukai_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(
            ehukai_module,
            "liquidity",
            lambda symbol, timeframe, **kw: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "source": "EhukaiLiquiditySwings",
                    "pools": [{"visual_label": "BSL LIQ OPEN C2 V100"}],
                },
            },
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "ehukai", "liquidity", "USDJPY", "M5"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["source"] == "EhukaiLiquiditySwings"
        assert data["data"]["pools"][0]["visual_label"] == "BSL LIQ OPEN C2 V100"

    def test_market_search_auto_wraps_bare_pattern(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbols_get.return_value = []
        market.search("EUR")
        mt5m.symbols_get.assert_called_once_with(group="*EUR*")

    def test_market_search_passes_explicit_glob_through(self, mt5m):
        from metatrader5_cli.mt5.core import market
        mt5m.symbols_get.return_value = []
        market.search("EUR*,GBP*")
        mt5m.symbols_get.assert_called_once_with(group="EUR*,GBP*")

    def test_market_sessions_returns_table_for_eurusd(self):
        from metatrader5_cli.mt5.core import market
        result = market.sessions("EURUSD")
        assert result["ok"] is True
        data = result["data"]
        assert set(data.keys()) == {"sydney", "tokyo", "london", "ny"}
        assert "start_utc" in data["london"]
        assert "end_utc" in data["london"]

    def test_market_sessions_unknown_symbol_returns_error(self):
        from metatrader5_cli.mt5.core import market
        result = market.sessions("UNKNOWN123")
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_SYMBOL"
        assert "market session" not in result["error"]["message"]
        assert "market info" in result["error"]["message"]


# ===========================================================================
# Task 8 — Rates (core/rates.py)
# ===========================================================================

class TestRates:
    _BAR = {
        "time": 0, "open": 1.1000, "high": 1.1050,
        "low": 1.0950, "close": 1.1020, "tick_volume": 500,
    }
    _TICK = {
        "time": 0, "bid": 1.1000, "ask": 1.1002,
        "last": 0.0, "volume": 1, "flags": 0,
    }

    def test_rates_fetch_returns_bars_array(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        mt5m.copy_rates_from_pos.return_value = [self._BAR, self._BAR]
        result = rates.fetch("EURUSD", "H1", 2)
        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert "time" in result["data"][0]
        assert "close" in result["data"][0]

    def test_rates_fetch_invalid_timeframe_returns_error(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        result = rates.fetch("EURUSD", "INVALID", 10)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_TIMEFRAME"

    def test_rates_latest_uses_start_pos_1(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        mt5m.copy_rates_from_pos.return_value = [self._BAR]
        rates.latest("EURUSD", "M1")
        args = mt5m.copy_rates_from_pos.call_args[0]
        # positional signature: (symbol, tf, start_pos, count)
        assert args[2] == 1, f"Expected start_pos=1, got {args[2]}"
        assert args[3] == 1, f"Expected count=1, got {args[3]}"

    def test_rates_ticks_lookback_window_24h(self, mt5m):
        from datetime import datetime, timedelta, timezone
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        mt5m.copy_ticks_from.return_value = [self._TICK] * 5
        before = datetime.now(tz=timezone.utc) - timedelta(hours=24, seconds=5)
        rates.ticks("EURUSD", 5)
        after = datetime.now(tz=timezone.utc) - timedelta(hours=24) + timedelta(seconds=5)
        date_from_arg = mt5m.copy_ticks_from.call_args[0][1]
        assert before <= date_from_arg <= after, f"date_from={date_from_arg} not in 24h window"

    def test_rates_ticks_slices_to_bars_count(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        mt5m.copy_ticks_from.return_value = [self._TICK] * 30
        result = rates.ticks("EURUSD", 5)
        assert result["ok"] is True
        assert len(result["data"]) == 5

    def test_rates_iso8601_conversion(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        bar_epoch = dict(self._BAR, time=0)  # POSIX 0 → 1970-01-01T00:00:00+00:00
        mt5m.copy_rates_from_pos.return_value = [bar_epoch]
        result = rates.fetch("EURUSD", "D1", 1)
        assert result["ok"] is True
        assert "1970-01-01" in result["data"][0]["time"]
        assert "+00:00" in result["data"][0]["time"]

    def test_rates_empty_response_returns_error_envelope(self, mt5m):
        from metatrader5_cli.mt5.core import rates
        mt5m.symbol_select.return_value = True
        mt5m.copy_rates_from_pos.return_value = None
        result = rates.fetch("EURUSD", "M5", 10)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_NO_DATA"

    def test_rates_invalid_timeframe_does_not_call_ensure_symbol(self, mt5m):
        """Timeframe validation must happen before symbol_select (P2 fix)."""
        from metatrader5_cli.mt5.core import rates
        rates.fetch("EURUSD", "BOGUS", 10)
        mt5m.symbol_select.assert_not_called()


# ===========================================================================
# Task 8 — Rates CLI smoke tests
# ===========================================================================

class TestRatesCLI:
    _BAR = {
        "time": 0, "open": 1.1000, "high": 1.1050,
        "low": 1.0950, "close": 1.1020, "tick_volume": 500,
    }
    _TICK = {
        "time": 0, "bid": 1.1000, "ask": 1.1002,
        "last": 0.0, "volume": 1, "flags": 0,
    }

    def _runner_and_env(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        return CliRunner(), mt5_cli

    def test_cli_rates_fetch_option_form(self, mt5m, monkeypatch, tmp_path):
        import json
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        mt5m.symbol_select.return_value = True
        mt5m.copy_rates_from_pos.return_value = [self._BAR]
        result = runner.invoke(mt5_cli.main, ["--json", "rates", "fetch", "EURUSD", "H1", "--bars", "1"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) == 1

    def test_cli_rates_ticks_option_form(self, mt5m, monkeypatch, tmp_path):
        import json
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        mt5m.symbol_select.return_value = True
        mt5m.copy_ticks_from.return_value = [self._TICK] * 10
        result = runner.invoke(mt5_cli.main, ["--json", "rates", "ticks", "EURUSD", "--bars", "5"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert len(data["data"]) == 5

    def test_cli_rates_range_from_to_options(self, mt5m, monkeypatch, tmp_path):
        import json
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        mt5m.symbol_select.return_value = True
        mt5m.copy_rates_range.return_value = [self._BAR]
        result = runner.invoke(
            mt5_cli.main,
            ["--json", "rates", "range", "EURUSD", "D1", "--from", "2024-01-01", "--to", "2024-01-02"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_cli_rates_ticks_range_from_to_options(self, mt5m, monkeypatch, tmp_path):
        import json
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        mt5m.symbol_select.return_value = True
        mt5m.copy_ticks_range.return_value = [self._TICK]
        result = runner.invoke(
            mt5_cli.main,
            ["--json", "rates", "ticks-range", "EURUSD", "--from", "2024-01-01", "--to", "2024-01-02"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True


# ===========================================================================
# Task 9 — Indicators (core/indicator.py)
# ===========================================================================

class TestIndicator:
    """
    Tests patch rates_module.fetch so no MT5 connection is required.
    Expected values are precomputed via pandas-ta with the same input data.
    """

    _CLOSES = [1.0, 1.1, 1.2, 1.15, 1.3, 1.25, 1.35, 1.4, 1.45, 1.5]

    @property
    def _bars(self):
        return [
            {
                "time": f"2024-01-{i+1:02d}T00:00:00+00:00",
                "open": c, "high": c + 0.02, "low": c - 0.02,
                "close": c, "tick_volume": 100,
            }
            for i, c in enumerate(self._CLOSES)
        ]

    def _mock_fetch(self, monkeypatch, bars=None):
        from metatrader5_cli.mt5.core import indicator, rates as rates_module
        data = bars if bars is not None else self._bars
        monkeypatch.setattr(rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": data})
        return indicator

    def test_ema_known_input_produces_known_output(self, monkeypatch):
        import pytest
        ind = self._mock_fetch(monkeypatch)
        result = ind.ema("EURUSD", "H1", period=5, bars=10)
        assert result["ok"] is True
        data = result["data"]
        assert data["symbol"] == "EURUSD"
        assert data["timeframe"] == "H1"
        assert len(data["values"]) > 0
        last = data["values"][-1]
        assert "ema" in last, "values rows must use 'ema' key per spec §6.4"
        assert "value" not in last
        assert last["ema"] == pytest.approx(1.3967078189, rel=1e-5)

    def test_atr_known_input_produces_known_output(self, monkeypatch):
        import pytest
        ind = self._mock_fetch(monkeypatch)
        result = ind.atr("EURUSD", "H1", period=5, bars=10)
        assert result["ok"] is True
        assert len(result["data"]["values"]) > 0
        last = result["data"]["values"][-1]["atr"]
        assert last == pytest.approx(0.08626112, rel=1e-4)

    def test_atr_rejects_bars_less_than_period(self, monkeypatch):
        ind = self._mock_fetch(monkeypatch, bars=self._bars[:5])
        result = ind.atr("EURUSD", "H1", period=14, bars=5)
        assert result["ok"] is False
        assert result["error"]["code"] == "INDICATOR_INVALID_INPUT"
        assert "--bars (5) must be >= --period (14)" in result["error"]["message"]

    def test_indicator_propagates_rates_error_envelope(self, monkeypatch):
        from metatrader5_cli.mt5.core import indicator, rates as rates_module
        err = {"ok": False, "error": {"code": "MT5_NO_DATA", "message": "no data", "mt5_retcode": None}}
        monkeypatch.setattr(rates_module, "fetch", lambda *a, **kw: err)
        result = indicator.ema("EURUSD", "H1", period=5)
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_NO_DATA"

    def test_fvg_returns_single_zone_with_nested_boundaries_not_loose_lines(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        ind = self._mock_fetch(monkeypatch, bars=[
            {"time": "2024-01-01T00:00:00+00:00", "open": 0.95, "high": 1.00, "low": 0.90, "close": 0.98, "tick_volume": 100},
            {"time": "2024-01-01T00:15:00+00:00", "open": 1.00, "high": 1.02, "low": 0.95, "close": 1.01, "tick_volume": 100},
            {"time": "2024-01-01T00:30:00+00:00", "open": 1.06, "high": 1.10, "low": 1.05, "close": 1.08, "tick_volume": 100},
            {"time": "2024-01-01T00:45:00+00:00", "open": 1.09, "high": 1.12, "low": 1.08, "close": 1.11, "tick_volume": 100},
            # Forming bar: would fill the gap, but FVG intentionally excludes the last fetched bar.
            {"time": "2024-01-01T01:00:00+00:00", "open": 1.02, "high": 1.04, "low": 0.99, "close": 1.00, "tick_volume": 100},
        ])
        monkeypatch.setattr(ind.bridge, "mt5_call", lambda *a, **kw: MM(point=0.01))

        result = ind.fvg("EURUSD", "M15", bars=5, min_points=1)

        assert result["ok"] is True
        zones = result["data"]["zones"]
        zone = next(z for z in zones if z["lower"] == 1.00 and z["upper"] == 1.05)
        assert zone["type"] == "fvg"
        assert zone["direction"] == "bullish"
        assert zone["lower"] == 1.00
        assert zone["upper"] == 1.05
        assert zone["mid"] == 1.025
        assert zone["size_points"] == 5
        assert zone["size_pips"] == 5
        assert zone["visual_label"] == "BULL FVG OPEN 5p"
        assert zone["visual_contract"] == "EhukaiFVG"
        assert zone["object_prefix"] == "EFVG_"
        assert zone["state"] == "open"
        assert zone["distance_points"] == 6
        assert zone["distance_pips"] == 6
        assert zone["atr_multiple"] is not None
        assert "boundaries" in zone
        assert set(zone["boundaries"]) == {"lower", "upper", "mid"}
        assert zone["render"]["kind"] == "zone"
        assert zone["render"]["label"] == zone["visual_label"]
        assert "lines" not in zone, "FVG boundaries must not be exposed as loose line objects"

    def test_fvg_visual_pips_use_jpy_three_digit_mapping(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        ind = self._mock_fetch(monkeypatch, bars=[
            {"time": "2024-01-01T00:00:00+00:00", "open": 157.760, "high": 157.798, "low": 157.740, "close": 157.790, "tick_volume": 100},
            {"time": "2024-01-01T00:15:00+00:00", "open": 157.800, "high": 157.820, "low": 157.790, "close": 157.810, "tick_volume": 100},
            {"time": "2024-01-01T00:30:00+00:00", "open": 157.840, "high": 157.870, "low": 157.830, "close": 157.860, "tick_volume": 100},
            {"time": "2024-01-01T00:45:00+00:00", "open": 157.860, "high": 157.880, "low": 157.850, "close": 157.870, "tick_volume": 100},
        ])
        monkeypatch.setattr(ind.bridge, "mt5_call", lambda *a, **kw: MM(point=0.001, digits=3))

        result = ind.fvg("USDJPY", "M15", bars=4, min_points=1)

        assert result["ok"] is True
        zone = result["data"]["zones"][0]
        assert zone["size_points"] == 32
        assert zone["size_pips"] == 3.2
        assert zone["visual_label"] == "BULL FVG OPEN 3.2p"

    def test_inferred_digits_ignores_float_repr_artifacts(self):
        from metatrader5_cli.mt5.core import indicator

        rows = [{"open": 0.1 + 0.2, "high": 157.123, "low": 157.100, "close": 157.120}]

        assert indicator._inferred_digits(rows) == 3

    def test_fvg_partial_mitigation_uses_one_zone_state(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        ind = self._mock_fetch(monkeypatch, bars=[
            {"time": "2024-01-01T00:00:00+00:00", "open": 0.95, "high": 1.00, "low": 0.90, "close": 0.98, "tick_volume": 100},
            {"time": "2024-01-01T00:15:00+00:00", "open": 1.00, "high": 1.02, "low": 0.95, "close": 1.01, "tick_volume": 100},
            {"time": "2024-01-01T00:30:00+00:00", "open": 1.06, "high": 1.10, "low": 1.05, "close": 1.08, "tick_volume": 100},
            {"time": "2024-01-01T00:45:00+00:00", "open": 1.09, "high": 1.12, "low": 1.03, "close": 1.10, "tick_volume": 100},
            {"time": "2024-01-01T01:00:00+00:00", "open": 1.11, "high": 1.13, "low": 1.10, "close": 1.12, "tick_volume": 100},
        ])
        monkeypatch.setattr(ind.bridge, "mt5_call", lambda *a, **kw: MM(point=0.01))

        result = ind.fvg("EURUSD", "M15", bars=5, state="partial", mitigation="wick")

        assert result["ok"] is True
        assert len(result["data"]["zones"]) == 1
        zone = result["data"]["zones"][0]
        assert zone["state"] == "partial"
        assert zone["fill_pct"] == 0.4

    def test_fvg_limit_returns_most_recent_zones(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        ind = self._mock_fetch(monkeypatch, bars=[
            {"time": "2024-01-01T00:00:00+00:00", "open": 0.95, "high": 1.00, "low": 0.90, "close": 0.98, "tick_volume": 100},
            {"time": "2024-01-01T00:15:00+00:00", "open": 1.00, "high": 1.02, "low": 0.95, "close": 1.01, "tick_volume": 100},
            {"time": "2024-01-01T00:30:00+00:00", "open": 1.06, "high": 1.10, "low": 1.05, "close": 1.08, "tick_volume": 100},
            {"time": "2024-01-01T00:45:00+00:00", "open": 1.11, "high": 1.14, "low": 1.08, "close": 1.12, "tick_volume": 100},
            {"time": "2024-01-01T01:00:00+00:00", "open": 1.20, "high": 1.24, "low": 1.18, "close": 1.22, "tick_volume": 100},
            {"time": "2024-01-01T01:15:00+00:00", "open": 1.23, "high": 1.25, "low": 1.21, "close": 1.24, "tick_volume": 100},
        ])
        monkeypatch.setattr(ind.bridge, "mt5_call", lambda *a, **kw: MM(point=0.01))

        result = ind.fvg("EURUSD", "M15", bars=6, limit=1)

        assert result["ok"] is True
        assert len(result["data"]["zones"]) == 1
        assert result["data"]["zones"][0]["formed_at"] == "2024-01-01T01:00:00+00:00"

    def test_indicator_list_returns_three_entries(self):
        from metatrader5_cli.mt5.core import indicator
        result = indicator.list_available()
        assert result["ok"] is True
        assert len(result["data"]) == 3
        names = {e["name"] for e in result["data"]}
        assert names == {"ema", "atr", "fvg"}


# ===========================================================================
# Task 10 — Analyze (core/analyze.py)
# ===========================================================================

class TestAnalyze:
    _TF_BULLISH = {
        "timeframe": "H1", "trend": "bullish", "structure": "HH_HL",
        "current_price": 1.25, "support": 1.10, "resistance": 1.50,
        "swing_highs": [{"time": "t1", "price": 1.30}, {"time": "t2", "price": 1.50}],
        "swing_lows": [{"time": "t1", "price": 1.00}, {"time": "t2", "price": 1.10}],
    }
    _TF_BEARISH = {
        "timeframe": "H4", "trend": "bearish", "structure": "LH_LL",
        "current_price": 1.10, "support": 1.00, "resistance": 1.25,
        "swing_highs": [{"time": "t1", "price": 1.50}, {"time": "t2", "price": 1.25}],
        "swing_lows": [{"time": "t1", "price": 1.10}, {"time": "t2", "price": 1.00}],
    }

    @staticmethod
    def _bars(n=20, pivot_high_idx=None, pivot_low_idx=None, close=0.95):
        rows = []
        for i in range(n):
            rows.append({
                "time": f"2024-01-{i + 1:02d}T00:00:00+00:00",
                "open": close,
                "high": 2.0 if i == pivot_high_idx else 1.0,
                "low":  0.5 if i == pivot_low_idx else 0.9,
                "close": close,
                "tick_volume": 100,
            })
        return rows

    @staticmethod
    def _structure_bars(kind="bullish"):
        rows = []
        for i in range(50):
            rows.append({
                "time": f"2024-01-{i + 1:02d}T00:00:00+00:00",
                "open": 1.2,
                "high": 1.4,
                "low": 1.2,
                "close": 1.25,
                "tick_volume": 100,
            })
        if kind == "bullish":
            rows[10]["low"] = 0.90
            rows[18]["high"] = 1.50
            rows[28]["low"] = 1.05
            rows[38]["high"] = 1.70
            rows[-1]["close"] = 1.30
        else:
            rows[10]["low"] = 1.05
            rows[18]["high"] = 1.70
            rows[28]["low"] = 0.90
            rows[38]["high"] = 1.50
            rows[-1]["close"] = 1.00
        return rows

    def test_topdown_classifies_bullish_market_structure_from_hh_hl(self, monkeypatch):
        from metatrader5_cli.mt5.core import analyze
        monkeypatch.setattr(
            analyze.rates_module,
            "fetch",
            lambda *a, **kw: {"ok": True, "data": self._structure_bars("bullish")},
        )

        result = analyze.topdown("EURUSD", ["H1"], bars=50)

        assert result["ok"] is True
        assert result["data"]["timeframes"]["H1"]["trend"] == "bullish"
        assert result["data"]["timeframes"]["H1"]["structure"] == "HH_HL"
        assert set(result["data"]["timeframes"]["H1"]) >= {
            "trend", "structure", "current_price", "support", "resistance", "swing_highs", "swing_lows",
            "bias", "signal_bar", "internal", "trade_read", "structure_engine_version",
        }
        assert result["data"]["timeframes"]["H1"]["structure_engine_version"] == "elite-v1"
        assert result["data"]["bias"] == "bullish"

    def test_ehukai_market_structure_uses_last_closed_bar_for_breaks(self, monkeypatch):
        from metatrader5_cli.mt5.core import ehukai

        rows = self._structure_bars("bullish")
        rows[-2]["close"] = 1.30
        rows[-1]["close"] = 2.00
        monkeypatch.setattr(ehukai.rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": rows})

        result = ehukai.market_structure("EURUSD", "H1", bars=50, pivot_bars=8)

        assert result["ok"] is True
        assert result["data"]["signal_bar"]["index"] == len(rows) - 2
        assert result["data"]["signal_bar"]["close"] == 1.30
        assert result["data"]["last_event"] is None
        assert result["data"]["bias"] == "BULLISH HH/HL"

    def test_ehukai_internal_structure_uses_internal_pivots_for_ibos(self, monkeypatch):
        from metatrader5_cli.mt5.core import ehukai

        rows = []
        for i in range(70):
            rows.append({
                "time": f"2024-02-{i + 1:02d}T00:00:00+00:00",
                "open": 1.10,
                "high": 1.12,
                "low": 1.09,
                "close": 1.10,
                "tick_volume": 100,
            })
        for idx, price in [(44, 0.90), (52, 1.00), (60, 1.08)]:
            rows[idx]["low"] = price
        for idx, price in [(48, 1.14), (56, 1.20)]:
            rows[idx]["high"] = price
        rows[-2]["close"] = 1.23
        rows[-1]["close"] = 1.11
        monkeypatch.setattr(ehukai.rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": rows})

        result = ehukai.market_structure("EURUSD", "M15", bars=70, pivot_bars=8)

        assert result["ok"] is True
        internal = result["data"]["internal"]
        assert internal["pivot_bars"] == 3
        assert internal["stage"] == "iBOS"
        assert internal["last_event"]["type"] == "iBOS"
        assert internal["direction"] == "bullish"
        assert internal["strong_side"] == "low"
        assert internal["strong_level"]["index"] == 60
        assert internal["weak_side"] == "high"
        assert internal["weak_level"]["index"] == 56

    def test_topdown_confluence_score_unanimous(self, monkeypatch):
        import pytest
        from metatrader5_cli.mt5.core import analyze
        monkeypatch.setattr(analyze, "_classify_tf", lambda s, tf, bars: dict(self._TF_BULLISH, timeframe=tf))
        result = analyze.topdown("EURUSD", ["H1", "H4"])
        assert result["ok"] is True
        assert result["data"]["confluence_score"] == pytest.approx(1.0)
        assert result["data"]["bias"] == "bullish"

    def test_topdown_confluence_score_mixed(self, monkeypatch):
        import pytest
        from metatrader5_cli.mt5.core import analyze
        tf_map = {"H1": self._TF_BULLISH, "H4": self._TF_BULLISH, "D1": self._TF_BEARISH}
        monkeypatch.setattr(
            analyze, "_classify_tf",
            lambda s, tf, bars: dict(tf_map.get(tf, self._TF_BULLISH), timeframe=tf),
        )
        result = analyze.topdown("EURUSD", ["H1", "H4", "D1"])
        assert result["ok"] is True
        assert result["data"]["bias"] == "bullish"
        assert result["data"]["confluence_score"] == pytest.approx(2 / 3)

    def test_structure_detects_swing_high_with_n_5(self, monkeypatch):
        from metatrader5_cli.mt5.core import analyze
        bars = self._bars(n=20, pivot_high_idx=10, pivot_low_idx=5)
        monkeypatch.setattr(analyze.rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": bars})
        result = analyze.structure("EURUSD", "H1", bars=20, pivot_n=5)
        assert result["ok"] is True
        assert any(abs(sh["price"] - 2.0) < 1e-9 for sh in result["data"]["swing_highs"])
        assert result["data"]["visual_contract"]["indicator"] == "EhukaiMarketStructure"
        assert all("visual_label" in p for p in result["data"]["swing_points"])

    def test_structure_support_resistance_relative_to_current_price(self, monkeypatch):
        from metatrader5_cli.mt5.core import analyze
        bars = self._bars(n=20, pivot_high_idx=10, pivot_low_idx=5, close=0.95)
        monkeypatch.setattr(analyze.rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": bars})
        result = analyze.structure("EURUSD", "H1", bars=20, pivot_n=5)
        data = result["data"]
        assert data["support"] < data["current_price"]
        assert data["resistance"] > data["current_price"]

    def test_structure_pivot_n_param_overrides_default(self, monkeypatch):
        from metatrader5_cli.mt5.core import analyze
        # Bar at index 3 has high=2.0; pivot_n=1 → range(1,19) → detected;
        # pivot_n=5 → range(5,15) → index 3 not in range → not detected.
        bars = self._bars(n=20, pivot_high_idx=3)
        monkeypatch.setattr(analyze.rates_module, "fetch", lambda *a, **kw: {"ok": True, "data": bars})
        result_n1 = analyze.structure("EURUSD", "H1", bars=20, pivot_n=1)
        assert any(abs(sh["price"] - 2.0) < 1e-9 for sh in result_n1["data"]["swing_highs"])
        result_n5 = analyze.structure("EURUSD", "H1", bars=20, pivot_n=5)
        assert not any(abs(sh["price"] - 2.0) < 1e-9 for sh in result_n5["data"]["swing_highs"])

    def test_bias_uses_default_timeframes_d1_h4_h1(self, monkeypatch):
        from metatrader5_cli.mt5.core import analyze
        captured = {}

        def mock_topdown(symbol, timeframes, bars=200):
            captured["timeframes"] = list(timeframes)
            return {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "generated_at": "2024-01-01T00:00:00+00:00",
                    "bias": "bullish",
                    "confluence_score": 1.0,
                    "timeframes": {},
                    "notes": ["D1: bullish structure (HH_HL); support=1.1, resistance=1.5"],
                },
            }

        monkeypatch.setattr(analyze, "topdown", mock_topdown)
        result = analyze.bias("EURUSD")
        assert captured["timeframes"] == ["D1", "H4", "H1"]
        assert isinstance(result["data"]["reasoning"], str), "reasoning must be a str per spec §6.5"

    def test_sniper_poc_returns_quote_aware_buy_limit_candidate(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(
            analyze.market,
            "info",
            lambda symbol: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "bid": 157.830,
                    "ask": 157.840,
                    "spread": 10,
                    "digits": 3,
                    "point": 0.001,
                    "pip_size": 0.01,
                },
            },
        )
        monkeypatch.setattr(
            analyze.market,
            "tick",
            lambda symbol: {"ok": True, "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840}},
        )
        monkeypatch.setattr(
            analyze.market,
            "depth",
            lambda symbol, levels=5: {
                "ok": False,
                "error": {"code": "MT5_MARKET_BOOK_SUBSCRIBE_FAILED", "message": "no book", "mt5_retcode": 1},
            },
        )

        def mock_structure(symbol, timeframe, bars=300, pivot_bars=4, max_swings=10):
            return {
                "ok": True,
                "data": {
                    "timeframe": timeframe,
                    "bias": "BULLISH HH/HL",
                    "support": 157.760,
                    "resistance": 157.900,
                },
            }

        def mock_fvg(symbol, timeframe, bars=100, min_gap_pips=1.0, max_zones=4, max_distance_pips=120.0):
            zone = {
                "direction": "bullish",
                "lower": 157.790,
                "upper": 157.810,
                "mid": 157.800,
                "state": "open",
                "age_bars": 2,
                "visual_label": "BULL FVG OPEN 2.0p",
            }
            return {"ok": True, "data": {"timeframe": timeframe, "zones": [zone] if timeframe in {"M1", "M5"} else []}}

        def mock_liquidity(symbol, timeframe, bars=300, length=14, area="wick", filter_by="count", filter_value=0.0, max_pools=10):
            pools = [
                {
                    "side": "sell_side",
                    "status": "swept",
                    "bottom": 157.770,
                    "top": 157.785,
                    "level": 157.770,
                    "sweep_age_bars": 3,
                    "visual_label": "SSL LIQ SWEPT C2 V100",
                },
                {
                    "side": "buy_side",
                    "status": "open",
                    "bottom": 157.890,
                    "top": 157.900,
                    "level": 157.900,
                    "visual_label": "BSL LIQ OPEN C3 V200",
                },
            ]
            return {"ok": True, "data": {"timeframe": timeframe, "pools": pools}}

        monkeypatch.setattr(analyze.ehukai, "market_structure", mock_structure)
        monkeypatch.setattr(analyze.ehukai, "fvg", mock_fvg)
        monkeypatch.setattr(analyze.ehukai, "liquidity", mock_liquidity)

        result = analyze.sniper_poc(
            "USDJPY",
            direction="auto",
            max_spread_points=30,
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "ready"
        assert data["legacy_status"] == "candidate"
        assert data["direction"] == "buy"
        assert data["quality_score"] >= 0.8
        assert data["poi"]["type"] == "fvg"
        assert data["poi"]["caused_structure_break"] is False
        assert data["poi"]["mitigated"] is False
        assert data["liquidity"]["poi_trap_risk"] is False
        assert data["entry"]["model"] == "fvg_limit"
        assert data["entry"]["confirmed"] is True
        assert data["quote"]["buy_limits_trigger_on"] == "ask"
        assert data["setup"]["order_type"] == "buy_limit"
        assert data["setup"]["entry"] == 157.8
        assert data["setup"]["stop_points"] == 50.0
        assert data["setup"]["rr"] >= 1.5
        assert "order dryrun USDJPY buy --order-type limit" in data["setup"]["order_command"]
        assert "order limit USDJPY buy" in data["setup"]["order_command"]

    def test_sniper_poc_blocks_wide_spread_trap(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(
            analyze.market,
            "info",
            lambda symbol: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "bid": 157.830,
                    "ask": 157.914,
                    "spread": 84,
                    "digits": 3,
                    "point": 0.001,
                    "pip_size": 0.01,
                },
            },
        )
        monkeypatch.setattr(
            analyze.market,
            "tick",
            lambda symbol: {"ok": True, "data": {"symbol": symbol, "bid": 157.830, "ask": 157.914}},
        )
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": True, "data": {}})
        monkeypatch.setattr(
            analyze.ehukai,
            "market_structure",
            lambda symbol, timeframe, bars=300, pivot_bars=4, max_swings=10: {
                "ok": True,
                "data": {"timeframe": timeframe, "bias": "BULLISH HH/HL", "support": 157.760, "resistance": 157.900},
            },
        )
        monkeypatch.setattr(
            analyze.ehukai,
            "fvg",
            lambda symbol, timeframe, bars=100, min_gap_pips=1.0, max_zones=4, max_distance_pips=120.0: {
                "ok": True,
                "data": {"timeframe": timeframe, "zones": [{
                    "direction": "bullish",
                    "lower": 157.790,
                    "upper": 157.810,
                    "mid": 157.800,
                    "state": "open",
                    "age_bars": 2,
                }]},
            },
        )
        monkeypatch.setattr(
            analyze.ehukai,
            "liquidity",
            lambda symbol, timeframe, bars=300, length=14, area="wick", filter_by="count", filter_value=0.0, max_pools=10: {
                "ok": True,
                "data": {"timeframe": timeframe, "pools": [
                    {"side": "sell_side", "status": "swept", "bottom": 157.770, "top": 157.785, "level": 157.770, "sweep_age_bars": 3},
                    {"side": "buy_side", "status": "open", "level": 157.900, "visual_label": "BSL LIQ OPEN"},
                ]},
            },
        )

        result = analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            max_spread_points=30,
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "no_trade"
        assert any(g["name"] == "spread" and g["ok"] is False for g in data["gates"])

    def test_sniper_poc_blocks_poi_with_liquidity_behind_zone(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "bias": "BULLISH HH/HL", "support": 157.760, "resistance": 157.900},
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "zones": [{
                "type": "fvg",
                "direction": "bullish",
                "lower": 157.790,
                "upper": 157.810,
                "mid": 157.800,
                "state": "open",
                "age_bars": 2,
            }] if timeframe == "M1" else []},
        })
        monkeypatch.setattr(analyze.ehukai, "liquidity", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "pools": [
                {"side": "sell_side", "status": "open", "level": 157.760, "bottom": 157.755, "top": 157.765},
                {"side": "buy_side", "status": "open", "level": 157.900, "visual_label": "BSL LIQ OPEN"},
            ]},
        })

        result = analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "no_trade"
        assert data["liquidity"]["liquidity_behind_zone"] is True
        assert data["liquidity"]["poi_trap_risk"] is True
        assert any(g["name"] == "liquidity_trap" and g["ok"] is False for g in data["gates"])

    def test_sniper_poc_marks_poi_that_caused_structure_break(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {
                "timeframe": timeframe,
                "bias": "BULLISH BOS",
                "direction": "bullish",
                "stage": "BOS",
                "support": 157.760,
                "resistance": 157.900,
                "last_event": {"type": "BOS", "direction": "bullish", "level": 157.850},
            },
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "zones": [{
                "type": "fvg",
                "direction": "bullish",
                "lower": 157.790,
                "upper": 157.810,
                "mid": 157.800,
                "state": "open",
                "age_bars": 2,
            }] if timeframe == "M1" else []},
        })
        monkeypatch.setattr(analyze.ehukai, "liquidity", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "pools": [
                {"side": "sell_side", "status": "swept", "level": 157.795, "bottom": 157.790, "top": 157.800, "sweep_age_bars": 2},
                {"side": "buy_side", "status": "open", "level": 157.900, "visual_label": "BSL LIQ OPEN"},
            ]},
        })

        result = analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "ready"
        assert data["poi"]["caused_structure_break"] is True
        assert data["poi"]["poi_quality"] == "primary"

    def test_sniper_poc_auto_tie_returns_no_trade(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})

        biases = {"D1": "BULLISH HH/HL", "H4": "BULLISH HH/HL", "M15": "BEARISH LH/LL", "M5": "BEARISH LH/LL", "M1": "BULLISH HH/HL"}
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "bias": biases[timeframe], "support": 157.760, "resistance": 157.900},
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda *a, **kw: {"ok": True, "data": {"zones": []}})
        monkeypatch.setattr(analyze.ehukai, "liquidity", lambda *a, **kw: {"ok": True, "data": {"pools": []}})

        result = analyze.sniper_poc(
            "USDJPY",
            direction="auto",
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        assert result["data"]["status"] == "no_trade"
        assert result["data"]["direction"] is None
        assert result["data"]["bias_counts"]["buy"] == result["data"]["bias_counts"]["sell"]

    def test_sniper_poc_rejects_stale_sweep_and_partial_fvg_by_default(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "bias": "BULLISH HH/HL", "support": 157.760, "resistance": 157.900},
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "zones": [{
                "direction": "bullish",
                "lower": 157.790,
                "upper": 157.810,
                "mid": 157.800,
                "state": "partial",
                "age_bars": 25,
            }]},
        })
        monkeypatch.setattr(analyze.ehukai, "liquidity", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "pools": [
                {"side": "sell_side", "status": "swept", "bottom": 157.770, "top": 157.785, "level": 157.770, "sweep_age_bars": 200},
                {"side": "buy_side", "status": "open", "level": 157.900, "visual_label": "BSL LIQ OPEN"},
            ]},
        })

        result = analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        assert result["data"]["status"] == "no_trade"
        assert any(g["name"] == "m1_fvg_poc" and g["ok"] is False for g in result["data"]["gates"])
        assert any(g["name"] == "liquidity_sweep" and g["ok"] is False for g in result["data"]["gates"])

    def test_sniper_poc_rollover_guard_blocks_fx_candidate(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "bias": "BULLISH HH/HL", "support": 157.760, "resistance": 157.900},
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "zones": [{
                "direction": "bullish",
                "lower": 157.790,
                "upper": 157.810,
                "mid": 157.800,
                "state": "open",
                "age_bars": 2,
            }]},
        })
        monkeypatch.setattr(analyze.ehukai, "liquidity", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "pools": [
                {"side": "sell_side", "status": "swept", "bottom": 157.770, "top": 157.785, "level": 157.770, "sweep_age_bars": 3},
                {"side": "buy_side", "status": "open", "level": 157.900, "visual_label": "BSL LIQ OPEN"},
            ]},
        })

        result = analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            generated_at=datetime(2026, 5, 5, 22, 15, tzinfo=timezone.utc),
        )

        assert result["ok"] is True
        assert result["data"]["status"] == "no_trade"
        assert any(g["name"] == "rollover_window" and g["ok"] is False for g in result["data"]["gates"])

    def test_sniper_poc_uses_fast_liquidity_pivots_on_m1_m5(self, monkeypatch):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze.market, "info", lambda symbol: {
            "ok": True,
            "data": {"symbol": symbol, "bid": 157.830, "ask": 157.840, "digits": 3, "point": 0.001, "pip_size": 0.01},
        })
        monkeypatch.setattr(analyze.market, "tick", lambda symbol: {"ok": True, "data": {"bid": 157.830, "ask": 157.840}})
        monkeypatch.setattr(analyze.market, "depth", lambda symbol, levels=5: {"ok": False, "error": {"code": "NO_BOOK"}})
        monkeypatch.setattr(analyze.ehukai, "market_structure", lambda symbol, timeframe, **kw: {
            "ok": True,
            "data": {"timeframe": timeframe, "bias": "BULLISH HH/HL", "support": 157.760, "resistance": 157.900},
        })
        monkeypatch.setattr(analyze.ehukai, "fvg", lambda *a, **kw: {"ok": True, "data": {"zones": []}})

        lengths = {}

        def mock_liquidity(symbol, timeframe, **kwargs):
            lengths[timeframe] = kwargs["length"]
            return {"ok": True, "data": {"timeframe": timeframe, "pools": []}}

        monkeypatch.setattr(analyze.ehukai, "liquidity", mock_liquidity)

        analyze.sniper_poc(
            "USDJPY",
            direction="buy",
            generated_at=datetime(2026, 5, 5, 20, 0, tzinfo=timezone.utc),
        )

        assert lengths["M1"] == 5
        assert lengths["M5"] == 5
        assert lengths["H4"] == 14
        assert lengths["D1"] == 14
        assert lengths["M15"] == 14

    def test_place_ready_limit_requires_ready_setup_and_places_after_immediate_dryrun(self, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import analyze

        setup_payload = {
            "symbol": "USDJPY",
            "status": "ready",
            "direction": "sell",
            "quote": {"point": 0.001},
            "reason": "ready for dry-run",
            "setup": {
                "order_type": "sell_limit",
                "entry": 156.899,
                "sl": 156.949,
                "tp": 156.676,
            },
        }
        calls = {"sniper": 0, "dryrun": 0, "place": 0}

        def mock_sniper(symbol, **kwargs):
            calls["sniper"] += 1
            return {"ok": True, "data": dict(setup_payload)}

        def mock_dryrun(symbol, side, **kwargs):
            calls["dryrun"] += 1
            assert symbol == "USDJPY"
            assert side == "sell"
            assert kwargs["order_type"] == "limit"
            assert kwargs["price"] == 156.899
            assert kwargs["sl"] == 156.949
            assert kwargs["tp"] == 156.676
            assert kwargs["strategy_id"] == "ehukai-m1-sniper-poc"
            return {"ok": True, "data": {"dry_run": True, "retcode": 0}}

        def mock_place(symbol, side, price, **kwargs):
            calls["place"] += 1
            assert symbol == "USDJPY"
            assert side == "sell"
            assert price == 156.899
            assert kwargs["sl"] == 156.949
            assert kwargs["tp"] == 156.676
            return {"ok": True, "data": {"ticket": 204, "symbol": symbol, "type": side}}

        monkeypatch.setattr(analyze, "sniper_poc", mock_sniper)
        monkeypatch.setattr(analyze.order_module, "dryrun", mock_dryrun)
        monkeypatch.setattr(analyze.order_module, "place_limit", mock_place)

        result = analyze.place_ready_limit(
            "USDJPY",
            direction="auto",
            volume=0.001,
            cfg=cfg,
            is_live_intent=True,
        )

        assert result["ok"] is True
        assert result["data"]["status"] == "placed"
        assert result["data"]["safety"]["account_type_block"] is False
        assert calls == {"sniper": 2, "dryrun": 2, "place": 1}

    def test_place_ready_limit_blocks_when_setup_not_ready(self, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import analyze

        monkeypatch.setattr(analyze, "sniper_poc", lambda symbol, **kwargs: {
            "ok": True,
            "data": {"status": "no_trade", "direction": "buy", "reason": "liquidity trap", "setup": None},
        })
        monkeypatch.setattr(analyze.order_module, "dryrun", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("dryrun should not be called")))
        monkeypatch.setattr(analyze.order_module, "place_limit", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("place should not be called")))

        result = analyze.place_ready_limit(
            "AUDUSD",
            direction="auto",
            volume=0.001,
            cfg=cfg,
            is_live_intent=True,
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "EHUKAI_SETUP_NOT_READY"

    def test_place_ready_limit_blocks_when_entry_drifts_after_dryrun(self, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import analyze

        initial_setup = {
            "status": "ready",
            "direction": "sell",
            "quote": {"point": 0.001},
            "setup": {"entry": 156.899, "sl": 156.949, "tp": 156.676},
        }
        final_setup = {
            "status": "ready",
            "direction": "sell",
            "quote": {"point": 0.001},
            "setup": {"entry": 156.910, "sl": 156.949, "tp": 156.676},
        }
        responses = [initial_setup, final_setup]
        calls = {"dryrun": 0}

        def mock_sniper(symbol, **kwargs):
            return {"ok": True, "data": responses.pop(0)}

        def mock_dryrun(*args, **kwargs):
            calls["dryrun"] += 1
            return {"ok": True, "data": {"dry_run": True}}

        monkeypatch.setattr(analyze, "sniper_poc", mock_sniper)
        monkeypatch.setattr(analyze.order_module, "dryrun", mock_dryrun)
        monkeypatch.setattr(analyze.order_module, "place_limit", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("place should not be called")))

        result = analyze.place_ready_limit(
            "USDJPY",
            direction="auto",
            volume=0.001,
            max_entry_drift_points=5,
            cfg=cfg,
            is_live_intent=True,
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "EHUKAI_SETUP_DRIFTED"
        assert calls["dryrun"] == 1

    def test_place_ready_limit_fails_closed_without_quote_point(self, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import analyze

        initial_setup = {
            "status": "ready",
            "direction": "buy",
            "quote": {"point": 0.001},
            "setup": {"entry": 156.800, "sl": 156.740, "tp": 156.920},
        }
        final_setup = {
            "status": "ready",
            "direction": "buy",
            "quote": {"point": 0.0},
            "setup": {"entry": 156.800, "sl": 156.740, "tp": 156.920},
        }
        responses = [initial_setup, final_setup]

        monkeypatch.setattr(analyze, "sniper_poc", lambda symbol, **kwargs: {"ok": True, "data": responses.pop(0)})
        monkeypatch.setattr(analyze.order_module, "dryrun", lambda *a, **kw: {"ok": True, "data": {"dry_run": True}})
        monkeypatch.setattr(analyze.order_module, "place_limit", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("place should not be called")))

        result = analyze.place_ready_limit(
            "USDJPY",
            direction="auto",
            volume=0.001,
            cfg=cfg,
            is_live_intent=True,
        )

        assert result["ok"] is False
        assert result["error"]["code"] == "EHUKAI_SETUP_INVALID"
        assert "tick size" in result["error"]["message"]


# ===========================================================================
# Task 10 — Analyze CLI smoke tests
# ===========================================================================

class TestAnalyzeCLI:
    _TF_RESULT = {
        "trend": "bullish", "structure": "HH_HL", "current_price": 1.25,
        "support": 1.10, "resistance": 1.50,
        "swing_highs": [{"time": "t1", "price": 1.30}, {"time": "t2", "price": 1.50}],
        "swing_lows": [{"time": "t1", "price": 1.00}, {"time": "t2", "price": 1.10}],
    }

    def _runner_and_env(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import project
        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        return CliRunner(), mt5_cli

    def test_cli_analyze_topdown_repeated_timeframes(self, monkeypatch, tmp_path):
        """--timeframes D1 --timeframes H4 --timeframes H1 (Click-native repeated form)."""
        import json
        from metatrader5_cli.mt5.core import analyze
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            analyze, "_classify_tf",
            lambda s, tf, bars: dict(self._TF_RESULT, timeframe=tf),
        )
        result = runner.invoke(mt5_cli.main, [
            "--json", "analyze", "topdown", "EURUSD",
            "--timeframes", "D1", "--timeframes", "H4", "--timeframes", "H1",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert set(data["data"]["timeframes"].keys()) == {"D1", "H4", "H1"}

    def test_cli_analyze_topdown_comma_separated_timeframes(self, monkeypatch, tmp_path):
        """--timeframes D1,H4,H1 (single-option comma-separated form, matches spec §6.5 notation)."""
        import json
        from metatrader5_cli.mt5.core import analyze
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            analyze, "_classify_tf",
            lambda s, tf, bars: dict(self._TF_RESULT, timeframe=tf),
        )
        result = runner.invoke(mt5_cli.main, [
            "--json", "analyze", "topdown", "EURUSD",
            "--timeframes", "D1,H4,H1",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert set(data["data"]["timeframes"].keys()) == {"D1", "H4", "H1"}

    def test_cli_analyze_topdown_uses_default_timeframes(self, monkeypatch, tmp_path):
        import json
        from metatrader5_cli.mt5.core import analyze
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)
        captured = {}

        def mock_classify(symbol, timeframe, bars):
            captured.setdefault("timeframes", []).append(timeframe)
            return dict(self._TF_RESULT, timeframe=timeframe)

        monkeypatch.setattr(analyze, "_classify_tf", mock_classify)
        result = runner.invoke(mt5_cli.main, [
            "--json", "analyze", "topdown", "EURUSD",
        ])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert captured["timeframes"] == ["D1", "H4", "H1"]

    def test_cli_analyze_sniper_poc_json(self, monkeypatch, tmp_path):
        import json
        from metatrader5_cli.mt5.core import analyze
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)

        monkeypatch.setattr(
            analyze,
            "sniper_poc",
            lambda symbol, **kwargs: {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "status": "ready",
                    "direction": kwargs["direction"],
                    "setup": {"order_type": "buy_limit"},
                },
            },
        )

        result = runner.invoke(mt5_cli.main, [
            "--json", "analyze", "sniper-poc", "USDJPY",
            "--direction", "buy",
            "--max-spread-points", "20",
        ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["status"] == "ready"
        assert data["data"]["direction"] == "buy"

    def test_cli_order_ready_limit_json(self, monkeypatch, tmp_path):
        import json
        from metatrader5_cli.mt5.core import analyze
        runner, mt5_cli = self._runner_and_env(monkeypatch, tmp_path)

        captured = {}

        def mock_place_ready_limit(symbol, **kwargs):
            captured["symbol"] = symbol
            captured["kwargs"] = kwargs
            return {
                "ok": True,
                "data": {
                    "symbol": symbol,
                    "status": "placed",
                    "safety": {"account_type_block": False},
                },
            }

        monkeypatch.setattr(analyze, "place_ready_limit", mock_place_ready_limit)

        result = runner.invoke(mt5_cli.main, [
            "--json", "order", "ready-limit", "USDJPY",
            "--direction", "sell",
            "--volume", "0.001",
            "--strategy-id", "ehukai-m1-sniper-poc",
            "--allow-rollover",
        ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["status"] == "placed"
        assert data["data"]["safety"]["account_type_block"] is False
        assert captured["symbol"] == "USDJPY"
        assert captured["kwargs"]["direction"] == "sell"
        assert captured["kwargs"]["volume"] == 0.001
        assert captured["kwargs"]["avoid_rollover"] is False


# ===========================================================================
# Task 11 — Orders (core/order.py + CLI)
# ===========================================================================

class TestOrder:
    """
    Most tests patch risk_module.check_order to {"ok": True} so they focus
    on order-pipeline logic (filling, magic, retcode mapping) rather than
    re-testing the 11 risk guards.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _setup_market_mocks(mt5m, *, filling_mode: int = 1):
        """Set up MT5 mock attributes needed to reach order_send in place_market."""
        from unittest.mock import MagicMock as MM
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(ask=1.1001, bid=1.0999)
        mt5m.symbol_info.return_value = MM(filling_mode=filling_mode)
        mt5m.order_send.return_value = MM(retcode=10009, order=99001, comment="OK")

    # ------------------------------------------------------------------
    # Test 1 — risk gate short-circuits order_send
    # ------------------------------------------------------------------

    def test_place_market_risk_check_blocks_order_send(self, mt5m, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(ask=1.1001)
        monkeypatch.setattr(
            order_module.risk_module, "check_order",
            lambda *a, **kw: {"ok": False, "error": {"code": "RISK_MAX_LOT_EXCEEDED", "message": "Too big", "mt5_retcode": None}},
        )
        result = order_module.place_market(
            "EURUSD", "buy", volume=100.0, sl=1.09, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        mt5m.order_send.assert_not_called()

    # ------------------------------------------------------------------
    # Test 2 — volume xor risk_pct validation
    # ------------------------------------------------------------------

    def test_place_market_volume_xor_risk_pct_required(self, mt5m, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        # Neither provided
        r1 = order_module.place_market("EURUSD", "buy", sl=1.09, cfg=cfg, is_live_intent=False)
        assert r1["ok"] is False
        assert r1["error"]["code"] == "MT5_INVALID_PARAMS"
        # Both provided
        r2 = order_module.place_market("EURUSD", "buy", volume=0.1, risk_pct=1.0, sl=1.09, cfg=cfg, is_live_intent=False)
        assert r2["ok"] is False
        assert r2["error"]["code"] == "MT5_INVALID_PARAMS"

    # ------------------------------------------------------------------
    # Test 3 — happy path retcode 10009
    # ------------------------------------------------------------------

    def test_place_market_happy_path(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(ask=1.1001, bid=1.0999)
        mt5m.symbol_info.return_value = MM(filling_mode=1)
        mt5m.order_send.return_value = MM(retcode=10009, order=99001, comment="OK", time=1700000000)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        result = order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is True
        assert result["data"]["ticket"] == 99001
        assert result["data"]["symbol"] == "EURUSD"
        assert result["data"]["type"] == "buy"
        assert "price" in result["data"]
        assert "time" in result["data"]

    # ------------------------------------------------------------------
    # Test 4 — auto filling picks FOK when bitmask bit 0 is set
    # ------------------------------------------------------------------

    def test_place_market_filling_auto_picks_FOK_when_bitmask_is_1(self, mt5m, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m, filling_mode=1)  # bit 0 → FOK
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09, filling="auto", cfg=cfg, is_live_intent=False,
        )
        request = mt5m.order_send.call_args[0][0]
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        assert request["type_filling"] == bridge.ORDER_FILLING_FOK

    # ------------------------------------------------------------------
    # Test 5 — retcode 10030 exposes filling_mode bitmask in error
    # ------------------------------------------------------------------

    def test_place_market_returns_filling_mode_bitmask_on_10030(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m, filling_mode=5)
        mt5m.order_send.return_value = MM(retcode=10030, order=0, comment="Invalid fill")
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        result = order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["mt5_retcode"] == 10030
        assert "5" in result["error"]["message"]  # bitmask 5 appears in message

    # ------------------------------------------------------------------
    # Test 6 — strategy_id echoed in envelope
    # ------------------------------------------------------------------

    def test_place_market_strategy_id_echoed_in_envelope(self, mt5m, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        result = order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09,
            strategy_id="scalp_v1", cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is True
        assert result["data"]["strategy_id"] == "scalp_v1"

    def test_place_limit_auto_filling_uses_return_for_pending(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = None
        mt5m.order_send.return_value = MM(retcode=10009, order=99002, comment="OK", time=1700000000)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})

        result = order_module.place_limit(
            "EURUSD", "buy", 1.10, volume=0.1, sl=1.09, tp=1.12,
            filling="auto", cfg=cfg, is_live_intent=False,
        )

        assert result["ok"] is True
        request = mt5m.order_send.call_args[0][0]
        assert request["type_filling"] == bridge.ORDER_FILLING_RETURN

    def test_order_list_pending_filters_symbol_and_maps_fields(self, mt5m, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        cfg = {**cfg, "strategy_ids": {"ehukai-sniper-test": 12345}}
        mt5m.orders_get.return_value = [
            MM(
                ticket=99002, symbol="USDJPY", type=2, state=1, volume_initial=0.001,
                volume_current=0.001, price_open=157.814, price_current=157.887,
                sl=157.760, tp=157.914, time_setup=1777997494, time_expiration=0,
                type_time=0, type_filling=2, magic=12345, comment="ehukai-sniper-test",
            )
        ]

        result = order_module.list_pending("USDJPY", cfg=cfg)

        assert result["ok"] is True
        mt5m.orders_get.assert_called_once_with(symbol="USDJPY")
        row = result["data"][0]
        assert row["type"] == "buy_limit"
        assert row["state"] == "placed"
        assert row["type_filling_name"] == "RETURN"
        assert row["strategy_id"] == "ehukai-sniper-test"
        assert row["is_agent_magic"] is False
        assert row["comment_truncated"] is False

    def test_order_list_marks_agent_magic_and_truncated_comment(self, mt5m, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.orders_get.return_value = [
            MM(
                ticket=99003, symbol="USDJPY", type=3, state=1, volume_initial=0.001,
                volume_current=0.001, price_open=157.785, price_current=157.635,
                sl=157.835, tp=157.700, time_setup=1777997494, time_expiration=0,
                type_time=0, type_filling=2, magic=113054, comment="ehukai-m1-sniper",
            )
        ]

        result = order_module.list_pending("USDJPY", cfg=cfg)

        assert result["ok"] is True
        row = result["data"][0]
        assert row["strategy_id"] is None
        assert row["is_agent_magic"] is True
        assert row["comment_truncated"] is True

    def test_order_list_marks_known_strategy_prefix_comment_as_truncated(self, mt5m, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        cfg = {**cfg, "strategy_ids": {"ehukai-sniper-test": 12345}}
        mt5m.orders_get.return_value = [
            MM(
                ticket=99004, symbol="USDJPY", type=2, state=1, volume_initial=0.001,
                volume_current=0.001, price_open=157.814, price_current=157.887,
                sl=157.760, tp=157.914, time_setup=1777997494, time_expiration=0,
                type_time=0, type_filling=2, magic=12345, comment="ehukai-sniper-te",
            )
        ]

        result = order_module.list_pending("USDJPY", cfg=cfg)

        assert result["ok"] is True
        row = result["data"][0]
        assert row["strategy_id"] == "ehukai-sniper-test"
        assert row["comment_truncated"] is True

    def test_cli_order_list_json(self, mt5m, monkeypatch, tmp_path):
        import json
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import order as order_module, project

        monkeypatch.setattr(project, "CONFIG_PATH", tmp_path / "missing.json")
        for var in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER", "MT5_LIVE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(
            order_module,
            "list_pending",
            lambda symbol=None, **kw: {"ok": True, "data": [{"ticket": 99002, "symbol": symbol}]},
        )

        result = CliRunner().invoke(mt5_cli.main, ["--json", "order", "list", "--symbol", "USDJPY"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"][0]["ticket"] == 99002

    # ------------------------------------------------------------------
    # Test 7 — default magic 88888 when no strategy_id
    # ------------------------------------------------------------------

    def test_place_market_default_magic_88888_when_no_strategy_id(self, mt5m, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09,
            strategy_id=None, cfg=cfg, is_live_intent=False,
        )
        request = mt5m.order_send.call_args[0][0]
        assert request["magic"] == 88888

    # ------------------------------------------------------------------
    # Test 8 — auto-derived magic in [100 000, 180 000) when strategy_id not in cfg
    # ------------------------------------------------------------------

    def test_place_market_auto_derived_magic_in_100k_180k_range(self, mt5m, monkeypatch, cfg):
        import hashlib
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        strategy_id = "unknown_strategy"
        order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09,
            strategy_id=strategy_id, cfg=cfg, is_live_intent=False,
        )
        request = mt5m.order_send.call_args[0][0]
        expected = int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000
        assert request["magic"] == expected
        assert 100000 <= request["magic"] < 180000

    # ------------------------------------------------------------------
    # Test 9 — modify uses SLTP action for position ticket
    # ------------------------------------------------------------------

    def test_modify_uses_SLTP_action_for_position_ticket(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.positions_get.return_value = [MM(symbol="EURUSD", sl=1.09, tp=1.12)]
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = order_module.modify(99001, sl=1.08)
        assert result["ok"] is True
        assert result["data"]["action"] == "SLTP"
        request = mt5m.order_send.call_args[0][0]
        assert request["action"] == bridge.TRADE_ACTION_SLTP

    # ------------------------------------------------------------------
    # Test 10 — modify uses MODIFY action for pending ticket
    # ------------------------------------------------------------------

    def test_modify_uses_MODIFY_action_for_pending_ticket(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.positions_get.return_value = []
        mt5m.orders_get.return_value = [MM(symbol="EURUSD", price_open=1.10, sl=1.09, tp=1.12, type_time=0, time_expiration=0)]
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = order_module.modify(99002, sl=1.08)
        assert result["ok"] is True
        assert result["data"]["action"] == "MODIFY"
        request = mt5m.order_send.call_args[0][0]
        assert request["action"] == bridge.TRADE_ACTION_MODIFY

    # ------------------------------------------------------------------
    # Test 11 — cancel uses REMOVE action
    # ------------------------------------------------------------------

    def test_cancel_uses_REMOVE_action(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.account_info.return_value = MM(trade_mode=0)
        mt5m.orders_get.return_value = [MM(symbol="EURUSD")]
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = order_module.cancel(99003, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["cancelled"] is True
        request = mt5m.order_send.call_args[0][0]
        assert request["action"] == bridge.TRADE_ACTION_REMOVE

    # ------------------------------------------------------------------
    # Test 12 — poll_fill returns filled=True when position appears
    # ------------------------------------------------------------------

    def test_poll_fill_returns_filled_true_when_position_appears(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.positions_get.return_value = [MM(ticket=55555)]
        result = order_module.poll_fill(55555, timeout_ms=5000)
        assert result["ok"] is True
        assert result["data"]["filled"] is True
        assert result["data"]["ticket"] == 55555

    # ------------------------------------------------------------------
    # Test 13 — poll_fill returns filled=False on timeout
    # ------------------------------------------------------------------

    def test_poll_fill_returns_filled_false_on_timeout(self, mt5m, monkeypatch):
        import time
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.positions_get.return_value = []
        mt5m.orders_get.return_value = [MM(ticket=55556)]  # pending still present
        monkeypatch.setattr(time, "sleep", lambda s: None)
        result = order_module.poll_fill(55556, timeout_ms=1)
        assert result["ok"] is True
        assert result["data"]["filled"] is False
        assert result["data"]["ticket"] == 55556

    # ------------------------------------------------------------------
    # Test 14 — dryrun runs risk envelope then calls order_check, not order_send
    # ------------------------------------------------------------------

    def test_dryrun_calls_order_check_not_order_send(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(ask=1.1001, bid=1.0999)
        mt5m.symbol_info.return_value = MM(filling_mode=1)
        mt5m.order_check.return_value = MM(margin=100.0, margin_free=9900.0, margin_level=5000.0, profit=0.0, retcode=0)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        result = order_module.dryrun(
            "EURUSD", "buy", volume=0.1, sl=1.09, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is True
        assert result["data"]["dry_run"] is True
        mt5m.order_send.assert_not_called()
        mt5m.order_check.assert_called_once()
        assert isinstance(mt5m.order_check.call_args.args[0], dict)
        assert mt5m.order_check.call_args.kwargs == {}

    def test_dryrun_limit_calls_order_check_with_pending_request(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.symbol_select.return_value = True
        mt5m.order_check.return_value = MM(
            margin=1.0, margin_free=9999.0, margin_level=5000.0, profit=0.0, retcode=0,
        )
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})

        result = order_module.dryrun(
            "USDJPY",
            "sell",
            order_type="limit",
            price=157.785,
            volume=0.001,
            sl=157.835,
            tp=157.700,
            strategy_id="ehukai-m1-sniper-poc",
            cfg=cfg,
            is_live_intent=False,
        )

        assert result["ok"] is True
        assert result["data"]["order_type"] == "limit"
        assert result["data"]["price"] == 157.785
        mt5m.order_send.assert_not_called()
        request = mt5m.order_check.call_args.args[0]
        assert request["action"] == bridge.TRADE_ACTION_PENDING
        assert request["type"] == bridge.ORDER_TYPE_SELL_LIMIT
        assert request["type_filling"] == bridge.ORDER_FILLING_RETURN
        assert request["price"] == 157.785

    def test_dryrun_rejects_nonzero_order_check_retcode(self, mt5m, monkeypatch, cfg):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(ask=1.1001, bid=1.0999)
        mt5m.symbol_info.return_value = MM(filling_mode=1)
        mt5m.order_check.return_value = MM(retcode=10013, comment="Invalid request")
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        result = order_module.dryrun(
            "EURUSD", "buy", volume=0.1, sl=1.09, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_ORDER_REJECTED"
        assert result["error"]["mt5_retcode"] == 10013
        mt5m.order_send.assert_not_called()

    # ------------------------------------------------------------------
    # Test 15 — strategy_id stored in MT5 comment field (spec §6.7)
    # ------------------------------------------------------------------

    def test_place_market_strategy_id_stored_in_mt5_comment(self, mt5m, monkeypatch, cfg):
        from metatrader5_cli.mt5.core import order as order_module
        self._setup_market_mocks(mt5m)
        monkeypatch.setattr(order_module.risk_module, "check_order", lambda *a, **kw: {"ok": True})
        order_module.place_market(
            "EURUSD", "buy", volume=0.1, sl=1.09,
            strategy_id="gopher-gate", cfg=cfg, is_live_intent=False,
        )
        request = mt5m.order_send.call_args[0][0]
        assert request["comment"] == "gopher-gate"

    # ------------------------------------------------------------------
    # Test 16 — dryrun does not consume a rate-limit slot
    # ------------------------------------------------------------------

    def test_dryrun_does_not_consume_rate_limit_slot(self, mt5m, cfg):
        """A successful dryrun must not reduce real-order capacity (spec §7.3).

        Uses the real risk.check_order (not mocked) so we exercise the
        consume_rate_limit=False path end-to-end.
        """
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import order as order_module
        from metatrader5_cli.mt5.core import risk
        # Wire up all guards so check_order passes without short-circuiting
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001, filling_mode=1)
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, margin_free=8000.0)
        mt5m.positions_get.return_value = []
        mt5m.history_deals_get.return_value = []
        mt5m.order_check.return_value = MM(
            margin=100.0, margin_free=9900.0, margin_level=5000.0, profit=0.0, retcode=0,
        )
        # sl=154.50 → sl_distance = (155.00-154.50)/0.001 = 500 pts ≥ min(50)
        slots_before = len(risk._rate_limiter)
        result = order_module.dryrun(
            "USDJPY", "buy", volume=0.1, sl=154.50, cfg=cfg, is_live_intent=False,
        )
        assert result["ok"] is True
        assert len(risk._rate_limiter) == slots_before, (
            "dryrun must not consume a rate-limit slot"
        )


# ===========================================================================
# Task 12 — Positions (core/position.py + CLI)
# ===========================================================================

class TestPosition:

    @staticmethod
    def _make_pos(**kwargs):
        from unittest.mock import MagicMock as MM
        defaults = dict(
            ticket=10001, symbol="EURUSD", type=0,
            volume=0.1, price_open=1.1000, sl=1.09, tp=1.12,
            profit=5.0, swap=-0.5, magic=88888,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    # ------------------------------------------------------------------
    # Test 1 — list returns all positions when no symbol given
    # ------------------------------------------------------------------

    def test_list_returns_all_positions_when_no_symbol(self, mt5m):
        from metatrader5_cli.mt5.core import position as position_module
        p1 = self._make_pos(ticket=10001, symbol="EURUSD")
        p2 = self._make_pos(ticket=10002, symbol="USDJPY", type=1)
        mt5m.positions_get.return_value = [p1, p2]
        result = position_module.list()
        assert result["ok"] is True
        assert len(result["data"]) == 2
        tickets = {d["ticket"] for d in result["data"]}
        assert tickets == {10001, 10002}
        mt5m.positions_get.assert_called_once_with()

    # ------------------------------------------------------------------
    # Test 2 — list filters by symbol via positions_get(symbol=...)
    # ------------------------------------------------------------------

    def test_list_filters_by_symbol(self, mt5m):
        from metatrader5_cli.mt5.core import position as position_module
        mt5m.positions_get.return_value = [self._make_pos(symbol="EURUSD")]
        result = position_module.list("EURUSD")
        assert result["ok"] is True
        assert len(result["data"]) == 1
        mt5m.positions_get.assert_called_once_with(symbol="EURUSD")

    # ------------------------------------------------------------------
    # Test 3 — close constructs opposite-side DEAL with position=ticket
    # ------------------------------------------------------------------

    def test_close_constructs_opposite_side_deal_request(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        pos = self._make_pos(ticket=10001, type=0)  # BUY position
        mt5m.account_info.return_value = MM(trade_mode=0)
        mt5m.positions_get.return_value = [pos]
        mt5m.symbol_info_tick.return_value = MM(ask=1.1010, bid=1.1005)
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = position_module.close(10001, is_live_intent=False)
        assert result["ok"] is True
        request = mt5m.order_send.call_args[0][0]
        assert request["action"] == bridge.TRADE_ACTION_DEAL
        assert request["type"] == bridge.ORDER_TYPE_SELL  # opposite of BUY
        assert request["position"] == 10001

    # ------------------------------------------------------------------
    # Test 4 — close_all continues on per-ticket failure
    # ------------------------------------------------------------------

    def test_close_all_continues_on_per_ticket_failure(self, mt5m, monkeypatch):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        mt5m.account_info.return_value = MM(trade_mode=0)
        p1 = self._make_pos(ticket=10001)
        p2 = self._make_pos(ticket=10002)
        mt5m.positions_get.return_value = [p1, p2]
        close_results = [
            {"ok": False, "error": {"code": "MT5_ORDER_REJECTED", "message": "rejected", "mt5_retcode": 10006}},
            {"ok": True, "data": {"ticket": 10002, "result": "closed", "profit": 5.0}},
        ]
        call_idx = [0]

        def mock_close(ticket, volume=None, *, is_live_intent):
            r = close_results[call_idx[0]]
            call_idx[0] += 1
            return r

        monkeypatch.setattr(position_module, "close", mock_close)
        result = position_module.close_all(is_live_intent=False)
        assert result["ok"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["result"] == "error"
        assert result["data"][1]["result"] == "closed"

    # ------------------------------------------------------------------
    # Test 5 — breakeven BUY with zero buffer sets SL to open price
    # ------------------------------------------------------------------

    def test_breakeven_buy_with_zero_buffer_sets_sl_to_open_price(self, mt5m):
        import pytest
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        mt5m.account_info.return_value = MM(trade_mode=0)
        pos = self._make_pos(ticket=10001, type=0, price_open=1.1000, tp=1.12)
        mt5m.positions_get.return_value = [pos]
        mt5m.symbol_info.return_value = MM(point=0.00001)
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = position_module.breakeven(10001, buffer_points=0, is_live_intent=False)
        assert result["ok"] is True
        assert result["data"]["sl_set_to"] == pytest.approx(1.1000)
        request = mt5m.order_send.call_args[0][0]
        assert request["sl"] == pytest.approx(1.1000)

    # ------------------------------------------------------------------
    # Test 6 — breakeven BUY with 5-point buffer sets SL above open
    # ------------------------------------------------------------------

    def test_breakeven_buy_with_5_point_buffer_sets_sl_above_open(self, mt5m):
        import pytest
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        mt5m.account_info.return_value = MM(trade_mode=0)
        pos = self._make_pos(ticket=10001, type=0, price_open=1.1000, tp=1.12)
        mt5m.positions_get.return_value = [pos]
        mt5m.symbol_info.return_value = MM(point=0.00001)
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = position_module.breakeven(10001, buffer_points=5, is_live_intent=False)
        assert result["ok"] is True
        expected_sl = 1.1000 + 5 * 0.00001
        assert result["data"]["sl_set_to"] == pytest.approx(expected_sl)

    # ------------------------------------------------------------------
    # Test 7 — breakeven SELL with 5-point buffer sets SL below open
    # ------------------------------------------------------------------

    def test_breakeven_sell_with_5_point_buffer_sets_sl_below_open(self, mt5m):
        import pytest
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        mt5m.account_info.return_value = MM(trade_mode=0)
        pos = self._make_pos(ticket=10003, type=1, price_open=1.1000, tp=1.09)  # SELL
        mt5m.positions_get.return_value = [pos]
        mt5m.symbol_info.return_value = MM(point=0.00001)
        mt5m.order_send.return_value = MM(retcode=10009, comment="OK")
        result = position_module.breakeven(10003, buffer_points=5, is_live_intent=False)
        assert result["ok"] is True
        expected_sl = 1.1000 - 5 * 0.00001
        assert result["data"]["sl_set_to"] == pytest.approx(expected_sl)

    # ------------------------------------------------------------------
    # Test 8 — close blocked on live account without live intent
    # ------------------------------------------------------------------

    def test_close_blocked_on_live_account_without_live_intent(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.account_info.return_value = MM(trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL)
        result = position_module.close(10001, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        mt5m.order_send.assert_not_called()

    # ------------------------------------------------------------------
    # Test 9 — move_sl blocked on live account without live intent
    # ------------------------------------------------------------------

    def test_move_sl_blocked_on_live_account_without_live_intent(self, mt5m):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.core import position as position_module
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        mt5m.account_info.return_value = MM(trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL)
        result = position_module.move_sl(10001, 1.0900, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"
        mt5m.order_send.assert_not_called()


# ===========================================================================
# Task 13 — History (core/history.py + CLI)
# ===========================================================================

class TestHistory:

    @staticmethod
    def _make_order(**kwargs):
        from unittest.mock import MagicMock as MM
        defaults = dict(
            ticket=20001, symbol="EURUSD", type=0,
            volume_initial=0.1, price_open=1.1000, sl=1.09, tp=1.12,
            time_setup=1700000000, time_done=1700000100,
            state=4, magic=88888,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    @staticmethod
    def _make_deal(**kwargs):
        from unittest.mock import MagicMock as MM
        defaults = dict(
            ticket=30001, order=20001, symbol="EURUSD", type=0,
            volume=0.1, price=1.1000, profit=10.0, commission=-0.5,
            swap=0.0, time=1700000100, magic=88888,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    # ------------------------------------------------------------------
    # Test 1 — orders filters by strategy_id via resolved magic
    # ------------------------------------------------------------------

    def test_orders_filters_by_strategy_id_via_resolved_magic(self, mt5m):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        cfg = {"magic": 88888, "strategy_ids": {"scalper": 88888}}
        o1 = self._make_order(ticket=20001, magic=88888)
        o2 = self._make_order(ticket=20002, magic=99999)
        mt5m.history_orders_get.return_value = [o1, o2]
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.orders(date_from, date_to, strategy_id="scalper", cfg=cfg)
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["ticket"] == 20001
        assert result["data"][0]["strategy_id"] == "scalper"
        # Timestamps must be ISO-8601 UTC strings, not raw integers
        ts = result["data"][0]["time_setup"]
        assert isinstance(ts, str) and ts.endswith("+00:00")

    # ------------------------------------------------------------------
    # Test 2 — deals filters by symbol
    # ------------------------------------------------------------------

    def test_deals_filters_by_symbol(self, mt5m):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        d1 = self._make_deal(ticket=30001, symbol="EURUSD")
        d2 = self._make_deal(ticket=30002, symbol="USDJPY")
        mt5m.history_deals_get.return_value = [d1, d2]
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.deals(date_from, date_to, symbol="EURUSD")
        assert result["ok"] is True
        assert len(result["data"]) == 1
        assert result["data"][0]["symbol"] == "EURUSD"
        # Deal time must be ISO-8601 UTC string, not a raw integer
        ts = result["data"][0]["time"]
        assert isinstance(ts, str) and ts.endswith("+00:00")

    # ------------------------------------------------------------------
    # Test 3 — stats computes win_rate and profit_factor
    # ------------------------------------------------------------------

    def test_stats_computes_win_rate_and_profit_factor(self, mt5m):
        import pytest
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        d1 = self._make_deal(ticket=30001, profit=10.0, time=1)
        d2 = self._make_deal(ticket=30002, profit=5.0, time=2)
        d3 = self._make_deal(ticket=30003, profit=-4.0, time=3)
        mt5m.history_deals_get.return_value = [d1, d2, d3]
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.stats(date_from, date_to)
        assert result["ok"] is True
        data = result["data"]
        assert data["trades"] == 3
        assert data["win_rate"] == pytest.approx(2 / 3)
        assert data["total_profit"] == pytest.approx(11.0)
        assert data["avg_profit"] == pytest.approx(7.5)   # (10+5)/2
        assert data["avg_loss"] == pytest.approx(4.0)
        assert data["profit_factor"] == pytest.approx(15.0 / 4.0)

    # ------------------------------------------------------------------
    # Test 4 — stats max_drawdown on known curve
    # ------------------------------------------------------------------

    def test_stats_max_drawdown_on_known_curve(self, mt5m):
        import pytest
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        # equity curve: +10 → 10, -15 → -5, +8 → 3
        # peak:          10        10       10
        # drawdown:       0        15        7
        # max_drawdown = 15
        d1 = self._make_deal(ticket=30001, profit=10.0, time=1)
        d2 = self._make_deal(ticket=30002, profit=-15.0, time=2)
        d3 = self._make_deal(ticket=30003, profit=8.0, time=3)
        mt5m.history_deals_get.return_value = [d1, d2, d3]
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.stats(date_from, date_to)
        assert result["ok"] is True
        assert result["data"]["max_drawdown"] == pytest.approx(15.0)

    # ------------------------------------------------------------------
    # Test 5 — stats without strategy_id aggregates all deals
    # ------------------------------------------------------------------

    def test_stats_without_strategy_id_aggregates_all(self, mt5m):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        d1 = self._make_deal(ticket=30001, profit=10.0, magic=88888, time=1)
        d2 = self._make_deal(ticket=30002, profit=5.0, magic=99999, time=2)
        mt5m.history_deals_get.return_value = [d1, d2]
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.stats(date_from, date_to)
        assert result["ok"] is True
        assert result["data"]["trades"] == 2
        assert result["data"]["total_profit"] == 15.0

    # ------------------------------------------------------------------
    # Test 6 — stats zero trades returns zeros not NaN
    # ------------------------------------------------------------------

    def test_stats_zero_trades_returns_zeros_not_nan(self, mt5m):
        import math
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        mt5m.history_deals_get.return_value = []
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        result = history_module.stats(date_from, date_to)
        assert result["ok"] is True
        data = result["data"]
        assert data["trades"] == 0
        for key in ("win_rate", "total_profit", "avg_profit", "avg_loss", "profit_factor", "max_drawdown"):
            assert not math.isnan(data[key]), f"{key} should not be NaN"
            assert data[key] == 0.0

    # ------------------------------------------------------------------
    # Test 7 — strategy_id without cfg returns structured error
    # ------------------------------------------------------------------

    def test_strategy_id_without_cfg_returns_error(self, mt5m):
        from datetime import datetime, timezone
        from metatrader5_cli.mt5.core import history as history_module
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        for fn in (history_module.orders, history_module.deals, history_module.stats):
            result = fn(date_from, date_to, strategy_id="scalper")  # cfg omitted (None)
            assert result["ok"] is False, f"{fn.__name__} should fail without cfg"
            assert result["error"]["code"] == "RISK_INVALID_INPUT"
        # MT5 should not have been called — guard fires before any bridge call
        mt5m.history_orders_get.assert_not_called()
        mt5m.history_deals_get.assert_not_called()


# ===========================================================================
# Task 14 — Screenshot (core/screenshot.py + CLI)
# ===========================================================================

class TestChart:
    class _Win:
        def __init__(self, title, hwnd=101):
            self.hwnd = hwnd
            self.title = title

    def _patch_switch_tf_win32(self, monkeypatch, chart_module, titles, sleep_calls):
        title_iter = iter(titles)

        monkeypatch.setattr(chart_module, "find_window", lambda _window: next(title_iter))
        monkeypatch.setattr(chart_module, "_find_period_toolbar", lambda _hwnd: 202)
        monkeypatch.setattr(chart_module, "_click_toolbar_button", lambda _hwnd, _toolbar, _tf: True)
        monkeypatch.setattr(chart_module, "_press_key", lambda _hwnd, _vk: None)
        monkeypatch.setattr(chart_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    def test_switch_tf_retries_until_title_reflects_timeframe(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        sleep_calls = []
        self._patch_switch_tf_win32(
            monkeypatch,
            chart_module,
            [
                self._Win("12345678 - Trading.comMarkets-MT5 - [USDJPY,Monthly]"),
                self._Win("12345678 - Trading.comMarkets-MT5 - [USDJPY,Monthly]"),
                self._Win("12345678 - Trading.comMarkets-MT5 - [USDJPY,Monthly]"),
                self._Win("12345678 - Trading.comMarkets-MT5 - [USDJPY,H1]"),
            ],
            sleep_calls,
        )

        result = chart_module.switch_tf("H1", settle_seconds=0)

        assert result["ok"] is True
        assert result["data"]["timeframe"] == "H1"
        assert result["data"]["title"].endswith("[USDJPY,H1]")
        assert sleep_calls == [0.05, 0.05, 0.05]

    def test_switch_tf_timeframe_verify_failure_keeps_error_shape(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        stale_title = "12345678 - Trading.comMarkets-MT5 - [USDJPY,Monthly]"
        sleep_calls = []
        self._patch_switch_tf_win32(
            monkeypatch,
            chart_module,
            [self._Win(stale_title) for _ in range(11)],
            sleep_calls,
        )

        result = chart_module.switch_tf("H1", settle_seconds=0)

        assert result == {
            "ok": False,
            "error": {
                "code": "CHART_TIMEFRAME_VERIFY_FAILED",
                "message": f"MT5 active child title did not show timeframe H1: {stale_title}. Detected charts: none",
                "mt5_retcode": None,
            },
        }
        assert sleep_calls == [0.05] * 10

    def test_title_has_symbol_tf_does_not_match_m1_inside_m15(self):
        from metatrader5_cli.mt5.core import chart as chart_module

        assert not chart_module.title_has_symbol_tf("[EURUSD,M15]", "EURUSD", "M1")
        assert chart_module.title_has_symbol_tf("[EURUSD,M1]", "EURUSD", "M1")

    def test_activate_chart_uses_mdi_activate_without_child_zorder_calls(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        calls = []

        class FakeWin32Gui:
            @staticmethod
            def EnumChildWindows(parent_hwnd, callback, extra):
                assert parent_hwnd == 10
                callback(55, extra)

            @staticmethod
            def GetClassName(hwnd):
                return "MDIClient" if hwnd == 55 else "AfxFrameOrView140"

            @staticmethod
            def SetForegroundWindow(hwnd):
                calls.append(("SetForegroundWindow", hwnd))

            @staticmethod
            def SendMessage(hwnd, msg, wparam, lparam):
                calls.append(("SendMessage", hwnd, msg, wparam, lparam))
                return 1

            @staticmethod
            def ShowWindow(hwnd, cmd):
                calls.append(("ShowWindow", hwnd, cmd))

            @staticmethod
            def BringWindowToTop(hwnd):
                calls.append(("BringWindowToTop", hwnd))

        monkeypatch.setattr(chart_module, "_win32", lambda: (FakeWin32Gui, None, None))

        result = chart_module.activate_chart(202, parent_hwnd=10, settle_seconds=0)

        assert result is True
        assert ("SendMessage", 55, chart_module.WM_MDIACTIVATE, 202, 0) in calls
        assert ("SetForegroundWindow", 10) in calls
        assert not any(call[0] in {"ShowWindow", "BringWindowToTop"} for call in calls)
        assert ("SetForegroundWindow", 202) not in calls

    def test_ensure_chart_sets_symbol_and_default_m15(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        calls = []
        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: calls.append(("symbol", symbol, kw)) or {
                "ok": True,
                "data": {"symbol": symbol, "title": f"[{symbol},M1]", "hwnd": 101},
            },
        )

        def fake_switch_tf(tf, **kw):
            calls.append(("switch_tf", tf, kw))
            return {"ok": True, "data": {"timeframe": tf, "title": f"[USDJPY,{tf}]"}}

        monkeypatch.setattr(chart_module, "switch_tf", fake_switch_tf)
        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda _window, **_kw: {
                "ok": True,
                "data": {"hwnd": 101, "title": "12345678 - Trading.comMarkets-MT5 - [USDJPY,M15]"},
            },
        )

        result = chart_module.ensure_chart("USDJPY")

        assert result["ok"] is True
        assert result["data"]["symbol"] == "USDJPY"
        assert result["data"]["timeframe"] == "M15"
        assert calls[0][0:2] == ("symbol", "USDJPY")
        assert calls[1][0:2] == ("switch_tf", "M15")

    def test_ensure_chart_timeframe_none_only_sets_symbol(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        switch_calls = []
        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: {
                "ok": True,
                "data": {"symbol": symbol, "title": f"[{symbol},H1]", "hwnd": 101},
            },
        )
        monkeypatch.setattr(chart_module, "switch_tf", lambda tf, **kw: switch_calls.append(tf))
        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda _window, **_kw: {
                "ok": True,
                "data": {"hwnd": 101, "title": "12345678 - Trading.comMarkets-MT5 - [USDJPY,H1]"},
            },
        )

        result = chart_module.ensure_chart("USDJPY", timeframe="none")

        assert result["ok"] is True
        assert result["data"]["symbol"] == "USDJPY"
        assert result["data"]["timeframe"] is None
        assert switch_calls == []

    def test_ensure_chart_does_not_reuse_parent_hwnd_as_child_chart_id(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        switch_kwargs = []
        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: {
                "ok": True,
                "data": {"symbol": symbol, "title": f"[{symbol},M1]", "hwnd": 10, "parent_hwnd": 10},
            },
        )
        monkeypatch.setattr(
            chart_module,
            "switch_tf",
            lambda tf, **kw: switch_kwargs.append(kw) or {
                "ok": True,
                "data": {"timeframe": tf, "title": f"[USDJPY,{tf}]"},
            },
        )
        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda _window, **_kw: {
                "ok": True,
                "data": {"hwnd": 10, "title": "12345678 - Trading.comMarkets-MT5 - [USDJPY,M15]"},
            },
        )

        result = chart_module.ensure_chart("USDJPY")

        assert result["ok"] is True
        assert switch_kwargs[0]["chart_id"] is None

    def test_ensure_chart_rejects_invalid_timeframe_before_gui_calls(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        symbol_calls = []
        monkeypatch.setattr(chart_module, "symbol", lambda symbol, **kw: symbol_calls.append(symbol))

        result = chart_module.ensure_chart("USDJPY", timeframe="M2")

        assert result["ok"] is False
        assert result["error"]["code"] == "CHART_INVALID_TIMEFRAME"
        assert symbol_calls == []

    def test_symbol_activates_existing_child_chart_without_text_input(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        sent_text = []
        activated = []
        match = chart_module.WindowMatch(10, "12345678 - Trading.comMarkets-MT5 - [GBPUSD,M15]")
        children = [
            chart_module.ChartWindow(101, "[GBPUSD,M15]", "GBPUSD", "M15", "AfxFrameOrView140", True),
            chart_module.ChartWindow(202, "[EURUSD,H1]", "EURUSD", "H1", "AfxFrameOrView140", False),
        ]

        monkeypatch.setattr(chart_module, "find_window", lambda _window: match)
        monkeypatch.setattr(chart_module, "enumerate_chart_children", lambda _parent: children)
        monkeypatch.setattr(chart_module, "activate_chart", lambda hwnd, parent_hwnd=None, settle_seconds=0.1: activated.append((hwnd, parent_hwnd)) or True)
        monkeypatch.setattr(chart_module, "_send_text", lambda hwnd, text: sent_text.append((hwnd, text)))
        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda _window, chart_id=None: {
                "ok": True,
                "data": {"hwnd": chart_id, "title": "[EURUSD,H1]", "parent_hwnd": 10},
            },
        )

        result = chart_module.symbol("EURUSD", settle_seconds=0)

        assert result["ok"] is True
        assert result["data"]["hwnd"] == 202
        assert result["data"]["activated_existing"] is True
        assert activated == [(202, 10)]
        assert sent_text == []

    def test_symbol_verify_failure_lists_detected_child_charts(self, monkeypatch):
        from metatrader5_cli.mt5.core import chart as chart_module

        match = chart_module.WindowMatch(10, "12345678 - Trading.comMarkets-MT5 - [GBPUSD,M15]")
        children = [
            chart_module.ChartWindow(101, "[GBPUSD,M15]", "GBPUSD", "M15", "AfxFrameOrView140", True),
        ]

        monkeypatch.setattr(chart_module, "find_window", lambda _window: match)
        monkeypatch.setattr(chart_module, "enumerate_chart_children", lambda _parent: children)
        monkeypatch.setattr(chart_module, "activate_chart", lambda *_args, **_kw: True)
        monkeypatch.setattr(chart_module, "_send_text", lambda _hwnd, _text: None)
        monkeypatch.setattr(
            chart_module,
            "current_title",
            lambda _window, chart_id=None: {
                "ok": True,
                "data": {"hwnd": chart_id, "title": "[GBPUSD,M15]", "parent_hwnd": 10},
            },
        )
        monkeypatch.setattr(
            chart_module,
            "list_charts",
            lambda _window: {
                "ok": True,
                "data": [chart_module._chart_payload(children[0])],
            },
        )

        result = chart_module.symbol("EURUSD", settle_seconds=0)

        assert result["ok"] is False
        assert result["error"]["code"] == "CHART_SYMBOL_VERIFY_FAILED"
        assert "Detected charts: 101:GBPUSD,M15" in result["error"]["message"]


class TestScreenshot:

    @staticmethod
    def _make_mss_mock(monitor_count: int = 2):
        """Return (mock_mss_module, mock_sct, mock_shot) ready for monkeypatching."""
        from unittest.mock import MagicMock
        mock_shot = MagicMock(rgb=b"\x00" * 100, size=(100, 100), width=100, height=100)
        mock_sct = MagicMock()
        mock_sct.monitors = [{"all": True}] + [{"monitor": i} for i in range(monitor_count)]
        mock_sct.grab.return_value = mock_shot
        mock_mss = MagicMock()
        mock_mss.mss.return_value.__enter__.return_value = mock_sct
        return mock_mss, mock_sct, mock_shot

    # ------------------------------------------------------------------
    # Test 1 — take uses cfg monitor when arg is None
    # ------------------------------------------------------------------

    def test_take_uses_cfg_monitor_when_arg_none(self, tmp_path, monkeypatch):
        from metatrader5_cli.mt5.core import screenshot as ss_module
        mock_mss, mock_sct, _ = self._make_mss_mock(monitor_count=2)
        monkeypatch.setattr(ss_module, "mss", mock_mss)

        cfg = {"screenshot_monitor": 2, "screenshot_path": str(tmp_path)}
        result = ss_module.take(
            output_path=str(tmp_path / "s.png"),
            window_substring="",  # skip pygetwindow
            cfg=cfg,
        )
        assert result["ok"] is True
        # cfg["screenshot_monitor"]=2 (positive) → sct.monitors[2] directly
        mock_sct.grab.assert_called_once_with(mock_sct.monitors[2])

    # ------------------------------------------------------------------
    # Test 2 — take arg monitor overrides cfg
    # ------------------------------------------------------------------

    def test_take_arg_monitor_overrides_cfg(self, tmp_path, monkeypatch):
        from metatrader5_cli.mt5.core import screenshot as ss_module
        mock_mss, mock_sct, _ = self._make_mss_mock(monitor_count=2)
        monkeypatch.setattr(ss_module, "mss", mock_mss)

        cfg = {"screenshot_monitor": 0, "screenshot_path": str(tmp_path)}  # cfg says 0
        result = ss_module.take(
            output_path=str(tmp_path / "s.png"),
            window_substring="",
            monitor=2,  # arg says 2 (second physical) → should win over cfg=0
            cfg=cfg,
        )
        assert result["ok"] is True
        # monitor arg=2 (positive) → sct.monitors[2] directly
        mock_sct.grab.assert_called_once_with(mock_sct.monitors[2])

    # ------------------------------------------------------------------
    # Test 3 — explicit output parent directories are created
    # ------------------------------------------------------------------

    def test_take_explicit_output_creates_parent_dir(self, tmp_path, monkeypatch):
        from metatrader5_cli.mt5.core import screenshot as ss_module
        mock_mss, _mock_sct, _ = self._make_mss_mock(monitor_count=2)
        monkeypatch.setattr(ss_module, "mss", mock_mss)

        output_path = tmp_path / "nested" / "dom" / "s.png"
        result = ss_module.take(
            output_path=str(output_path),
            window_substring="",
            monitor=1,
            cfg={},
        )

        assert result["ok"] is True
        assert output_path.parent.exists()

    # ------------------------------------------------------------------
    # Test 4 — take window match failure fails closed
    # ------------------------------------------------------------------

    def test_take_window_match_failure_returns_error(self, tmp_path, monkeypatch):
        import sys
        from metatrader5_cli.mt5.core import screenshot as ss_module
        mock_mss, mock_sct, _ = self._make_mss_mock(monitor_count=2)
        monkeypatch.setattr(ss_module, "mss", mock_mss)

        class MockGw:
            @staticmethod
            def getAllWindows():
                return []

            @staticmethod
            def getWindowsWithTitle(_title):
                return []

        mock_gw = MockGw()
        monkeypatch.setitem(sys.modules, "pygetwindow", mock_gw)

        cfg = {"screenshot_monitor": 0, "screenshot_path": str(tmp_path)}
        result = ss_module.take(
            output_path=str(tmp_path / "s.png"),
            window_substring="MT5",
            cfg=cfg,
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "SCREENSHOT_WINDOW_NOT_FOUND"
        mock_sct.grab.assert_not_called()

    # ------------------------------------------------------------------
    # Test 4 — screenshot_monitor: 2 does not IndexError on a 2-monitor setup
    # ------------------------------------------------------------------

    def test_take_cfg_monitor_2_on_two_monitor_setup_no_indexerror(self, tmp_path, monkeypatch):
        from metatrader5_cli.mt5.core import screenshot as ss_module
        # Only 2 physical monitors → mss.monitors = [all, primary, secondary] (len=3)
        mock_mss, mock_sct, _ = self._make_mss_mock(monitor_count=2)
        monkeypatch.setattr(ss_module, "mss", mock_mss)

        cfg = {"screenshot_monitor": 2, "screenshot_path": str(tmp_path)}
        result = ss_module.take(
            output_path=str(tmp_path / "s.png"),
            window_substring="",
            cfg=cfg,
        )
        assert result["ok"] is True
        # 2 → sct.monitors[2] (second physical); NOT sct.monitors[3] which would IndexError
        mock_sct.grab.assert_called_once_with(mock_sct.monitors[2])

    # ------------------------------------------------------------------
    # Test 5 — annotate writes output file with Pillow
    # ------------------------------------------------------------------

    def test_annotate_writes_output_file_with_pillow_call(self, tmp_path):
        from PIL import Image
        from metatrader5_cli.mt5.core import screenshot as ss_module

        img = Image.new("RGB", (50, 50), color=(0, 0, 0))
        input_path = str(tmp_path / "input.png")
        output_path = str(tmp_path / "output.png")
        img.save(input_path)

        result = ss_module.annotate(input_path, output_path, "LABEL", (5, 5))
        assert result["ok"] is True
        assert result["data"]["path"] == output_path
        assert (tmp_path / "output.png").exists()

    # ------------------------------------------------------------------
    # Test 6 — list filters PNGs and sorts by mtime
    # ------------------------------------------------------------------

    def test_list_filters_pngs_and_sorts_by_mtime(self, tmp_path):
        import os
        from metatrader5_cli.mt5.core import screenshot as ss_module

        f_old = tmp_path / "old.png"
        f_old.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        os.utime(str(f_old), (1000.0, 1000.0))  # old mtime

        f_new = tmp_path / "new.png"
        f_new.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        os.utime(str(f_new), (2000.0, 2000.0))  # newer mtime

        (tmp_path / "other.txt").write_text("ignored")

        result = ss_module.list(directory=str(tmp_path))
        assert result["ok"] is True
        data = result["data"]
        assert len(data) == 2  # only PNGs, not .txt
        assert data[0]["path"].endswith("new.png")   # newest first
        assert data[1]["path"].endswith("old.png")
        assert isinstance(data[0]["timestamp"], str) and data[0]["timestamp"].endswith("+00:00")
        assert "size_kb" in data[0]

    # ------------------------------------------------------------------
    # Test 7 — visual TDA captures six timeframe PNGs for one symbol
    # ------------------------------------------------------------------

    def test_visual_manifest_prefers_unified_tda_overlay(self):
        from metatrader5_cli.mt5.core import tda_manifest

        manifest = tda_manifest.visual_manifest()

        assert manifest["preferred_chart_indicator"] == "EhukaiTDAOverlay"
        assert manifest["object_contract"]["tda_overlay_prefix"] == "ETDA_"
        assert "EhukaiTDAOverlay" in manifest["indicator_assets"]
        assert any("Apply only EhukaiTDAOverlay" in rule for rule in manifest["agent_rules"])

    def test_screenshot_tda_captures_usdjpy_six_timeframes(self, tmp_path, monkeypatch):
        import os
        from PIL import Image
        from metatrader5_cli.mt5.core import chart as chart_module
        from metatrader5_cli.mt5.core import screenshot as ss_module
        from metatrader5_cli.mt5.core import tda_manifest

        timeframes = ["D1", "H4", "H1", "M15", "M5", "M1"]

        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: {"ok": True, "data": {"symbol": symbol, "title": f"[{symbol},D1]"}},
        )
        switch_calls = []

        def fake_switch_tf(tf, **_kw):
            switch_calls.append(tf)
            return {"ok": True, "data": {"timeframe": tf, "title": f"[USDJPY,{tf}]"}}

        monkeypatch.setattr(
            chart_module,
            "switch_tf",
            fake_switch_tf,
        )

        def fake_take(output_path, **_kwargs):
            img = Image.effect_noise((1280, 720), 100).convert("RGB")
            img.save(output_path)
            return {
                "ok": True,
                "data": {
                    "path": output_path,
                    "width": 1280,
                    "height": 720,
                    "timestamp": "2026-04-29T00:00:00+00:00",
                    "window_matched": True,
                },
            }

        monkeypatch.setattr(ss_module, "take", fake_take)
        monkeypatch.setattr(
            tda_manifest,
            "frame_context",
            lambda symbol, timeframe, **kw: {
                "symbol": symbol,
                "timeframe": timeframe,
                "market_structure": {"support": 157.0, "resistance": 158.0, "bias": "BULLISH HH/HL"},
                "fvg": {"zones": []},
            },
        )
        monkeypatch.setattr(
            tda_manifest,
            "visual_manifest",
            lambda: {"version": "test", "legend": [{"label_pattern": "HH|HL"}]},
        )

        result = ss_module.tda(
            "USDJPY",
            timeframes=",".join(timeframes),
            output_dir=str(tmp_path),
            crop="window",
            max_width=1280,
        )

        assert result["ok"] is True
        frames = result["data"]["frames"]
        assert len(frames) == 6
        assert [frame["tf"] for frame in frames] == timeframes
        assert switch_calls == timeframes + ["M15"]
        assert result["data"]["final_timeframe"] == "M15"
        assert result["data"]["visual_manifest"]["version"] == "test"
        assert result["data"]["ehukai_analysis"]["dominant_bias"] == "BULLISH HH/HL"
        assert os.path.exists(result["data"]["manifest_path"])
        for frame in frames:
            assert frame["path"].endswith(".png")
            assert os.path.getsize(frame["path"]) >= 50 * 1024
            assert f"[USDJPY,{frame['tf']}]" in frame["title"]
            assert frame["structured_context"]["market_structure"]["support"] == 157.0

    def test_screenshot_tda_final_timeframe_none_leaves_last_tf(self, tmp_path, monkeypatch):
        from PIL import Image
        from metatrader5_cli.mt5.core import chart as chart_module
        from metatrader5_cli.mt5.core import screenshot as ss_module

        switch_calls = []
        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: {"ok": True, "data": {"symbol": symbol, "title": f"[{symbol},H1]"}},
        )
        monkeypatch.setattr(
            chart_module,
            "switch_tf",
            lambda tf, **kw: switch_calls.append(tf) or {"ok": True, "data": {"timeframe": tf, "title": f"[USDJPY,{tf}]"}},
        )

        def fake_take(output_path, **_kwargs):
            Image.new("RGB", (1280, 720), color=(255, 255, 255)).save(output_path)
            return {
                "ok": True,
                "data": {"path": output_path, "width": 1280, "height": 720, "timestamp": "2026-05-05T00:00:00+00:00"},
            }

        monkeypatch.setattr(ss_module, "take", fake_take)

        result = ss_module.tda(
            "USDJPY",
            timeframes="H1,M5",
            output_dir=str(tmp_path),
            crop="window",
            final_timeframe="none",
        )

        assert result["ok"] is True
        assert switch_calls == ["H1", "M5"]
        assert "final_timeframe" not in result["data"]

    def test_screenshot_tda_final_timeframe_failure_preserves_captures(self, tmp_path, monkeypatch):
        import json
        import os
        from PIL import Image
        from metatrader5_cli.mt5.core import chart as chart_module
        from metatrader5_cli.mt5.core import screenshot as ss_module

        switch_calls = []
        monkeypatch.setattr(
            chart_module,
            "symbol",
            lambda symbol, **kw: {"ok": True, "data": {"symbol": symbol, "title": f"[{symbol},H1]"}},
        )

        def fake_switch_tf(tf, **_kw):
            switch_calls.append(tf)
            if tf == "M15":
                return {
                    "ok": False,
                    "error": {
                        "code": "CHART_TIMEFRAME_VERIFY_FAILED",
                        "message": "title lagged",
                        "mt5_retcode": None,
                    },
                }
            return {"ok": True, "data": {"timeframe": tf, "title": f"[USDJPY,{tf}]"}}

        monkeypatch.setattr(chart_module, "switch_tf", fake_switch_tf)

        def fake_take(output_path, **_kwargs):
            Image.new("RGB", (1280, 720), color=(255, 255, 255)).save(output_path)
            return {
                "ok": True,
                "data": {"path": output_path, "width": 1280, "height": 720, "timestamp": "2026-05-05T00:00:00+00:00"},
            }

        monkeypatch.setattr(ss_module, "take", fake_take)

        result = ss_module.tda(
            "USDJPY",
            timeframes="H1",
            output_dir=str(tmp_path),
            crop="window",
            structured_context=False,
            visual_manifest=False,
        )

        assert result["ok"] is True
        assert switch_calls == ["H1", "M15"]
        assert len(result["data"]["frames"]) == 1
        assert os.path.exists(result["data"]["frames"][0]["path"])
        assert result["data"]["final_timeframe_error"]["code"] == "CHART_TIMEFRAME_VERIFY_FAILED"
        with open(result["data"]["manifest_path"], encoding="utf-8") as fh:
            manifest = json.load(fh)
        assert manifest["final_timeframe_error"]["message"] == "title lagged"

    # ------------------------------------------------------------------
    # Test 8 — GUI Depth of Market window capture uses symbol title by default
    # ------------------------------------------------------------------

    def test_screenshot_dom_captures_symbol_window(self, tmp_path, monkeypatch):
        from PIL import Image
        from metatrader5_cli.mt5.core import chart as chart_module
        from metatrader5_cli.mt5.core import screenshot as ss_module

        captured = {}

        def fake_take(output_path, window_substring, **_kwargs):
            captured["window_substring"] = window_substring
            img = Image.new("RGB", (640, 900), color=(255, 255, 255))
            img.save(output_path)
            return {
                "ok": True,
                "data": {
                    "path": output_path,
                    "width": 640,
                    "height": 900,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "window_matched": True,
                    "window_title": "USDJPY, US Dollar vs Japanese Yen",
                },
            }

        monkeypatch.setattr(ss_module, "take", fake_take)
        monkeypatch.setattr(
            chart_module,
            "open_depth_of_market",
            lambda symbol, **kwargs: {
                "ok": True,
                "data": {"symbol": symbol, "menu": "Charts > Depth Of Market"},
            },
        )
        monkeypatch.setattr(
            chart_module,
            "close_depth_of_market",
            lambda symbol, **kwargs: {
                "ok": True,
                "data": {"symbol": symbol, "closed": 1},
            },
        )

        result = ss_module.dom("USDJPY", output_dir=str(tmp_path), max_width=1280, close_panel=True)

        assert result["ok"] is True
        assert captured["window_substring"] == "MT5"
        assert result["data"]["symbol"] == "USDJPY"
        assert result["data"]["source"] == "gui_depth_of_market_window"
        assert result["data"]["panel_opened"] is True
        assert result["data"]["panel_closed"] is True
        assert result["data"]["path"].endswith(".png")

    def test_screenshot_dom_closes_panel_by_default(self, tmp_path, monkeypatch):
        from PIL import Image
        from metatrader5_cli.mt5.core import chart as chart_module
        from metatrader5_cli.mt5.core import screenshot as ss_module

        closed = {"called": False}

        def fake_take(output_path, **_kwargs):
            img = Image.new("RGB", (640, 900), color=(255, 255, 255))
            img.save(output_path)
            return {
                "ok": True,
                "data": {
                    "path": output_path,
                    "width": 640,
                    "height": 900,
                    "timestamp": "2026-05-05T00:00:00+00:00",
                    "window_matched": True,
                    "window_title": "USDJPY, US Dollar vs Japanese Yen",
                },
            }

        monkeypatch.setattr(ss_module, "take", fake_take)
        monkeypatch.setattr(
            chart_module,
            "open_depth_of_market",
            lambda symbol, **kwargs: {"ok": True, "data": {"symbol": symbol}},
        )
        monkeypatch.setattr(
            chart_module,
            "close_depth_of_market",
            lambda symbol, **kwargs: closed.update(called=True) or {
                "ok": True,
                "data": {"symbol": symbol, "closed": 1},
            },
        )

        result = ss_module.dom("USDJPY", output_dir=str(tmp_path), max_width=1280)

        assert result["ok"] is True
        assert closed["called"] is True
        assert result["data"]["panel_closed"] is True

    def test_depth_of_market_child_title_does_not_match_chart_title(self):
        from metatrader5_cli.mt5.core import chart as chart_module

        assert chart_module.is_depth_of_market_child_title(
            "USDJPY, US Dollar vs Japanese Yen", "USDJPY"
        )
        assert not chart_module.is_depth_of_market_child_title("USDJPY,M15", "USDJPY")
        assert not chart_module.is_depth_of_market_child_title("[USDJPY,M15]", "USDJPY")


# ===========================================================================
# Task 15 — Kill-Switch + REPL
# ===========================================================================

class TestKillSwitch:
    """Tests for the kill-switch CLI command and cancel_all_pending core function."""

    # ------------------------------------------------------------------
    # Test 1 — kill-switch requires confirmation unless --yes
    # ------------------------------------------------------------------

    def test_kill_switch_requires_confirmation_unless_yes(self, mt5m):
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["kill-switch"], input="n\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output
        mt5m.orders_get.assert_not_called()
        mt5m.positions_get.assert_not_called()

    # ------------------------------------------------------------------
    # Test 2 — kill-switch continues on per-ticket failure
    # ------------------------------------------------------------------

    def test_kill_switch_continues_on_per_ticket_failure(self, mt5m, monkeypatch):
        from unittest.mock import MagicMock as MM
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import position as pos_mod, order as ord_mod

        mt5m.initialize.return_value = True

        # close_all: ticket 1 closes ok, ticket 2 errors
        monkeypatch.setattr(pos_mod, "close_all", lambda symbol=None, *, is_live_intent: {
            "ok": True,
            "data": [
                {"ticket": 1001, "result": "closed", "profit": 5.0},
                {"ticket": 1002, "result": "error", "error": {"code": "MT5_ORDER_REJECTED", "message": "rejected", "mt5_retcode": 10006}},
            ],
        })
        monkeypatch.setattr(ord_mod, "cancel_all_pending", lambda symbol=None, *, is_live_intent: {
            "ok": True, "data": [],
        })

        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["--json", "kill-switch", "--yes"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        # Both tickets present in output
        tickets = {e["ticket"] for e in data["data"]}
        assert 1001 in tickets
        assert 1002 in tickets
        # First succeeded, second didn't
        by_ticket = {e["ticket"]: e for e in data["data"]}
        assert by_ticket[1001]["ok"] is True
        assert by_ticket[1002]["ok"] is False

    # ------------------------------------------------------------------
    # Test 3 — kill-switch returns combined position + order results
    # ------------------------------------------------------------------

    def test_kill_switch_returns_combined_results(self, mt5m, monkeypatch):
        from click.testing import CliRunner
        from metatrader5_cli.mt5 import mt5_cli
        from metatrader5_cli.mt5.core import position as pos_mod, order as ord_mod

        mt5m.initialize.return_value = True

        monkeypatch.setattr(pos_mod, "close_all", lambda symbol=None, *, is_live_intent: {
            "ok": True,
            "data": [{"ticket": 2001, "result": "closed", "profit": 3.0}],
        })
        monkeypatch.setattr(ord_mod, "cancel_all_pending", lambda symbol=None, *, is_live_intent: {
            "ok": True,
            "data": [{"ticket": 3001, "result": "canceled"}],
        })

        runner = CliRunner()
        result = runner.invoke(mt5_cli.main, ["--json", "kill-switch", "--yes"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["ok"] is True
        tickets = {e["ticket"] for e in data["data"]}
        # Both position and order tickets appear
        assert 2001 in tickets
        assert 3001 in tickets


class TestRepl:
    """Tests for ReplSkin banner and last-symbol tracking."""

    # ------------------------------------------------------------------
    # Test 4 — REPL banner shows server and balance
    # ------------------------------------------------------------------

    def test_repl_banner_shows_server_and_balance(self, mt5m, monkeypatch):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils.repl_skin import ReplSkin

        mt5m.account_info.return_value = MM(
            balance=10119.50, currency="USD", server="Trading.com-Demo",
            equity=10119.50, margin_free=8000.0, trade_mode=0,
        )

        monkeypatch.setattr("metatrader5_cli.mt5.utils.repl_skin.PromptSession",
                            MM(return_value=MM()))

        skin = ReplSkin({"server": "Trading.com-Demo", "magic": 88888})
        banner = skin._banner()
        assert "Trading.com-Demo" in banner
        assert "10,119.50" in banner
        assert "USD" in banner

    # ------------------------------------------------------------------
    # Test 5 — REPL remembers last symbol in prompt
    # ------------------------------------------------------------------

    def test_repl_remembers_last_symbol_in_prompt(self, monkeypatch):
        import click as _click
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils.repl_skin import ReplSkin

        mock_session = MM()
        mock_session.prompt.side_effect = ["market tick EURUSD", EOFError()]
        monkeypatch.setattr("metatrader5_cli.mt5.utils.repl_skin.PromptSession",
                            MM(return_value=mock_session))

        skin = ReplSkin({"server": "Demo", "magic": 88888})
        # Stub banner and dispatch to avoid side effects
        monkeypatch.setattr(skin, "_banner", lambda: "MT5 CLI v0.1")
        monkeypatch.setattr(skin, "_dispatch", lambda args, cli: None)
        monkeypatch.setattr(_click, "echo", lambda msg, **kw: None)

        skin.run()

        assert skin.last_symbol == "EURUSD"
        assert skin._prompt_text() == "mt5 (EURUSD)> "

    # ------------------------------------------------------------------
    # Test 6 — REPL reconnects once on ConnectionError then succeeds
    # ------------------------------------------------------------------

    def test_repl_reconnects_on_connection_error(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils.repl_skin import ReplSkin
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        import metatrader5_cli.mt5.mt5_cli as mt5_cli_mod

        monkeypatch.setattr("metatrader5_cli.mt5.utils.repl_skin.PromptSession",
                            MM(return_value=MM()))

        skin = ReplSkin({"server": "Demo"})

        call_count = 0

        def mock_main(args, standalone_mode=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("MT5 disconnected")

        mock_main_obj = MM()
        mock_main_obj.main = mock_main
        monkeypatch.setattr(mt5_cli_mod, "main", mock_main_obj)
        monkeypatch.setattr(bridge, "reconnect_once", lambda cfg: True)

        error_messages = []
        monkeypatch.setattr("click.secho", lambda msg, **kw: error_messages.append(msg))

        skin._dispatch(["market", "tick", "EURUSD"], mt5_cli_mod)

        assert call_count == 2  # first raised ConnectionError, second succeeded
        assert not any("MT5_CONNECTION_ERROR" in m for m in error_messages)

    # ------------------------------------------------------------------
    # Test 7 — REPL surfaces error when reconnect fails (double-disconnect)
    # ------------------------------------------------------------------

    def test_repl_surfaces_error_when_reconnect_fails(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils.repl_skin import ReplSkin
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        import metatrader5_cli.mt5.mt5_cli as mt5_cli_mod

        monkeypatch.setattr("metatrader5_cli.mt5.utils.repl_skin.PromptSession",
                            MM(return_value=MM()))

        skin = ReplSkin({"server": "Demo"})

        def mock_main_raise(args, standalone_mode=True):
            raise ConnectionError("MT5 disconnected")

        mock_main_obj = MM()
        mock_main_obj.main = mock_main_raise
        monkeypatch.setattr(mt5_cli_mod, "main", mock_main_obj)
        monkeypatch.setattr(bridge, "reconnect_once", lambda cfg: False)

        error_messages = []
        monkeypatch.setattr("click.secho", lambda msg, **kw: error_messages.append(msg))

        skin._dispatch(["market", "tick", "EURUSD"], mt5_cli_mod)

        assert any("MT5_CONNECTION_ERROR" in m for m in error_messages)

    # ------------------------------------------------------------------
    # Test 8 — REPL reconnects once on SystemExit(2) (CLI connection path)
    # ------------------------------------------------------------------

    def test_repl_reconnects_on_systemexit_2(self, monkeypatch):
        from unittest.mock import MagicMock as MM
        from metatrader5_cli.mt5.utils.repl_skin import ReplSkin
        from metatrader5_cli.mt5.utils import mt5_backend as bridge
        import metatrader5_cli.mt5.mt5_cli as mt5_cli_mod

        monkeypatch.setattr("metatrader5_cli.mt5.utils.repl_skin.PromptSession",
                            MM(return_value=MM()))

        skin = ReplSkin({"server": "Demo"})

        call_count = 0

        def mock_main(args, standalone_mode=True):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SystemExit(2)

        mock_main_obj = MM()
        mock_main_obj.main = mock_main
        monkeypatch.setattr(mt5_cli_mod, "main", mock_main_obj)
        monkeypatch.setattr(bridge, "reconnect_once", lambda cfg: True)

        error_messages = []
        monkeypatch.setattr("click.secho", lambda msg, **kw: error_messages.append(msg))

        skin._dispatch(["market", "tick", "EURUSD"], mt5_cli_mod)

        assert call_count == 2  # first raised SystemExit(2), second succeeded
        assert not any("MT5_CONNECTION_ERROR" in m for m in error_messages)


# ===========================================================================
# Task 16 — documentation integrity tests
# ===========================================================================

class TestDocs:
    """Smoke-tests that verify doc files exist and contain required content."""

    # ------------------------------------------------------------------
    # Test 1 — SKILL.md documents Step 0 market search
    # ------------------------------------------------------------------

    def test_skill_md_documents_step_0_market_search(self):
        from pathlib import Path
        skill_md = (
            Path(__file__).parent.parent / "skills" / "SKILL.md"
        )
        assert skill_md.exists(), f"SKILL.md not found at {skill_md}"
        content = skill_md.read_text(encoding="utf-8")
        assert "market search" in content, (
            "SKILL.md must document 'market search' as Step 0"
        )

    # ------------------------------------------------------------------
    # Test 2 — test_e2e.py module skips without MT5_DEMO_INTEGRATION
    # ------------------------------------------------------------------

    def test_e2e_module_skips_without_env_var(self, monkeypatch):
        import importlib
        import sys

        # Ensure the env var is absent
        monkeypatch.delenv("MT5_DEMO_INTEGRATION", raising=False)

        # Remove any cached import so the module-level skip guard re-runs
        monkeypatch.delitem(sys.modules, "metatrader5_cli.mt5.tests.test_e2e", raising=False)

        with pytest.raises(pytest.skip.Exception):
            importlib.import_module("metatrader5_cli.mt5.tests.test_e2e")
