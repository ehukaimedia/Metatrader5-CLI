"""Unit tests for dispatch wrapper. Real ehukaiconnect calls are mocked."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dispatch


def test_alert_payload_path_is_alert_id_keyed(tmp_path):
    payload = {"alert_id": "2026-05-08T16:37:15Z-USDJPY", "pair": "USDJPY"}
    path = dispatch.alert_payload_path(tmp_path, payload["alert_id"])
    # Colons in the timestamp get sanitized to underscores
    assert path.parent == tmp_path
    assert path.name.endswith("USDJPY.json")


def test_write_alert_payload_creates_file(tmp_path):
    payload = {"alert_id": "abc", "pair": "USDJPY", "direction": "buy"}
    path = dispatch.write_alert_payload(tmp_path, payload)
    assert path.exists()
    assert json.loads(path.read_text()) == payload


def test_create_review_task_calls_ehukaiconnect(tmp_path):
    payload = {"alert_id": "abc", "pair": "USDJPY", "setup_fingerprint": "deadbeef"}
    fake = MagicMock(returncode=0, stdout="Task created: task-12345abc — title\n", stderr="")
    with patch("dispatch.subprocess.run", return_value=fake) as run:
        task_id = dispatch.create_review_task(
            payload, alerts_dir=tmp_path, reviewer="ClaudeReviewer"
        )
    assert task_id is not None and len(task_id) >= 4
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] == "ehukaiconnect"
    assert cmd[1] == "task" and cmd[2] == "create"
    # The CLI doesn't expose --type, so we discriminate by title prefix.
    assert "--title" in cmd
    title = cmd[cmd.index("--title") + 1]
    assert title.startswith("trade_review-")
    assert "--assignee" in cmd and "ClaudeReviewer" in cmd
    assert "--description" in cmd
    desc_idx = cmd.index("--description") + 1
    assert cmd[desc_idx].endswith("abc.json")


def test_create_review_task_returns_none_on_failure(tmp_path):
    payload = {"alert_id": "abc", "pair": "USDJPY"}
    fake = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch("dispatch.subprocess.run", return_value=fake):
        assert dispatch.create_review_task(
            payload, alerts_dir=tmp_path, reviewer="ClaudeReviewer"
        ) is None


def test_list_done_review_tasks_parses_output(tmp_path):
    out = json.dumps({
        "ok": True,
        "tasks": [
            {"id": "t-1", "title": "trade_review-USDJPY-abc", "status": "done",
             "description": str(tmp_path / "verdicts" / "abc.json"),
             "updated_at": 1778263496.2666745},
            {"id": "t-2", "title": "trade_review-EURUSD-def", "status": "done",
             "description": str(tmp_path / "verdicts" / "def.json"),
             "updated_at": 1778263995.0},
            # Non-review task should be filtered out
            {"id": "t-3", "title": "test-probe", "status": "done",
             "description": "", "updated_at": 1778263000.0},
        ],
    })
    fake = MagicMock(returncode=0, stdout=out)
    with patch("dispatch.subprocess.run", return_value=fake):
        tasks = dispatch.list_done_review_tasks(since=None)
    assert len(tasks) == 2
    titles = {t["title"] for t in tasks}
    assert all(t.startswith("trade_review-") for t in titles)
