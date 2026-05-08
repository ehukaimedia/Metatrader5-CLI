"""Autopilot executor — gated 12-step pipeline that places trades when the
2-of-2 reviewer consensus says `take` and every safety gate passes.

This module starts with the kill-switch helpers; the 12-gate
`attempt_autopilot_place` is added in plan §Task 9.
"""
from __future__ import annotations

from pathlib import Path

import journal
import state_db


_KILL_CURSOR = "autopilot_kill"


def kill_switch_get(db_path: Path) -> str:
    """Return 'on' or 'off' (default 'off' for fresh DBs)."""
    val = state_db.cursor_get(db_path, _KILL_CURSOR)
    return val if val == "on" else "off"


def kill_switch_set(db_path: Path, new_state: str, *, source: str) -> None:
    """Flip the kill-switch and journal the change.

    Idempotent: a second set to the same state does NOT emit a duplicate
    `autopilot_kill` event. `source` should be 'bus' or 'dashboard'.
    """
    if new_state not in {"on", "off"}:
        raise ValueError(f"kill_switch state must be 'on' or 'off', got {new_state!r}")
    prev = kill_switch_get(db_path)
    if prev == new_state:
        return
    state_db.cursor_set(db_path, _KILL_CURSOR, new_state)
    journal.log_autopilot_kill(prev=prev, new=new_state, source=source)
