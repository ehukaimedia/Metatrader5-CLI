"""Regression tests for Codex1's phase-3 final-audit findings.

P1 #1: allowlist gates by ticket+symbol+account (not ticket alone).
P1 #2: adopted positions with sl<=0 fail closed and journal adoption_skip.
P2 #3: mode=trail_only skips the BE move (manage straight from be_armed).
P3 #4: bootstrap_position is the canonical-private _bootstrap_position;
       loop_once is the single eligibility gatekeeper.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _entry(*, ticket=204841232, symbol="GBPJPY", account=9999, mode="trail_only"):
    return {
        "ticket": ticket,
        "symbol": symbol,
        "account": account,
        "mode": mode,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "operator_note": "test",
    }


def _setup(tmp_path, monkeypatch, allowlist_entries):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    allowlist_path = tmp_path / "managed_positions.json"
    allowlist_path.write_text(json.dumps(allowlist_entries))
    return db, log, allowlist_path


def _cfg(allowlist_path):
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"loop_seconds": 1, "be_buffer_points": 5,
                    "max_spread_points": 100, "min_sl_improvement_points": 5,
                    "modify_cooldown_seconds": 5,
                    "allowlist_path": str(allowlist_path)},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def _kinds(log):
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


# ---- P1 #1: ticket+symbol+account match ---------------------------------

def test_adoption_skips_on_symbol_mismatch(tmp_path, monkeypatch):
    """Allowlist says ticket 1 is GBPJPY; live position with ticket 1 is
    actually USDJPY (operator typo or stale entry). Must fail closed."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY")])
    pos = {"ticket": 1, "symbol": "USDJPY", "magic": 0, "type": "buy",
           "open_price": 156.50, "sl": 156.30, "tp": 157.00, "spread": 10,
           "time": "t"}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    assert state_db.list_managed_positions(db) == []
    skip = [r for r in _kinds(log) if r["kind"] == "adoption_skip"]
    assert skip and "symbol_mismatch" in skip[0]["reason"]


def test_adoption_skips_on_account_mismatch(tmp_path, monkeypatch):
    """Allowlist says account 9999; live account is 8888. Different account
    = different broker session = must fail closed."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY", account=9999)])
    pos = {"ticket": 1, "symbol": "GBPJPY", "magic": 0, "type": "buy",
           "open_price": 213.0, "sl": 212.5, "tp": 214.0, "spread": 30,
           "time": "t"}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=8888), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    assert state_db.list_managed_positions(db) == []
    skip = [r for r in _kinds(log) if r["kind"] == "adoption_skip"]
    assert skip and "account_mismatch" in skip[0]["reason"]


def test_adoption_skips_when_account_lookup_fails(tmp_path, monkeypatch):
    """_account_login returns 0 when MT5 account info is unavailable. We
    must fail closed on adoption rather than letting through with a
    fictional account."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY", account=9999)])
    pos = {"ticket": 1, "symbol": "GBPJPY", "magic": 0, "type": "buy",
           "open_price": 213.0, "sl": 212.5, "tp": 214.0, "spread": 30,
           "time": "t"}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=0), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    assert state_db.list_managed_positions(db) == []
    skip = [r for r in _kinds(log) if r["kind"] == "adoption_skip"]
    assert skip
    # The first skip is the account_lookup_failed banner; it might be
    # alone or accompanied by per-ticket skips depending on flow order.
    assert any("account_lookup_failed" in (s.get("reason") or "") for s in skip)


# ---- P1 #2: sl<=0 fails closed ------------------------------------------

def test_adoption_skips_on_no_protective_sl(tmp_path, monkeypatch):
    """Live position has sl=0 (operator forgot a stop). No risk anchor =
    can't compute initial_risk = must fail closed."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY")])
    pos = {"ticket": 1, "symbol": "GBPJPY", "magic": 0, "type": "buy",
           "open_price": 213.0, "sl": 0, "tp": 214.0, "spread": 30,
           "time": "t"}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    assert state_db.list_managed_positions(db) == []
    skip = [r for r in _kinds(log) if r["kind"] == "adoption_skip"]
    assert skip and "no_protective_sl" in skip[0]["reason"]


# ---- P2 #3: mode=trail_only skips the BE move ---------------------------

def test_trail_only_mode_promotes_to_be_armed_skipping_be(tmp_path, monkeypatch):
    """A trail_only adoption must NOT do a BE move — go straight to trail.
    Verified by the post-bootstrap row having stage='be_armed' with
    last_sl_set pinned to the current SL."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY",
                                             mode="trail_only")])
    pos = {"ticket": 1, "symbol": "GBPJPY", "magic": 0, "type": "buy",
           "open_price": 213.0, "sl": 212.5, "tp": 214.0, "spread": 30,
           "time": "t", "bid": 213.40, "ask": 213.43}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    row = state_db.get_managed_position(db, 1)
    assert row is not None
    assert row["stage"] == "be_armed"
    assert row["last_sl_set"] == 212.5  # pinned to current SL


def test_be_and_trail_mode_starts_from_init(tmp_path, monkeypatch):
    """The default be_and_trail mode preserves phase-1 behavior — start at
    init, BE-move first, then trail. Sanity check that the trail_only
    promotion doesn't accidentally apply to be_and_trail."""
    db, log, allowlist_path = _setup(tmp_path, monkeypatch,
                                     [_entry(ticket=1, symbol="GBPJPY",
                                             mode="be_and_trail")])
    pos = {"ticket": 1, "symbol": "GBPJPY", "magic": 0, "type": "buy",
           "open_price": 213.0, "sl": 212.5, "tp": 214.0, "spread": 30,
           "time": "t", "bid": 213.0, "ask": 213.03}
    cfg = _cfg(allowlist_path)
    with patch.object(trade_manager, "list_positions", return_value=[pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    row = state_db.get_managed_position(db, 1)
    assert row is not None
    assert row["stage"] == "init"


# ---- P3 #4: bootstrap_position alias + canonical private ----------------

def test_bootstrap_position_canonical_name_is_private():
    """The canonical name is _bootstrap_position; bootstrap_position is a
    backward-compat alias. New callers should prefer the underscored
    name to flag that they own the eligibility gate."""
    assert hasattr(trade_manager, "_bootstrap_position")
    assert trade_manager.bootstrap_position is trade_manager._bootstrap_position
