"""Skeleton tests: trade_manager initializes state.db and writes heartbeat."""
from __future__ import annotations

from unittest.mock import patch

import state_db
import trade_manager


def test_init_creates_state_db(tmp_path):
    db = tmp_path / "state.db"
    trade_manager.init_state(db)
    rows = state_db.heartbeat_all(db)
    assert isinstance(rows, list)


def test_loop_once_upserts_heartbeat(tmp_path):
    db = tmp_path / "state.db"
    trade_manager.init_state(db)
    cfg = {
        "manager": {"loop_seconds": 1},
        "pairs": [],
        "agent": {"strategy_id_prefix": "x"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }
    with patch("trade_manager.list_positions", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.heartbeat_all(db)
    procs = {r["process"] for r in rows}
    assert "manager" in procs
