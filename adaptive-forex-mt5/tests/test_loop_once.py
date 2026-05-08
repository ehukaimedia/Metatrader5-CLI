"""End-to-end (in-process) loop_once test: heartbeat + bootstrap + infer + manage."""
from __future__ import annotations

from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {
            "loop_seconds": 1,
            "be_trigger_r": 0.80,
            "be_buffer_points": 5,
            "be_trigger_points_fallback": 80,
            "chandelier_atr_period": 2,
            "chandelier_atr_multiplier": 1.0,
            "chandelier_extreme_lookback": 3,
            "chandelier_timeframe": "M5",
            "min_sl_improvement_points": 5,
            "max_spread_points": 100,
            "modify_cooldown_seconds": 5,
        },
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_loop_once_writes_heartbeat_and_bootstraps(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": 156.50, "sl": 156.30, "tp": 157.00,
                    "direction": "buy"})
    fake_pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
                "open_price": 156.50, "sl": 156.30, "tp": 157.00, "spread": 10,
                "time": "2026-05-08T12:00:00+00:00",
                "bid": 156.50, "ask": 156.501}
    cfg = _cfg()
    with patch.object(trade_manager, "list_positions", return_value=[fake_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    hb = state_db.heartbeat_all(db)
    assert any(h["process"] == "manager" for h in hb)


def test_loop_once_ignores_non_poc_positions(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    manual_pos = {"ticket": 42, "symbol": "GBPJPY", "magic": 0, "type": "buy",
                  "open_price": 213.0, "sl": 212.5, "tp": 214.0, "spread": 30,
                  "time": "2026-05-08T12:00:00+00:00",
                  "bid": 213.0, "ask": 213.03}
    cfg = _cfg()
    with patch.object(trade_manager, "list_positions", return_value=[manual_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "poc_magics", return_value={128461}):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    assert rows == []  # manual magic=0 stays untouched
