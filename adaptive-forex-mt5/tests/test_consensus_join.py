"""Phase-2 consensus join: agent.evaluate_pending_consensus joins llm_verdict
records by alert_id, computes consensus, journals consensus_verdict, advances
cursor. Dedupe by alert_id."""
from __future__ import annotations

import json
from unittest.mock import patch

import agent
import journal
import state_db


FP = "deadbeef"


def _verdict(*, alert_id, model, decision="take", direction="buy",
             confidence=0.84, accepted_levels=True, fingerprint=FP):
    return {
        "kind": "llm_verdict",
        "pair": alert_id.rsplit("-", 1)[-1],
        "alert_id": alert_id,
        "decision": decision,
        "direction": direction,
        "confidence": confidence,
        "accepted_levels": accepted_levels,
        "reviewed_fingerprint": fingerprint,
        "model": model,
    }


def test_consensus_evaluator_joins_two_verdicts(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    # Stamp the alert (with alert_id + setup_fingerprint) and two verdicts
    aid = "2026-05-08T16:00:00-USDJPY"
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid, "setup_fingerprint": FP,
                    "direction": "buy"})
    journal.append(_verdict(alert_id=aid, model="claude"))
    journal.append(_verdict(alert_id=aid, model="codex", confidence=0.79))

    cfg = {"autopilot": {"min_confidence": 0.75}}
    count = agent.evaluate_pending_consensus(cfg, db)
    assert count == 1

    # Last journal record is the consensus_verdict
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    consensus_records = [r for r in records if r["kind"] == "consensus_verdict"]
    assert len(consensus_records) == 1
    cv = consensus_records[0]
    assert cv["alert_id"] == aid
    assert cv["consensus"] == "take"
    assert cv["setup_fingerprint"] == FP
    assert sorted(cv["reviewers"]) == ["claude", "codex"]


def test_consensus_evaluator_dedupes_via_cursor(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    aid = "2026-05-08T16:00:00-USDJPY"
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid, "setup_fingerprint": FP,
                    "direction": "buy"})
    journal.append(_verdict(alert_id=aid, model="claude"))
    journal.append(_verdict(alert_id=aid, model="codex"))

    cfg = {"autopilot": {"min_confidence": 0.75}}
    count1 = agent.evaluate_pending_consensus(cfg, db)
    count2 = agent.evaluate_pending_consensus(cfg, db)
    assert count1 == 1
    assert count2 == 0  # already processed


def test_consensus_evaluator_skips_unpaired_verdicts(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    # Only ONE verdict (claude) — codex hasn't returned yet
    aid = "2026-05-08T16:00:00-USDJPY"
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid, "setup_fingerprint": FP,
                    "direction": "buy"})
    journal.append(_verdict(alert_id=aid, model="claude"))

    cfg = {"autopilot": {"min_confidence": 0.75}}
    count = agent.evaluate_pending_consensus(cfg, db)
    assert count == 0
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    assert not any(r["kind"] == "consensus_verdict" for r in records)


def test_two_readys_same_pair_join_to_correct_alert(tmp_path, monkeypatch):
    """Codex1 blocker #2 regression: two READYs on USDJPY with DIFFERENT
    fingerprints. Verdicts for the second alert must join to the second
    alert's fingerprint, not the first's."""
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    aid1 = "2026-05-08T16:00:00-USDJPY"
    aid2 = "2026-05-08T16:30:00-USDJPY"
    fp1 = "aaaa1111"
    fp2 = "bbbb2222"
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid1, "setup_fingerprint": fp1, "direction": "buy"})
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid2, "setup_fingerprint": fp2, "direction": "buy"})
    # Both verdicts for the SECOND alert use fp2
    journal.append(_verdict(alert_id=aid2, model="claude", fingerprint=fp2))
    journal.append(_verdict(alert_id=aid2, model="codex", fingerprint=fp2,
                            confidence=0.80))
    cfg = {"autopilot": {"min_confidence": 0.75}}
    agent.evaluate_pending_consensus(cfg, db)
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    cv = [r for r in records if r["kind"] == "consensus_verdict"]
    assert len(cv) == 1
    assert cv[0]["alert_id"] == aid2
    assert cv[0]["setup_fingerprint"] == fp2
    assert cv[0]["consensus"] == "take"  # fp matches → take


def test_consensus_evaluator_records_no_consensus_for_disagreement(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    aid = "2026-05-08T16:00:00-USDJPY"
    journal.append({"kind": "ready_alert", "pair": "USDJPY",
                    "alert_id": aid, "setup_fingerprint": FP,
                    "direction": "buy"})
    journal.append(_verdict(alert_id=aid, model="claude", decision="take"))
    journal.append(_verdict(alert_id=aid, model="codex", decision="skip",
                            accepted_levels=False))

    cfg = {"autopilot": {"min_confidence": 0.75}}
    agent.evaluate_pending_consensus(cfg, db)
    records = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    cv = [r for r in records if r["kind"] == "consensus_verdict"][0]
    assert cv["consensus"] == "no_consensus"
    assert "one_skipped" in cv["consensus_reason"]
