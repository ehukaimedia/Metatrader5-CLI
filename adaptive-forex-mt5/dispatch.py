"""Wrap ehukaiconnect task and shared-file payload calls used by the agent."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path


_DEFAULT_TIMEOUT_SECONDS = 30


def _resolve_ehukaiconnect() -> str:
    """Resolve the ehukaiconnect command, falling back to the well-known
    Windows install path if PATH lookup fails.

    `shutil.which` honours PATH; if that fails, this falls back to
    `~/.ehukaiconnect/bin/ehukaiconnect.cmd` on Windows or
    `~/.ehukaiconnect/bin/ehukaiconnect` elsewhere.
    """
    found = shutil.which("ehukaiconnect")
    if found:
        return found
    home = Path.home()
    win = home / ".ehukaiconnect" / "bin" / "ehukaiconnect.cmd"
    nix = home / ".ehukaiconnect" / "bin" / "ehukaiconnect"
    if os.name == "nt" and win.exists():
        return str(win)
    if nix.exists():
        return str(nix)
    return "ehukaiconnect"  # last-resort; subprocess will surface the error


_EHUKAICONNECT = _resolve_ehukaiconnect()


def _shared_root() -> Path:
    """Resolve the workspace's shared-files root.

    The adaptive-forex-mt5 module sits two directories deep from the repo
    root, so walk up one level to find .ehukaiconnect/.
    """
    here = Path(__file__).resolve()
    return here.parent.parent / ".ehukaiconnect" / "shared" / "files"


def alerts_dir_default() -> Path:
    return _shared_root() / "alerts"


def verdicts_dir_default() -> Path:
    return _shared_root() / "verdicts"


def alert_payload_path(alerts_dir: Path, alert_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.+-]", "_", alert_id)
    return alerts_dir / f"{safe}.json"


def write_alert_payload(alerts_dir: Path, payload: dict) -> Path:
    alerts_dir.mkdir(parents=True, exist_ok=True)
    path = alert_payload_path(alerts_dir, payload["alert_id"])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


# ehukaiconnect's `task create` prints an 8-char hex id, e.g.:
#   "Task created: 270b8ceb — title"
_TASK_ID_RE = re.compile(r"Task created:\s+([A-Za-z0-9_-]+)")


def create_review_task(payload: dict, *, alerts_dir: Path, reviewer: str,
                       priority: str = "high",
                       timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Write the alert payload to shared files, create an ehukaiconnect task,
    and return the parsed task id (None on failure or timeout)."""
    path = write_alert_payload(alerts_dir, payload)
    cmd = [
        _EHUKAICONNECT, "task", "create",
        "--title", f"trade_review-{payload.get('pair','?')}-{payload['alert_id']}"[:80],
        "--assignee", reviewer,
        "--priority", priority,
        "--description", str(path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    m = _TASK_ID_RE.search(res.stdout or "")
    return m.group(1) if m else None


_REVIEW_TITLE_PREFIX = "trade_review-"


def list_done_review_tasks(since: str | None,
                           timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> list[dict]:
    """List done tasks whose title starts with `trade_review-`.

    The ehukaiconnect CLI doesn't expose a --type flag so we discriminate
    by title prefix in Python. `since` filters by `updated_at` (unix ts).
    """
    cmd = [_EHUKAICONNECT, "task", "list", "--status", "done", "--json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return []
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    review_tasks = [
        t for t in tasks if (t.get("title") or "").startswith(_REVIEW_TITLE_PREFIX)
    ]
    if since:
        try:
            since_ts = float(since)
            review_tasks = [
                t for t in review_tasks
                if float(t.get("updated_at") or 0) > since_ts
            ]
        except (TypeError, ValueError):
            pass
    return review_tasks
