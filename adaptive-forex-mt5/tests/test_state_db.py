"""Unit tests for state_db module."""
from __future__ import annotations

from pathlib import Path

import pytest

import state_db


@pytest.fixture
def db(tmp_path) -> Path:
    p = tmp_path / "state.db"
    state_db.init(p)
    return p


def test_init_creates_tables(db):
    with state_db.connect(db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"managed_position", "cursor", "heartbeat"} <= names


def test_init_is_idempotent(db):
    state_db.init(db)  # second call should be a no-op
    with state_db.connect(db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"managed_position", "cursor", "heartbeat"} <= names


def test_upsert_managed_position_round_trip(db):
    row = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "init",
    }
    state_db.upsert_managed_position(db, row)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    assert rows[0]["ticket"] == 42
    assert rows[0]["symbol"] == "USDJPY"
    assert rows[0]["stage"] == "init"


def test_active_pos_uniq_index_blocks_duplicate_active(db):
    base = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "init",
    }
    state_db.upsert_managed_position(db, base)
    duplicate = {**base, "ticket": 43}
    with pytest.raises(state_db.DuplicateActiveError):
        state_db.upsert_managed_position(db, duplicate)


def test_active_pos_uniq_allows_new_after_close(db):
    base = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "closed",
    }
    state_db.upsert_managed_position(db, base)
    new = {**base, "ticket": 43, "stage": "init"}
    state_db.upsert_managed_position(db, new)  # must not raise


def test_cursor_get_set(db):
    assert state_db.cursor_get(db, "last_verdict_seen") is None
    state_db.cursor_set(db, "last_verdict_seen", "2026-05-08T12:00:00+00:00")
    assert state_db.cursor_get(db, "last_verdict_seen") == "2026-05-08T12:00:00+00:00"


def test_heartbeat_upsert_get(db):
    state_db.heartbeat_upsert(db, "manager", pid=1234)
    rows = state_db.heartbeat_all(db)
    assert any(r["process"] == "manager" and r["pid"] == 1234 for r in rows)
