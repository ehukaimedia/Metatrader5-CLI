"""Bootstrap should infer stage from current SL relative to entry, never loosen."""
from __future__ import annotations

from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"be_buffer_points": 5},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def _seed_placement(monkeypatch, tmp_path, sl=156.30, entry=156.50):
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": entry, "sl": sl, "tp": 157.00,
                    "direction": "buy"})


def test_init_stage_when_sl_below_entry_buy(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.30, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
    assert row["last_sl_set"] is None


def test_be_armed_when_sl_at_or_above_entry_buy(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.505, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "be_armed"
    assert row["last_sl_set"] == 156.505


def test_be_armed_for_sell_when_sl_below_entry_minus_buffer(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path, sl=156.70, entry=156.50)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "sell",
           "open_price": 156.50, "sl": 156.495, "tp": 156.00,
           "time": "2026-05-08T12:00:00+00:00"}
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "be_armed"


def test_init_stage_for_sell_when_sl_above_entry(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path, sl=156.70, entry=156.50)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "sell",
           "open_price": 156.50, "sl": 156.70, "tp": 156.00,
           "time": "2026-05-08T12:00:00+00:00"}
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
