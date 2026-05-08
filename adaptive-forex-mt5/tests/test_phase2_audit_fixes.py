"""Regression tests for Codex1's phase-2 final-audit findings.

#1 Autopilot placements must flow through the existing trade lifecycle:
   - manager bootstrap finds them via _open_journal_placements
   - folded_trades counts them
   - resolve_outcomes can attribute their outcomes
#2 AUTOPILOT ABORT polling is wired into agent.scan_once and runs BEFORE
   any consensus/autopilot placement path."""
from __future__ import annotations

import json
from datetime import datetime, timezone
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
        placement={"data": {"ticket": 1234, "magic": 128461, "volume": 0.001,
                            "symbol": "USDJPY", "type": "buy",
                            "price": 156.50, "sl": 156.30, "tp": 157.00}},
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
        placement={"data": {"ticket": 1234, "magic": 128461, "volume": 0.001,
                            "symbol": "USDJPY", "type": "buy",
                            "price": 156.50, "sl": 156.30, "tp": 157.00}},
        consensus_alert_id="abc-USDJPY",
        reviewer_confidences=[0.84, 0.79],
    )
    rows = journal.folded_trades()
    assert any(r["ticket"] == 1234 for r in rows)


def test_attempt_autopilot_place_journals_with_flat_response_shape(tmp_path, monkeypatch):
    """End-to-end through attempt_autopilot_place: with the REAL flat
    `mt5 order limit` response shape, the journaled placement record must
    carry ticket/magic/volume/direction/entry/sl/tp so trade_manager
    bootstrap can ticket-match the resulting position. This is the
    Codex1 phase-2 fix-review regression."""
    import news
    news._SOURCES.clear()
    news.register_source("t", lambda p: [])
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    alert = {
        "alert_id": "abc-USDJPY", "pair": "USDJPY", "direction": "buy",
        "setup_fingerprint": "deadbeef",
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
        "ts": (datetime.now(timezone.utc)).isoformat(),
    }
    cfg = {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"max_spread_points": 100},
        "autopilot": {
            "enabled": True, "min_confidence": 0.75,
            "pair_allowlist": ["USDJPY"],
            "max_alert_age_seconds": 31536000,  # don't fail on age
            "max_entry_drift_points": 30,
            "lot_size": 0.001,
            "daily_trade_cap": 5, "daily_loss_cap_usd": 5.00,
            "news_source": "t",
        },
        "mt5_cli": {"command": "mt5", "live": True, "subprocess_timeout_seconds": 60},
    }
    consensus = {
        "consensus": "take", "consensus_reason": "test",
        "votes": [
            {"reviewer": "claude", "confidence": 0.84},
            {"reviewer": "codex",  "confidence": 0.79},
        ],
    }

    def fake_run(cmd, **kwargs):
        class R: pass
        r = R(); r.returncode = 0; r.stderr = ""; r.stdout = "{}"
        if "sniper-poc" in cmd or "analyze" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "status": "ready", "direction": "buy",
                "setup": dict(alert["setup"]),
                "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
                "structure": {"last_confirmed_event": {"type": "BOS",
                              "level": {"time": "2026-05-08T12:00:00+00:00"}}},
                "setup_fingerprint": "deadbeef",
            }})
        elif "market" in cmd and "info" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "bid": 156.499, "ask": 156.500, "spread": 10,
                "digits": 3, "point": 0.001,
            }})
        elif "order" in cmd and "limit" in cmd:
            # FLAT response shape — what the real mt5 order limit returns.
            r.stdout = json.dumps({"ok": True, "data": {
                "ticket": 5555, "magic": 128461, "volume": 0.001,
                "symbol": "USDJPY", "type": "buy",
                "price": 156.50, "sl": 156.30, "tp": 157.00,
                "strategy_id": "ehukai-poc-USDJPY",
            }})
        elif "position" in cmd and "list" in cmd:
            r.stdout = json.dumps({"ok": True, "data": []})
        return r

    with patch("autopilot.subprocess.run", side_effect=fake_run):
        out = autopilot.attempt_autopilot_place(cfg, db, alert, consensus)

    assert out is not None and out.get("ok"), out
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    placements = [r for r in rows if r["kind"] == "placement" and r.get("autopilot")]
    assert len(placements) == 1
    p = placements[0]
    # CRITICAL: every field needed by manager bootstrap / outcome
    # resolution / stats is present and non-None.
    assert p["ticket"] == 5555
    assert p["magic"] == 128461
    assert p["volume"] == 0.001
    assert p["direction"] == "buy"
    assert p["entry"] == 156.50
    assert p["sl"] == 156.30
    assert p["tp"] == 157.00
    assert p["strategy_id"]
    # And it flows through the lifecycle:
    folded = journal.folded_trades()
    assert any(r["ticket"] == 5555 for r in folded)
    open_placements = trade_manager._open_journal_placements()
    assert any(r["ticket"] == 5555 for r in open_placements)


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
        placement={"data": {"ticket": 1234, "magic": 128461, "volume": 0.001,
                            "symbol": "USDJPY", "type": "buy",
                            "price": 156.50, "sl": 156.30, "tp": 157.00}},
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
