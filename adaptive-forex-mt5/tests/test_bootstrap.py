"""Bootstrap matches MT5 positions to journal placements; fail-closed on
ambiguity or missing data."""
from __future__ import annotations

import json
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY", "GBPJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"loop_seconds": 1, "be_buffer_points": 5},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_poc_magics_derived_from_pairs():
    cfg = _cfg()
    magics = trade_manager.poc_magics(cfg)
    assert len(magics) == 2
    assert all(isinstance(m, int) for m in magics)


def test_bootstrap_ticket_match(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    journal.append({
        "kind": "placement", "pair": "USDJPY",
        "ticket": 99, "magic": 128461,
        "entry": 156.50, "sl": 156.30, "tp": 157.00,
        "direction": "buy",
    })
    cfg = _cfg()
    pos = {
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "volume": 0.001, "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    assert rows[0]["ticket"] == 99
    assert rows[0]["initial_sl"] == 156.30
    assert rows[0]["stage"] == "init"


def test_bootstrap_fail_closed_no_match(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    cfg = _cfg()
    pos = {
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "volume": 0.001, "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert rows == []
    lines = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kinds = [r["kind"] for r in lines]
    assert "unmanaged_poc_position" in kinds


def test_bootstrap_ambiguous_magic_symbol_fails_closed(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 50, "magic": 128461,
                    "entry": 156.20, "sl": 156.00, "tp": 156.80, "direction": "buy"})
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 60, "magic": 128461,
                    "entry": 156.30, "sl": 156.10, "tp": 156.90, "direction": "buy"})
    cfg = _cfg()
    pos = {
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert rows == []
