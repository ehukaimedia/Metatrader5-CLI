"""Unit tests for new journal event kinds added in phase 1."""
from __future__ import annotations

import json
from pathlib import Path

import journal


def _read_kinds(tmp_log: Path) -> list[str]:
    return [json.loads(l)["kind"] for l in tmp_log.read_text().splitlines() if l.strip()]


def test_log_llm_verdict_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_llm_verdict("USDJPY", {"alert_id": "abc", "decision": "take", "confidence": 0.8})
    assert _read_kinds(log) == ["llm_verdict"]


def test_log_manage_action_includes_required_fields(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_manage_action(ticket=42, stage_from="init", stage_to="be_armed",
                              old_sl=1.20, new_sl=1.205, trigger="be_r")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "manage_action"
    assert rec["ticket"] == 42
    assert rec["stage_from"] == "init"
    assert rec["stage_to"] == "be_armed"
    assert rec["old_sl"] == 1.20
    assert rec["new_sl"] == 1.205
    assert rec["trigger"] == "be_r"
    assert "ts" in rec


def test_log_manage_skip_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_manage_skip(ticket=42, reason="spread_cap")
    assert _read_kinds(log) == ["manage_skip"]


def test_log_unmanaged_poc_position(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_unmanaged_poc_position(ticket=42, symbol="USDJPY", magic=128461,
                                       reason="no_journal_match")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "unmanaged_poc_position"
    assert rec["reason"] == "no_journal_match"


def test_log_review_request_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_review_request(alert_id="abc", task_id="t-1", pair="USDJPY")
    assert _read_kinds(log) == ["review_request"]
