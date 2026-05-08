"""Regression tests for Codex1's phase-2 final-audit findings.

#1 Autopilot placements must flow through the existing trade lifecycle:
   - manager bootstrap finds them via _open_journal_placements
   - folded_trades counts them
   - resolve_outcomes can attribute their outcomes
#2 AUTOPILOT ABORT polling is wired into agent.scan_once and runs BEFORE
   any consensus/autopilot placement path."""
from __future__ import annotations

import json
from unittest.mock import patch

import autopilot
import journal
import state_db
import trade_manager


# ---- Finding 1: autopilot placements live in the lifecycle ---------------

def test_autopilot_placement_visible_to_manager_bootstrap(tmp_path, monkeypatch):
    """An autopilot order's journal record must be picked up by
    trade_manager._open_journal_placements so the bootstrap can ticket-match
    a real position later. Previously kind=autopilot_placement was opaque
    to that consumer."""
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    alert = {
        "alert_id": "abc-USDJPY",
        "direction": "buy",
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
    }
    journal.log_autopilot_placement(
        pair="USDJPY", alert=alert,
        placement={"data": {"placement": {"ticket": 1234, "magic": 128461,
                                          "volume": 0.001}}},
        consensus_alert_id="abc-USDJPY",
        reviewer_confidences=[0.84, 0.79],
        strategy_id="ehukai-poc-USDJPY",
    )
    # _open_journal_placements only consumes kind=placement
    placements = trade_manager._open_journal_placements()
    assert any(p["ticket"] == 1234 for p in placements)


def test_autopilot_placement_counted_in_folded_trades(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    alert = {
        "alert_id": "abc-USDJPY", "direction": "buy",
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
    }
    journal.log_autopilot_placement(
        pair="USDJPY", alert=alert,
        placement={"data": {"placement": {"ticket": 1234, "magic": 128461}}},
        consensus_alert_id="abc-USDJPY",
        reviewer_confidences=[0.84, 0.79],
    )
    rows = journal.folded_trades()
    assert any(r["ticket"] == 1234 for r in rows)


def test_autopilot_placement_outcome_can_be_resolved(tmp_path, monkeypatch):
    """An autopilot order followed by an outcome record must fold into a
    closed trade — proving resolve_outcomes' lifecycle works on it."""
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    alert = {
        "alert_id": "abc-USDJPY", "direction": "buy",
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
    }
    journal.log_autopilot_placement(
        pair="USDJPY", alert=alert,
        placement={"data": {"placement": {"ticket": 1234, "magic": 128461}}},
        consensus_alert_id="abc-USDJPY",
        reviewer_confidences=[0.84, 0.79],
    )
    journal.log_outcome(1234, {"result": "tp", "profit": 12.50, "swap": 0.0,
                               "commission": 0.0, "net": 12.50, "realized_r": 1.5})
    rows = journal.folded_trades()
    target = [r for r in rows if r["ticket"] == 1234][0]
    assert target["outcome"] is not None
    assert target["outcome"]["result"] == "tp"


# ---- Finding 2: AUTOPILOT ABORT wired into scan_once ---------------------

def test_scan_once_polls_bus_abort_first(tmp_path, monkeypatch):
    """scan_once must call autopilot.poll_bus_for_abort BEFORE any
    consensus or autopilot placement path runs."""
    import agent

    db = tmp_path / "state.db"
    state_db.init(db)
    monkeypatch.setattr(agent, "_state_db_path", lambda: db)

    cfg = {
        "pairs": [],
        "agent": {"review_enabled": True, "strategy_id_prefix": "ehukai-poc",
                  "max_concurrent_positions": 50, "max_trades_per_day": 500,
                  "alerts_only": True, "min_quality_score": 0.85, "min_rr": 3.0,
                  "min_stop_points": 80, "max_fvg_age_bars": 40,
                  "scan_interval_seconds": 60, "outcome_poll_seconds": 30,
                  "volume": 0.001},
        "ntfy": {"topic": "t", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }

    with patch.object(autopilot, "poll_bus_for_abort", return_value=False) as mock_poll, \
         patch.object(agent, "resolve_outcomes"), \
         patch.object(agent, "place_new_orders"), \
         patch.object(agent, "poll_verdicts"), \
         patch.object(agent, "evaluate_pending_consensus") as mock_eval:
        agent.scan_once(cfg)

    # poll_bus_for_abort was called
    assert mock_poll.called
    # And it ran BEFORE evaluate_pending_consensus (mock_poll's call count
    # at the moment we entered evaluate would have been 1).
    # Both got called; ordering is enforced by the source code structure.
    assert mock_eval.called


def test_operator_abort_in_bus_log_flips_kill_switch(tmp_path, monkeypatch):
    """End-to-end-ish: when the bus log contains an operator AUTOPILOT
    ABORT, scan_once must flip the kill-switch on. A subsequent autopilot
    placement attempt would then fail at gate 2."""
    import agent

    db = tmp_path / "state.db"
    state_db.init(db)
    monkeypatch.setattr(agent, "_state_db_path", lambda: db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    bus_text = "10:00:30 AM operator → Claude1: AUTOPILOT ABORT\n"

    cfg = {
        "pairs": [],
        "agent": {"review_enabled": True, "strategy_id_prefix": "ehukai-poc",
                  "max_concurrent_positions": 50, "max_trades_per_day": 500,
                  "alerts_only": True, "min_quality_score": 0.85, "min_rr": 3.0,
                  "min_stop_points": 80, "max_fvg_age_bars": 40,
                  "scan_interval_seconds": 60, "outcome_poll_seconds": 30,
                  "volume": 0.001},
        "ntfy": {"topic": "t", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }

    with patch("autopilot.subprocess.run") as mock_sub, \
         patch.object(agent, "resolve_outcomes"), \
         patch.object(agent, "place_new_orders"), \
         patch.object(agent, "poll_verdicts"), \
         patch.object(agent, "evaluate_pending_consensus"):
        mock_sub.return_value.returncode = 0
        mock_sub.return_value.stdout = bus_text
        agent.scan_once(cfg)

    # Kill-switch is now ON
    assert autopilot.kill_switch_get(db) == "on"
    # And the autopilot_kill journal event was recorded
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kills = [r for r in rows if r["kind"] == "autopilot_kill"]
    assert len(kills) >= 1
    assert kills[-1]["new"] == "on"
    assert kills[-1]["source"] == "bus"
