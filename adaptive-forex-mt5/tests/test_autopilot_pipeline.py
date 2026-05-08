"""Phase-2 pipeline: evaluate_pending_consensus journals consensus_verdict
AND, when autopilot.enabled+consensus=take, calls autopilot.attempt_autopilot_place
with the ORIGINAL ready_alert (looked up by alert_id) — NOT a fresh sniper_poc."""
from __future__ import annotations

import json
from unittest.mock import patch

import agent
import journal
import state_db


FP = "deadbeef"
AID = "2026-05-08T16:00:00.000000+00:00-USDJPY"


def _seed_pipeline(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    # Original ready_alert with alert_id
    journal.append({
        "kind": "ready_alert", "pair": "USDJPY", "direction": "buy",
        "alert_id": AID, "setup_fingerprint": FP,
        "entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5,
    })
    # Two reviewer verdicts both take
    for model, conf in [("claude", 0.84), ("codex", 0.79)]:
        journal.append({
            "kind": "llm_verdict", "pair": "USDJPY",
            "alert_id": AID, "decision": "take", "direction": "buy",
            "confidence": conf, "accepted_levels": True,
            "reviewed_fingerprint": FP, "model": model,
        })
    return db, log


def _cfg(*, enabled=True):
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc", "review_enabled": True},
        "manager": {"max_spread_points": 100},
        "autopilot": {
            "enabled": enabled,
            "min_confidence": 0.75,
            "pair_allowlist": ["USDJPY"],
            "max_alert_age_seconds": 31536000,  # 1 year — don't fail on test fixture
            "max_entry_drift_points": 30,
            "lot_size": 0.001,
            "daily_trade_cap": 5,
            "daily_loss_cap_usd": 5.00,
            "news_source": "t",
        },
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_pipeline_journals_consensus_then_calls_executor(tmp_path, monkeypatch):
    db, log = _seed_pipeline(tmp_path, monkeypatch)
    cfg = _cfg(enabled=True)
    with patch("agent.autopilot") as mock_ap:
        mock_ap.attempt_autopilot_place.return_value = None
        agent.evaluate_pending_consensus(cfg, db)
    # consensus_verdict was journaled
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    cv = [r for r in rows if r["kind"] == "consensus_verdict"]
    assert len(cv) == 1 and cv[0]["consensus"] == "take"
    # autopilot.attempt_autopilot_place was called with the original alert
    assert mock_ap.attempt_autopilot_place.called
    args = mock_ap.attempt_autopilot_place.call_args.args
    passed_alert = args[2]
    assert passed_alert["alert_id"] == AID
    assert passed_alert["setup_fingerprint"] == FP
    # The original alert.setup is what gets passed (not a re-evaluated one)
    assert passed_alert["setup"]["entry"] == 156.50
    assert passed_alert["setup"]["sl"] == 156.30
    assert passed_alert["setup"]["tp"] == 157.00


def test_pipeline_skips_executor_when_autopilot_disabled(tmp_path, monkeypatch):
    db, log = _seed_pipeline(tmp_path, monkeypatch)
    cfg = _cfg(enabled=False)
    with patch("agent.autopilot") as mock_ap:
        agent.evaluate_pending_consensus(cfg, db)
    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert any(r["kind"] == "consensus_verdict" for r in rows)  # still journaled (shadow)
    assert not mock_ap.attempt_autopilot_place.called  # but executor not invoked


def test_pipeline_skips_executor_when_consensus_not_take(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "ready_alert", "pair": "USDJPY", "direction": "buy",
                    "alert_id": AID, "setup_fingerprint": FP,
                    "entry": 156.50, "sl": 156.30, "tp": 157.00})
    # Disagreement → no_consensus
    journal.append({"kind": "llm_verdict", "alert_id": AID, "decision": "take",
                    "direction": "buy", "confidence": 0.84,
                    "accepted_levels": True, "reviewed_fingerprint": FP, "model": "claude"})
    journal.append({"kind": "llm_verdict", "alert_id": AID, "decision": "skip",
                    "direction": "buy", "confidence": 0.50,
                    "accepted_levels": False, "reviewed_fingerprint": FP, "model": "codex"})
    cfg = _cfg(enabled=True)
    with patch("agent.autopilot") as mock_ap:
        agent.evaluate_pending_consensus(cfg, db)
    assert not mock_ap.attempt_autopilot_place.called
