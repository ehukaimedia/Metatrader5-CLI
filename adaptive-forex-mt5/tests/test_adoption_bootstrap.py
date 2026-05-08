"""Phase-3 bootstrap path for allowlisted manual trades.

Invariants verified here:
- A position whose magic is NOT in poc-set but whose ticket IS in the
  allowlist gets adopted (synthesized placement + bootstrapped).
- A position whose magic is NOT in poc-set and ticket is NOT in the
  allowlist is left untouched (phase-1 invariant preserved).
- The synthesized placement record is idempotent across loops.
- Allowlisted ticket but no live MT5 position → no synth, no warning loop.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _allowlist_entry(ticket=204841232, symbol="GBPJPY"):
    return {
        "ticket": ticket,
        "symbol": symbol,
        "account": 9999,
        "mode": "trail_only",
        "be_r": 0.80,
        "trail_model": "chandelier_atr22_3.0",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "operator_note": "manual long, hand to bot for trail",
    }


def _cfg(*, allowlist_path):
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"loop_seconds": 1, "be_buffer_points": 5,
                    "max_spread_points": 100, "min_sl_improvement_points": 5,
                    "modify_cooldown_seconds": 5,
                    "allowlist_path": str(allowlist_path)},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def _setup(tmp_path, monkeypatch, allowlist_entries=None):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    allowlist_path = tmp_path / "managed_positions.json"
    if allowlist_entries:
        allowlist_path.write_text(json.dumps(allowlist_entries))
    return db, log, allowlist_path


def test_allowlisted_manual_position_is_adopted(tmp_path, monkeypatch):
    """The big invariant: a magic=0 position whose ticket is allowlisted
    gets adopted — synthesized placement + managed_position row in state.db."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_allowlist_entry(ticket=204841232,
                                                       symbol="GBPJPY")])
    cfg = _cfg(allowlist_path=allowlist_path)
    manual_pos = {
        "ticket": 204841232, "symbol": "GBPJPY", "magic": 0, "type": "buy",
        "volume": 0.5, "open_price": 213.216, "sl": 213.269, "tp": 213.959,
        "time": "2026-05-08T12:00:00+00:00", "bid": 213.40, "ask": 213.43,
        "spread": 30,
    }
    with patch.object(trade_manager, "list_positions", return_value=[manual_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    assert rows[0]["ticket"] == 204841232
    # Synthesized placement record exists and is marked adopted=true
    placement_rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    placements = [r for r in placement_rows
                  if r["kind"] == "placement" and r.get("adopted")]
    assert len(placements) == 1
    assert placements[0]["ticket"] == 204841232


def test_non_allowlisted_manual_position_left_untouched(tmp_path, monkeypatch):
    """Phase-1 invariant preserved: magic=0 + not allowlisted → ignored."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_allowlist_entry(ticket=999, symbol="USDJPY")])
    cfg = _cfg(allowlist_path=allowlist_path)
    manual_pos = {
        "ticket": 204841232, "symbol": "GBPJPY", "magic": 0, "type": "buy",
        "volume": 0.5, "open_price": 213.216, "sl": 213.269, "tp": 213.959,
        "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "list_positions", return_value=[manual_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    assert rows == []


def test_synthesized_placement_is_idempotent(tmp_path, monkeypatch):
    """Two loops on the same allowlisted ticket must NOT duplicate the
    synthesized placement record."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_allowlist_entry(ticket=204841232,
                                                       symbol="GBPJPY")])
    cfg = _cfg(allowlist_path=allowlist_path)
    manual_pos = {
        "ticket": 204841232, "symbol": "GBPJPY", "magic": 0, "type": "buy",
        "volume": 0.5, "open_price": 213.216, "sl": 213.269, "tp": 213.959,
        "time": "2026-05-08T12:00:00+00:00", "bid": 213.40, "ask": 213.43,
        "spread": 30,
    }
    with patch.object(trade_manager, "list_positions", return_value=[manual_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
        trade_manager.loop_once(cfg, db)
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    placements = [r for r in rows if r["kind"] == "placement" and r.get("adopted")]
    assert len(placements) == 1


def test_allowlisted_but_no_live_position(tmp_path, monkeypatch):
    """Allowlisted ticket but no matching MT5 position (e.g. operator
    closed it). No synth, no managed row, no errors."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_allowlist_entry(ticket=204841232)])
    cfg = _cfg(allowlist_path=allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[]), \
         patch.object(trade_manager, "_account_login", return_value=9999):
        trade_manager.loop_once(cfg, db)
    assert state_db.list_managed_positions(db) == []
    if log.exists():
        placement_rows = [r for r in
                          [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
                          if r.get("kind") == "placement"]
        assert placement_rows == []


def test_poc_magic_position_still_works_alongside_adoption(tmp_path, monkeypatch):
    """Phase-1 path coexists: a poc-magic position adopts via journal-match
    (existing path) while a magic=0 allowlisted position adopts via
    synthesized placement."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_allowlist_entry(ticket=999, symbol="GBPJPY")])
    # Pre-seed a poc-magic placement
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 50,
                    "magic": 128461, "entry": 156.50, "sl": 156.30, "tp": 157.00,
                    "direction": "buy"})
    cfg = _cfg(allowlist_path=allowlist_path)
    poc_pos = {"ticket": 50, "symbol": "USDJPY", "magic": 128461, "type": "buy",
               "open_price": 156.50, "sl": 156.30, "tp": 157.00,
               "time": "t", "spread": 10, "bid": 156.50, "ask": 156.51}
    manual_pos = {"ticket": 999, "symbol": "GBPJPY", "magic": 0, "type": "buy",
                  "open_price": 213.0, "sl": 212.5, "tp": 214.0,
                  "time": "t", "spread": 30, "bid": 213.0, "ask": 213.03}
    with patch.object(trade_manager, "list_positions",
                      return_value=[poc_pos, manual_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    tickets = {r["ticket"] for r in rows}
    assert tickets == {50, 999}
