"""
Unit tests for the MT5 CLI core and bridge layers.
All tests use the MagicMock MetaTrader5 stub installed by conftest.py.
No real MT5 terminal is required.
"""
import threading
from unittest.mock import MagicMock

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

    def test_load_live_env_does_not_set_cfg_live(self, tmp_path, monkeypatch):
        """MT5_LIVE must NOT affect cfg["live"]; gate 3 checks it directly
        in _compose_live_intent so gates 1 and 3 stay independent (spec §7.1)."""
        from cli_anything.mt5.core import project
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


# ===========================================================================
# Task 4 — Risk (core/risk.py)
# ===========================================================================

class TestRisk:
    # --- resolve_magic ---
    def test_resolve_magic_uses_config_map(self, cfg):
        from cli_anything.mt5.core import risk
        cfg["strategy_ids"] = {"gopher-gate": 12001}
        assert risk.resolve_magic("gopher-gate", cfg) == 12001

    def test_resolve_magic_auto_derives_in_range_100k_180k(self, cfg):
        from cli_anything.mt5.core import risk
        magic = risk.resolve_magic("my-strategy", cfg)
        assert 100000 <= magic < 180000

    def test_resolve_magic_deterministic(self, cfg):
        from cli_anything.mt5.core import risk
        assert risk.resolve_magic("my-strategy", cfg) == risk.resolve_magic("my-strategy", cfg)

    def test_resolve_magic_default_when_no_id(self, cfg):
        from cli_anything.mt5.core import risk
        assert risk.resolve_magic(None, cfg) == 88888

    def test_resolve_magic_rejects_configured_magic_out_of_range(self, cfg):
        from cli_anything.mt5.core import risk
        cfg["strategy_ids"] = {"bad-strat": 150000}  # collides with auto-derived range
        with pytest.raises(ValueError, match="must be < 100000"):
            risk.resolve_magic("bad-strat", cfg)

    # --- compute_volume_from_risk_pct ---
    def test_compute_volume_from_risk_pct_basic(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
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
        from cli_anything.mt5.core import risk
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
        from cli_anything.mt5.core import risk
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
            trade_mode=0, equity=10000.0, free_margin=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []

    def test_check_order_happy_path_passes(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result == {"ok": True}

    def test_check_order_rejects_strategy_id_too_long(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        long_id = "x" * 32
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, long_id, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_STRATEGY_ID_TOO_LONG"

    def test_check_order_rejects_live_gate(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(
            trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL,
            equity=10000.0, free_margin=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_LIVE_GATE_BLOCKED"

    def test_check_order_live_intent_true_passes_gate(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        # When is_live_intent=True, live gate should NOT fire even on real account
        mt5m.account_info.return_value = MagicMock(
            trade_mode=bridge.ACCOUNT_TRADE_MODE_REAL,
            equity=10000.0, free_margin=8000.0,
        )
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MagicMock(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MagicMock(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=True)
        assert result == {"ok": True}

    def test_check_order_rejects_symbol_not_allowed(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["symbol_allowlist"] = ["EURUSD"]
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_SYMBOL_NOT_ALLOWED"

    def test_check_order_rejects_max_lot_exceeded(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 2.0, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"

    def test_check_order_rejects_no_stop_loss(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        result = risk.check_order("USDJPY", "buy", 0.10, None, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_rejects_sl_too_close(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        # entry=155.00, sl=154.99 → distance = abs(155.00-154.99)/0.001 = 10 points < 50
        result = risk.check_order("USDJPY", "buy", 0.10, 154.99, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_NO_STOP_LOSS"

    def test_check_order_rejects_spread_too_wide(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        mt5m.account_info.return_value = MagicMock(
            trade_mode=0, equity=10000.0, free_margin=8000.0,
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
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=8000.0)
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
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=8000.0)
        mt5m.positions_get.return_value = [MM(symbol="GBPUSD", type=0, profit=0)] * 5  # max_positions=5
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_POSITIONS"

    def test_check_order_rejects_insufficient_margin(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        # free_margin = 100, equity = 10000 → 1% < 20%
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=100.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INSUFFICIENT_MARGIN"

    def test_check_order_rejects_max_daily_loss(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=8000.0)
        mt5m.positions_get.return_value = [MM(profit=-30.0)]  # floating -30
        # Realized deals: profit=-20, comm=-1, swap=-0.5 → realized = -21.5
        # Total = -30 + (-21.5) = -51.5 <= -50 → fires
        deal = MM(profit=-20.0, commission=-1.0, swap=-0.5)
        mt5m.history_deals_get.return_value = [deal]
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_MAX_DAILY_LOSS"

    def test_check_order_rejects_rate_limit(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["max_orders_per_minute"] = 3
        for _ in range(3):
            r = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
            assert r == {"ok": True}
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_RATE_LIMIT"

    def test_rate_limiter_does_not_consume_slot_on_earlier_failure(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        self._happy_path_setup(mt5m, cfg)
        cfg["max_orders_per_minute"] = 2
        # Make guard #4 (max lot) fail → slot should NOT be consumed
        for _ in range(5):
            r = risk.check_order("USDJPY", "buy", 99.0, 154.50, None, cfg, is_live_intent=False)
            assert r["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"
        assert len(risk._rate_limiter) == 0  # no slots consumed

    # --- daily_loss ---
    def test_daily_loss_includes_realized_and_floating(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.positions_get.return_value = [MM(profit=-20.0), MM(profit=-10.0)]  # floating -30
        deal = MM(profit=-15.0, commission=-2.0, swap=-0.5)
        mt5m.history_deals_get.return_value = [deal]
        result = risk.daily_loss(cfg)
        # realized = -15 + (-2) + (-0.5) = -17.5; floating = -30; total = -47.5
        assert result == pytest.approx(-47.5)

    def test_check_order_rejects_account_info_none(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        mt5m.account_info.return_value = None
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_tick_none(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=8000.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = None
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_point_zero(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=10000.0, free_margin=8000.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INVALID_INPUT"

    def test_check_order_rejects_equity_zero(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
        from unittest.mock import MagicMock as MM
        mt5m.account_info.return_value = MM(trade_mode=0, equity=0.0, free_margin=0.0)
        mt5m.positions_get.return_value = []
        mt5m.symbol_info_tick.return_value = MM(ask=155.00, bid=154.99)
        mt5m.symbol_info.return_value = MM(point=0.001)
        mt5m.history_deals_get.return_value = []
        result = risk.check_order("USDJPY", "buy", 0.10, 154.50, None, cfg, is_live_intent=False)
        assert result["ok"] is False
        assert result["error"]["code"] == "RISK_INSUFFICIENT_MARGIN"

    # --- rate limiter sliding window ---
    def test_rate_limiter_sliding_window(self, mt5m, cfg):
        from cli_anything.mt5.core import risk
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
        from cli_anything.mt5 import mt5_cli
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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project

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
        from cli_anything.mt5 import mt5_cli
        assert mt5_cli._exit_code_for("RISK_MAX_LOT_EXCEEDED") == 1
        assert mt5_cli._exit_code_for("MT5_INVALID_REQUEST") == 1

    def test_exit_code_2_for_connection_error(self):
        from cli_anything.mt5 import mt5_cli
        assert mt5_cli._exit_code_for("MT5_CONNECTION_ERROR") == 2

    def test_output_human_mode_uses_red_for_error(self):
        import click
        from click.testing import CliRunner
        from cli_anything.mt5 import mt5_cli

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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project

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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project

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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project

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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project

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
        from cli_anything.mt5.utils import mt5_backend as bridge
        defaults = dict(
            login=12345678, name="Test User", server="Trading.com-Demo",
            currency="USD", balance=10000.0, equity=10000.0,
            margin=0.0, free_margin=10000.0, margin_level=0.0,
            leverage=50, profit=0.0,
            trade_mode=bridge.ACCOUNT_TRADE_MODE_DEMO,
            trade_allowed=True,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    def test_account_info_happy_path(self, mt5m):
        from cli_anything.mt5.core import account
        from cli_anything.mt5.utils import mt5_backend as bridge
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
        from cli_anything.mt5.core import account
        mt5m.account_info.return_value = None
        result = account.info()
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_CONNECTION_ERROR"

    def test_account_info_trade_mode_string_mapping(self, mt5m):
        from cli_anything.mt5.core import account
        from cli_anything.mt5.utils import mt5_backend as bridge
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
        from cli_anything.mt5.core import account
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
        from cli_anything.mt5.core import account
        mt5m.account_info.return_value = self._make_acc(
            equity=10000.0, free_margin=8000.0, currency="USD"
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
        from cli_anything.mt5 import mt5_cli
        from cli_anything.mt5.core import project
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
            digits=5, trade_tick_value=1.0,
            volume_min=0.01, volume_step=0.01, volume_max=100.0,
            swap_long=-1.5, swap_short=0.5,
            filling_mode=1, trade_mode=0,
        )
        defaults.update(kwargs)
        return MM(**defaults)

    def test_market_info_pip_size_eurusd_0_0001(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym(digits=5)
        result = market.info("EURUSD")
        assert result["ok"] is True
        assert result["data"]["pip_size"] == pytest.approx(0.0001)

    def test_market_info_pip_size_usdjpy_0_01(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym(name="USDJPY", digits=3)
        result = market.info("USDJPY")
        assert result["ok"] is True
        assert result["data"]["pip_size"] == pytest.approx(0.01)

    def test_market_info_calls_ensure_symbol(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info.return_value = self._make_sym()
        market.info("EURUSD")
        mt5m.symbol_select.assert_called_with("EURUSD", True)

    def test_market_info_ensure_symbol_false_returns_error(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = False
        result = market.info("INVALID")
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_SYMBOL"

    def test_market_tick_calls_ensure_symbol(self, mt5m):
        from unittest.mock import MagicMock as MM
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(time=1700000000, bid=1.085, ask=1.086, last=0.0, volume=0)
        market.tick("EURUSD")
        mt5m.symbol_select.assert_called_with("EURUSD", True)

    def test_market_tick_iso8601(self, mt5m):
        from unittest.mock import MagicMock as MM
        from cli_anything.mt5.core import market
        mt5m.symbol_select.return_value = True
        mt5m.symbol_info_tick.return_value = MM(time=1700000000, bid=1.085, ask=1.086, last=0.0, volume=0)
        result = market.tick("EURUSD")
        assert result["ok"] is True
        time_str = result["data"]["time"]
        # Must parse as ISO-8601 without raising
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(time_str)
        assert dt.tzinfo is not None  # timezone-aware

    def test_market_search_auto_wraps_bare_pattern(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbols_get.return_value = []
        market.search("EUR")
        mt5m.symbols_get.assert_called_once_with(group="*EUR*")

    def test_market_search_passes_explicit_glob_through(self, mt5m):
        from cli_anything.mt5.core import market
        mt5m.symbols_get.return_value = []
        market.search("EUR*,GBP*")
        mt5m.symbols_get.assert_called_once_with(group="EUR*,GBP*")

    def test_market_sessions_returns_table_for_eurusd(self):
        from cli_anything.mt5.core import market
        result = market.sessions("EURUSD")
        assert result["ok"] is True
        data = result["data"]
        assert set(data.keys()) == {"sydney", "tokyo", "london", "ny"}
        assert "start_utc" in data["london"]
        assert "end_utc" in data["london"]

    def test_market_sessions_unknown_symbol_returns_error(self):
        from cli_anything.mt5.core import market
        result = market.sessions("UNKNOWN123")
        assert result["ok"] is False
        assert result["error"]["code"] == "MT5_INVALID_SYMBOL"
