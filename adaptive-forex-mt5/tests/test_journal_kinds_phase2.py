"""Phase-2 journal kinds: consensus_verdict, autopilot_placement, autopilot_skip, autopilot_kill."""
from __future__ import annotations

import json

import journal


def _kinds(log):
    return [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]


def test_log_consensus_verdict(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_consensus_verdict({
        "alert_id": "x", "setup_fingerprint": "deadbeef",
        "consensus": "take", "consensus_reason": "2-of-2",
        "votes": [], "reviewers": ["A", "B"],
    })
    assert _kinds(log) == ["consensus_verdict"]


def test_log_autopilot_placement(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_placement(
        pair="USDJPY",
        placement={"data": {"placement": {"ticket": 99, "magic": 128461}}},
        consensus_alert_id="abc",
        reviewer_confidences=[0.84, 0.79],
    )
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "autopilot_placement"
    assert rec["pair"] == "USDJPY"
    assert rec["consensus_alert_id"] == "abc"
    assert rec["reviewer_confidences"] == [0.84, 0.79]


def test_log_autopilot_skip(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_skip(alert_id="abc", gate="news_blackout",
                               reason="event_within_window")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "autopilot_skip"
    assert rec["gate"] == "news_blackout"
    assert rec["reason"] == "event_within_window"


def test_log_autopilot_kill(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_autopilot_kill(prev="off", new="on", source="bus")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "autopilot_kill"
    assert rec["prev"] == "off"
    assert rec["new"] == "on"
    assert rec["source"] == "bus"
