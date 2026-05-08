"""Manual-trade adoption allowlist (phase 3).

The operator declares specific manual MT5 tickets the bot should manage in
`adaptive-forex-mt5/managed_positions.json`. This module is the only path
by which the trade manager touches a position whose magic is NOT in the
poc-set — every other path falls under the phase-1 invariant
`Magic=0 stays untouched`.

Schema (per spec § Phase 3):

```json
[
  {
    "ticket":         204841232,
    "symbol":         "GBPJPY",
    "account":        9999,
    "mode":           "trail_only" | "be_and_trail",
    "expires_at":     "2026-05-15T00:00:00Z",
    "operator_note":  "GBPJPY manual long, hand to bot for trail"
  }
]
```

Missing file is the safe default — `load()` returns `[]` and no adoptions
happen. Expired entries (`expires_at` in the past) are filtered out
automatically. Malformed JSON is silently dropped to `[]` (operator can
fix and retry; we log an error elsewhere).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


_REQUIRED_FIELDS = {"ticket", "symbol", "account", "mode", "expires_at", "operator_note"}


def default_path() -> Path:
    return Path(__file__).resolve().parent / "managed_positions.json"


def _is_expired(entry: dict) -> bool:
    raw = entry.get("expires_at")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return True  # malformed expiry → treat as expired (fail closed)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= datetime.now(timezone.utc)


def _is_valid(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return _REQUIRED_FIELDS.issubset(entry.keys())


def load(path: Path | None = None) -> list[dict]:
    """Load + validate + expiry-filter the allowlist. Returns the list of
    currently-active adoption entries (may be empty)."""
    p = path or default_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [e for e in raw if _is_valid(e) and not _is_expired(e)]


def adopted_tickets(path: Path | None = None) -> set[int]:
    """Convenience: tickets currently authorized for adoption."""
    return {int(e["ticket"]) for e in load(path) if "ticket" in e}


def lookup(path: Path | None = None, ticket: int | None = None) -> dict | None:
    if ticket is None:
        return None
    for e in load(path):
        if int(e.get("ticket") or 0) == int(ticket):
            return e
    return None
