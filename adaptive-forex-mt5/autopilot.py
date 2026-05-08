"""Autopilot executor — gated 12-step pipeline that places trades when the
2-of-2 reviewer consensus says `take` and every safety gate passes.

This module starts with the kill-switch + bus-abort listener; the 12-gate
`attempt_autopilot_place` is added in plan §Task 9.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import journal
import state_db


# ehukaiconnect read output line shape: "HH:MM:SS AM/PM <from> → <to>: <text>"
_BUS_LINE_RE = re.compile(
    r"^\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)\s+(?P<sender>\S+)\s+→\s+(?P<recipient>\S+):\s+(?P<text>.*)$"
)
_ABORT_TOKEN = "AUTOPILOT ABORT"


def _resolve_ehukaiconnect() -> str:
    """Same fallback as dispatch.py — handle PATH not having ehukaiconnect."""
    found = shutil.which("ehukaiconnect")
    if found:
        return found
    home = Path.home()
    win = home / ".ehukaiconnect" / "bin" / "ehukaiconnect.cmd"
    nix = home / ".ehukaiconnect" / "bin" / "ehukaiconnect"
    if win.exists():
        return str(win)
    if nix.exists():
        return str(nix)
    return "ehukaiconnect"


_EHUKAICONNECT = _resolve_ehukaiconnect()


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


def poll_bus_for_abort(db_path: Path, *, lookback: int = 20,
                       timeout_seconds: float = 30) -> bool:
    """Read the last `lookback` bus messages, scan for `AUTOPILOT ABORT`
    sent by the operator, and flip the kill-switch on if found.

    Returns True iff the kill-switch was flipped (i.e. an abort message was
    found AND the switch wasn't already on). The flip itself is idempotent
    via kill_switch_set, so repeated abort messages while already-on are
    no-ops in terms of journal events.
    """
    cmd = [_EHUKAICONNECT, "read", str(int(lookback))]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return False
    if res.returncode != 0:
        return False
    found_abort = False
    for line in (res.stdout or "").splitlines():
        m = _BUS_LINE_RE.match(line.strip())
        if not m:
            continue
        if m.group("sender") != "operator":
            continue
        if _ABORT_TOKEN in m.group("text"):
            found_abort = True
            break  # one match is enough
    if not found_abort:
        return False
    if kill_switch_get(db_path) == "on":
        return False  # already on, no flip
    kill_switch_set(db_path, "on", source="bus")
    return True
