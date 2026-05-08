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


def test_log_autopilot_placement_writes_kind_placement_with_autopilot_flag(tmp_path, monkeypatch):
    """Phase-2 audit fix: autopilot placements must be kind=placement so
    the existing trade lifecycle (manager bootstrap, resolve_outcomes,
    folded_trades) consumes them natively. The autopilot=true flag plus
    consensus_alert_id let the dashboard split them out."""
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    alert = {
        "alert_id": "abc",
        "direction": "buy",
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
        "reasoning": {"structure": {"last_confirmed_event": {"type": "BOS"}}},
    }
    journal.log_autopilot_placement(
        pair="USDJPY",
        alert=alert,
        placement={"data": {"placement": {"ticket": 99, "magic": 128461,
                                          "volume": 0.001}}},
        consensus_alert_id="abc",
        reviewer_confidences=[0.84, 0.79],
        strategy_id="ehukai-poc-USDJPY",
    )
    rec = json.loads(log.read_text().splitlines()[0])
    # CRITICAL: kind=placement so the lifecycle picks it up
    assert rec["kind"] == "placement"
    assert rec["autopilot"] is True
    # Full setup fields needed for bootstrap + R analysis
    assert rec["pair"] == "USDJPY"
    assert rec["ticket"] == 99
    assert rec["magic"] == 128461
    assert rec["direction"] == "buy"
    assert rec["entry"] == 156.50
    assert rec["sl"] == 156.30
    assert rec["tp"] == 157.00
    assert rec["rr"] == 2.5
    assert rec["volume"] == 0.001
    assert rec["strategy_id"] == "ehukai-poc-USDJPY"
    assert rec["reasoning"] is not None
    # Audit-trail fields preserved
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
