"""Verify agent.poll_verdicts journals + ntfy-pushes closed reviews."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import agent


def _cfg():
    return {
        "agent": {"reviewer_agent": "ClaudeReviewer"},
        "ntfy": {"topic": "test", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_poll_verdicts_journals_and_advances_cursor(tmp_path):
    verdict_path = tmp_path / "verdicts" / "abc-claude.json"
    verdict_path.parent.mkdir(parents=True)
    verdict_path.write_text(json.dumps({
        "alert_id": "2026-05-08T16:00:00-USDJPY",
        "decision": "take",
        "confidence": 0.84,
        "reviewed_fingerprint": "deadbeef",
        "reasoning_summary": "clean BOS, M1 trap absent",
    }))
    db_path = tmp_path / "state.db"
    with patch("agent.dispatch") as mock_dispatch, \
         patch("agent.alerts") as mock_alerts, \
         patch("agent.journal") as mock_journal, \
         patch("agent.state_db") as mock_state:
        mock_state.cursor_get.return_value = None
        mock_dispatch.list_done_review_tasks.return_value = [{
            "id": "t-1",
            "title": "trade_review-USDJPY-abc",
            "status": "done",
            "description": str(verdict_path),
            "updated_at": 1778263496.27,
        }]
        agent.poll_verdicts(_cfg(), db_path)
    mock_journal.log_llm_verdict.assert_called_once()
    args = mock_journal.log_llm_verdict.call_args.args
    assert args[0] == "USDJPY"
    assert args[1]["alert_id"] == "2026-05-08T16:00:00-USDJPY"
    mock_alerts.push.assert_called_once()
    mock_state.cursor_set.assert_called_once()
    set_args = mock_state.cursor_set.call_args.args
    assert set_args[1] == "last_verdict_seen"
    assert set_args[2] == "1778263496.27"


def test_poll_verdicts_handles_unreadable_file(tmp_path):
    db_path = tmp_path / "state.db"
    with patch("agent.dispatch") as mock_dispatch, \
         patch("agent.alerts") as _mock_alerts, \
         patch("agent.journal") as mock_journal, \
         patch("agent.state_db") as mock_state:
        mock_state.cursor_get.return_value = None
        mock_dispatch.list_done_review_tasks.return_value = [{
            "id": "t-1",
            "title": "trade_review-USDJPY-abc",
            "status": "done",
            "description": str(tmp_path / "missing.json"),
            "updated_at": 1778263496.27,
        }]
        agent.poll_verdicts(_cfg(), db_path)
    mock_journal.log_error.assert_called()
    mock_journal.log_llm_verdict.assert_not_called()


def test_poll_verdicts_no_tasks(tmp_path):
    db_path = tmp_path / "state.db"
    with patch("agent.dispatch") as mock_dispatch, \
         patch("agent.state_db") as mock_state:
        mock_state.cursor_get.return_value = "1778000000"
        mock_dispatch.list_done_review_tasks.return_value = []
        count = agent.poll_verdicts(_cfg(), db_path)
    assert count == 0
    mock_state.cursor_set.assert_not_called()
