"""Autopilot kill-switch helpers."""
from __future__ import annotations

import json

import autopilot
import journal
import state_db


def test_kill_switch_default_off(tmp_path):
    db = tmp_path / "state.db"
    state_db.init(db)
    assert autopilot.kill_switch_get(db) == "off"


def test_kill_switch_set_persists_and_journals(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    autopilot.kill_switch_set(db, "on", source="bus")
    assert autopilot.kill_switch_get(db) == "on"
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kill_records = [r for r in records if r["kind"] == "autopilot_kill"]
    assert len(kill_records) == 1
    assert kill_records[0]["prev"] == "off"
    assert kill_records[0]["new"] == "on"
    assert kill_records[0]["source"] == "bus"


def test_kill_switch_idempotent_no_double_journal(tmp_path, monkeypatch):
    """Setting the same state twice must NOT journal a second autopilot_kill
    event — the bus listener may issue ABORT repeatedly."""
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    autopilot.kill_switch_set(db, "on", source="bus")
    autopilot.kill_switch_set(db, "on", source="bus")
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kill_records = [r for r in records if r["kind"] == "autopilot_kill"]
    assert len(kill_records) == 1


def test_kill_switch_clear_back_to_off(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    autopilot.kill_switch_set(db, "on", source="dashboard")
    autopilot.kill_switch_set(db, "off", source="dashboard")
    assert autopilot.kill_switch_get(db) == "off"
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kill_records = [r for r in records if r["kind"] == "autopilot_kill"]
    assert len(kill_records) == 2
    assert kill_records[1]["prev"] == "on"
    assert kill_records[1]["new"] == "off"
