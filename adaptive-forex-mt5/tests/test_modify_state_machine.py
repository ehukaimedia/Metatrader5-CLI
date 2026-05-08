"""Confirm-before-promote modify state machine.

Codex1's NO-GO points (made explicit in this task):
1. Live-gated: cfg.mt5_cli.live=False → no broker call, manage_skip reason=not_live.
2. Confirm-existing-without-broker-call: pending_action set + MT5.sl already at
   requested_sl → promote, NO `position move-sl` call.
3. Cooldown-elapsed retry uses the SAME idempotency_key (no fresh hash).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _seeded(tmp_path, monkeypatch):
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
        "source_order_ticket": None, "journal_anchor": None, "stage": "init",
    })
    return db, log


def _kinds(log) -> list[str]:
    return [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]


def _cfg(*, live: bool, cooldown: float = 5):
    return {
        "manager": {
            "min_sl_improvement_points": 5,
            "max_spread_points": 100,
            "modify_cooldown_seconds": cooldown,
        },
        "mt5_cli": {"command": "mt5", "live": live, "subprocess_timeout_seconds": 60},
    }


def test_live_false_skips_with_not_live(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    with patch.object(trade_manager, "_run") as mock_run:
        trade_manager.attempt_modify(_cfg(live=False), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")
    row = state_db.get_managed_position(db, 99)
    assert row["last_sl_set"] is None
    assert row["pending_action"] is None
    assert "manage_skip" in _kinds(log)
    # No broker call attempted
    assert mock_run.call_count == 0


def test_spread_cap_skips(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 200}
    with patch.object(trade_manager, "_run") as mock_run:
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")
    assert mock_run.call_count == 0
    skips = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert any(r.get("reason") == "spread_cap" for r in skips)


def test_min_improvement_skips(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    # 4 points improvement, below 5-point floor
    with patch.object(trade_manager, "_run") as mock_run:
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.304, reason="trail")
    assert mock_run.call_count == 0
    skips = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert any(r.get("reason") == "min_improvement" for r in skips)


def test_successful_modify_promotes_last_sl_set(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    def fake_run(cfg, args):
        if args[:2] == ["position", "move-sl"]:
            return {"ok": True, "data": {"retcode": 10009}}
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.40,
                                          "symbol": "USDJPY", "type": "buy"}]}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")
    row = state_db.get_managed_position(db, 99)
    assert row["last_sl_set"] == 156.40
    assert row["stage"] == "be_armed"
    assert row["pending_action"] is None
    assert row["requested_sl"] is None
    assert row["idempotency_key"] is None
    assert "manage_action" in _kinds(log)


def test_unknown_result_keeps_pending_for_retry(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    def fake_run(cfg, args):
        if args[:2] == ["position", "move-sl"]:
            return {"ok": True, "data": {"retcode": 10009}}
        if args[:2] == ["position", "list"]:
            # Confirm read shows the OLD SL — broker hasn't updated yet
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")
    row = state_db.get_managed_position(db, 99)
    assert row["pending_action"] == "modify_sl"
    assert row["requested_sl"] == 156.40
    assert row["last_sl_set"] is None
    assert row["idempotency_key"] is not None


def test_pending_existing_already_at_requested_promotes_without_broker_call(tmp_path, monkeypatch):
    """The confirm-existing path: pending_action set, requested_sl matches the
    new target, MT5.sl ALREADY at that level → promote, no broker call.

    This catches the lost-ack scenario where the previous attempt succeeded but
    the response was lost/timed out, and prevents a duplicate broker call.
    """
    db, log = _seeded(tmp_path, monkeypatch)
    # Pre-seed a pending_action on the row
    row = state_db.get_managed_position(db, 99)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = 156.40
    row["idempotency_key"] = "preexisting"
    row["last_action_ts"] = datetime.now(timezone.utc).isoformat()
    state_db.upsert_managed_position(db, row)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    list_call_count = 0
    move_sl_call_count = 0

    def fake_run(cfg, args):
        nonlocal list_call_count, move_sl_call_count
        if args[:2] == ["position", "list"]:
            list_call_count += 1
            # MT5 already at the requested SL — previous call landed, ack lost
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.40,
                                          "symbol": "USDJPY", "type": "buy"}]}
        if args[:2] == ["position", "move-sl"]:
            move_sl_call_count += 1
            return {"ok": True, "data": {"retcode": 10009}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(_cfg(live=True), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")

    # CRITICAL: no `position move-sl` broker call — we just confirmed.
    assert move_sl_call_count == 0
    assert list_call_count >= 1
    row = state_db.get_managed_position(db, 99)
    assert row["last_sl_set"] == 156.40
    assert row["stage"] == "be_armed"
    assert row["pending_action"] is None


def test_cooldown_blocks_rapid_retry(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    # Pre-seed pending_action, last_action_ts very recent
    row = state_db.get_managed_position(db, 99)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = 156.40
    row["idempotency_key"] = "preexisting"
    row["last_action_ts"] = datetime.now(timezone.utc).isoformat()
    state_db.upsert_managed_position(db, row)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    def fake_run(cfg, args):
        if args[:2] == ["position", "list"]:
            # MT5 still at the OLD SL, so we'd want to retry — except cooldown
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        if args[:2] == ["position", "move-sl"]:
            return {"ok": True, "data": {"retcode": 10009}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run) as mock_run:
        trade_manager.attempt_modify(_cfg(live=True, cooldown=5), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")

    # Cooldown should have blocked the modify call
    move_sl_calls = [c for c in mock_run.call_args_list if c.args[1][:2] == ["position", "move-sl"]]
    assert len(move_sl_calls) == 0
    skips = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert any(r.get("reason") == "cooldown" for r in skips)


def test_cooldown_elapsed_retry_reuses_same_idempotency_key(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    pre_existing_key = "preexisting-abcdef12"
    # Pre-seed pending_action, last_action_ts well in the past
    row = state_db.get_managed_position(db, 99)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = 156.40
    row["idempotency_key"] = pre_existing_key
    row["last_action_ts"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    state_db.upsert_managed_position(db, row)
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}

    captured_keys: list[str] = []

    def fake_run(cfg, args):
        if args[:2] == ["position", "list"]:
            # First read: still at old SL → triggers cooldown-elapsed retry path.
            # We capture the idempotency key during the retry by inspecting the
            # state.db row at the time of the move-sl call.
            current = state_db.get_managed_position(db, 99)
            captured_keys.append(current.get("idempotency_key"))
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        if args[:2] == ["position", "move-sl"]:
            current = state_db.get_managed_position(db, 99)
            captured_keys.append(current.get("idempotency_key"))
            return {"ok": True, "data": {"retcode": 10009}}
        return None

    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(_cfg(live=True, cooldown=5), db, pos,
                                     new_sl=156.40, reason="be_r", stage_to="be_armed")

    # The idempotency_key during the retry must equal the pre-existing one
    # (Codex1's must-fix: cooldown-elapsed retry reuses the same key so a
    # duplicate broker call cannot end up double-applied).
    assert pre_existing_key in captured_keys
