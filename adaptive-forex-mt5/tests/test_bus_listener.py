"""Bus listener for 'AUTOPILOT ABORT' — operator can abort from any device."""
from __future__ import annotations

from unittest.mock import patch

import autopilot
import state_db


def test_bus_listener_flips_kill_switch_on_abort_from_operator(tmp_path):
    db = tmp_path / "state.db"
    state_db.init(db)
    bus_text = (
        "10:00:00 AM tasks → operator: Task done. [tasks]\n"
        "10:00:30 AM operator → Claude1: AUTOPILOT ABORT\n"
        "10:00:45 AM Claude1 → operator: ack\n"
    )
    with patch("autopilot.subprocess.run") as mock_run, \
         patch("autopilot.journal"):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = bus_text
        flipped = autopilot.poll_bus_for_abort(db, lookback=20)
    assert flipped is True
    assert autopilot.kill_switch_get(db) == "on"


def test_bus_listener_ignores_abort_from_non_operator(tmp_path):
    db = tmp_path / "state.db"
    state_db.init(db)
    bus_text = (
        "10:00:00 AM Claude1 → Codex1: testing AUTOPILOT ABORT command\n"
    )
    with patch("autopilot.subprocess.run") as mock_run, \
         patch("autopilot.journal"):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = bus_text
        flipped = autopilot.poll_bus_for_abort(db, lookback=20)
    assert flipped is False
    assert autopilot.kill_switch_get(db) == "off"


def test_bus_listener_idempotent_already_on(tmp_path, monkeypatch):
    """If kill-switch is already on, repeated ABORT messages don't cause noise."""
    db = tmp_path / "state.db"
    state_db.init(db)
    import journal
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    autopilot.kill_switch_set(db, "on", source="dashboard")  # already on
    bus_text = "10:00:30 AM operator → Claude1: AUTOPILOT ABORT\n"
    with patch("autopilot.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = bus_text
        autopilot.poll_bus_for_abort(db, lookback=20)
    # Only ONE autopilot_kill in journal (the original "dashboard" set), not a second from the bus
    import json as _json
    rows = [_json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kills = [r for r in rows if r["kind"] == "autopilot_kill"]
    assert len(kills) == 1
    assert kills[0]["source"] == "dashboard"


def test_bus_listener_returns_false_on_subprocess_failure(tmp_path):
    db = tmp_path / "state.db"
    state_db.init(db)
    with patch("autopilot.subprocess.run") as mock_run, \
         patch("autopilot.journal"):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stdout = ""
        assert autopilot.poll_bus_for_abort(db, lookback=20) is False
