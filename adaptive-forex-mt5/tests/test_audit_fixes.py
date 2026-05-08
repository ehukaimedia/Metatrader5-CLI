"""Regression tests for Codex1's phase-1 final audit findings.

1. list_positions enriches each row with bid/ask/spread from market info.
2. Unmanaged-warning rate-limit survives across two bootstrap calls
   (only ONE log entry within the 60s window) and surfaces to the dashboard
   even when no managed_position row exists.
3. Pending modify is single-flight: a freshly computed Chandelier target
   that differs from the pending requested_sl must NOT issue a second
   broker call while the first is in flight.
5. Stage inference rejects sl <= 0 — sell positions with no SL set must
   stay 'init' (the prior buggy code would promote them to be_armed).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg(*, live: bool = False):
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"loop_seconds": 1, "be_buffer_points": 5,
                    "min_sl_improvement_points": 5, "max_spread_points": 100,
                    "modify_cooldown_seconds": 5},
        "mt5_cli": {"command": "mt5", "live": live, "subprocess_timeout_seconds": 60},
    }


# ---- Finding 1: list_positions enriches with bid/ask/spread -----------------

def test_list_positions_enriches_with_quote():
    cfg = _cfg()

    def fake_run(cfg, args):
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [{
                "ticket": 99, "symbol": "USDJPY", "type": "buy",
                "volume": 0.001, "open_price": 156.50,
                "sl": 156.30, "tp": 157.00, "profit": 1.0, "swap": 0.0,
                "magic": 128461, "comment": "",
            }]}
        if args[:2] == ["market", "info"]:
            return {"ok": True, "data": {
                "symbol": "USDJPY", "bid": 156.70, "ask": 156.711,
                "spread": 11, "digits": 3, "point": 0.001,
            }}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        positions = trade_manager.list_positions(cfg)

    assert len(positions) == 1
    p = positions[0]
    assert p["bid"] == 156.70
    assert p["ask"] == 156.711
    assert p["spread"] == 11


def test_list_positions_caches_quote_per_symbol():
    """Two positions on the same symbol should fetch market info ONCE."""
    cfg = _cfg()
    market_info_calls = []

    def fake_run(cfg, args):
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [
                {"ticket": 1, "symbol": "USDJPY", "type": "buy", "volume": 0.001,
                 "open_price": 156.5, "sl": 156.3, "tp": 157.0, "magic": 128461},
                {"ticket": 2, "symbol": "USDJPY", "type": "sell", "volume": 0.001,
                 "open_price": 156.6, "sl": 156.9, "tp": 156.0, "magic": 128462},
            ]}
        if args[:2] == ["market", "info"]:
            market_info_calls.append(args[2])
            return {"ok": True, "data": {"bid": 156.70, "ask": 156.71, "spread": 10}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.list_positions(cfg)
    assert market_info_calls == ["USDJPY"]  # one call, not two


# ---- Finding 2: unmanaged warning rate-limit + dashboard surface ------------

def test_two_bootstraps_within_60s_emit_only_one_warning(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.30, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    cfg = _cfg()
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
        # Second call right after — must NOT emit another warning
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]
    assert kinds.count("unmanaged_poc_position") == 1


def test_unmanaged_warning_visible_to_dashboard_without_managed_row(tmp_path, monkeypatch):
    """Fail-closed bootstrap must surface a warning even though the position
    never gets a managed_position row."""
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.30, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    cfg = _cfg()
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    # No managed_position row — but the warning must still be queryable
    assert state_db.list_managed_positions(db) == []
    recent = state_db.unmanaged_warning_recent(db, since_seconds=60)
    assert len(recent) == 1
    assert recent[0]["ticket"] == 99


# ---- Finding 3: pending modify single-flight (dynamic-target hole) ----------

def test_pending_modify_with_different_new_sl_does_not_issue_fresh_call(tmp_path, monkeypatch):
    """If a pending modify exists with requested_sl=156.40 and the manager
    later proposes 156.45 (e.g. Chandelier moved), the second call MUST NOT
    issue a fresh `position move-sl` while the first might still be in flight.
    """
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    state_db.upsert_managed_position(db, {
        "ticket": 99, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": None, "journal_anchor": None, "stage": "be_armed",
    })
    # Pre-existing pending @ 156.40 with cooldown not yet elapsed
    row = state_db.get_managed_position(db, 99)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = 156.40
    row["idempotency_key"] = "preexisting"
    row["last_action_ts"] = datetime.now(timezone.utc).isoformat()
    state_db.upsert_managed_position(db, row)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    move_sl_calls = 0

    def fake_run(cfg, args):
        nonlocal move_sl_calls
        if args[:2] == ["position", "list"]:
            # MT5 still at the OLD sl — pending hasn't landed yet
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        if args[:2] == ["position", "move-sl"]:
            move_sl_calls += 1
            return {"ok": True, "data": {"retcode": 10009}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        # Manager proposes a NEW target (156.45) different from pending (156.40).
        # Single-flight must block: cooldown not elapsed, no broker call.
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.45, reason="chandelier",
                                     stage_to="trailing")

    assert move_sl_calls == 0
    skips = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert any(r.get("reason") == "cooldown" for r in skips)


def test_pending_modify_cooldown_elapsed_retries_with_pending_sl_not_new_sl(tmp_path, monkeypatch):
    """When the cooldown elapses, the retry must use the EXISTING pending
    requested_sl + idempotency_key, NOT the freshly computed new_sl."""
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    state_db.upsert_managed_position(db, {
        "ticket": 99, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": None, "journal_anchor": None, "stage": "be_armed",
    })
    row = state_db.get_managed_position(db, 99)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = 156.40
    row["idempotency_key"] = "preexisting"
    row["last_action_ts"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    state_db.upsert_managed_position(db, row)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    move_sl_args = []

    def fake_run(cfg, args):
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        if args[:2] == ["position", "move-sl"]:
            move_sl_args.append(list(args))
            return {"ok": True, "data": {"retcode": 10009}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        # Manager proposes a NEW target (156.45) but cooldown elapsed and a
        # pending exists @ 156.40 — the retry must use 156.40, not 156.45.
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.45, reason="chandelier",
                                     stage_to="trailing")

    assert len(move_sl_args) == 1
    sent_args = move_sl_args[0]
    sl_idx = sent_args.index("--sl") + 1
    assert sent_args[sl_idx] == "156.400"  # pending value, not 156.450


# ---- Finding 5: sl <= 0 must not promote on stage inference ----------------

def test_sell_with_sl_zero_stays_init(tmp_path, monkeypatch):
    """A sell position with sl=0 trivially satisfies `sl <= entry - buf*point`
    and would falsely promote to be_armed under the prior implementation."""
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": 156.50, "sl": 156.70, "tp": 156.00,
                    "direction": "sell"})
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "sell",
           "open_price": 156.50, "sl": 0, "tp": 156.00,  # sl=0 — no protective stop
           "time": "2026-05-08T12:00:00+00:00"}
    cfg = _cfg()
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(cfg, db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
    assert row["last_sl_set"] is None


def test_buy_with_sl_zero_stays_init(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": 156.50, "sl": 156.30, "tp": 157.00,
                    "direction": "buy"})
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 0, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    cfg = _cfg()
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(cfg, db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
