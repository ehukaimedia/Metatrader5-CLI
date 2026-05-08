# Trade Manager + LLM Review Pipeline (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AdaptiveTrailEA for our magics with a Python `trade_manager.py` process and add a dispatcher-driven advisory LLM review pipeline that emits enriched verdicts on every `ready_alert`.

**Architecture:** New `trade_manager.py` runs as a sibling process to `agent.py` and `dashboard.py`. Mutable runtime state lives in `adaptive-forex-mt5/state.db` (SQLite, WAL mode). `trades.jsonl` stays append-only audit. Bootstrap from MT5 positions + journal placements, fail-closed on ambiguity, confirm-before-promote on every modify call, reuse `cfg.mt5_cli.live` as the live-intent gate. The review pipeline registers a `ClaudeReviewer` agent via `ehukaiconnect agent create`; on each READY, `agent.py` writes the alert payload to `.ehukaiconnect/shared/files/alerts/<id>.json`, dispatches a `trade_review` task, and polls for closure.

**Tech Stack:** Python 3.13, sqlite3 (stdlib), pytest 7+, ehukaiconnect CLI, MT5 CLI, ntfy.

**Spec reference:** `docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md` (commit 1e1786f).

---

## File Structure

**New files:**

| Path | Responsibility |
|---|---|
| `adaptive-forex-mt5/state_db.py` | SQLite layer: connect/init/upsert/query for managed_position, cursor, heartbeat. WAL mode. |
| `adaptive-forex-mt5/fingerprint.py` | Compute `setup_fingerprint` from a sniper-poc payload. Pure function, no I/O. |
| `adaptive-forex-mt5/trade_manager.py` | Separate process: bootstrap + management loop (BE → Chandelier) with confirm-before-promote modify. |
| `adaptive-forex-mt5/dispatch.py` | Wraps `ehukaiconnect task create / list` calls and shared-file payload writes. |
| `adaptive-forex-mt5/tests/__init__.py` | Empty marker. |
| `adaptive-forex-mt5/tests/conftest.py` | Pytest fixtures: tmp `state.db`, fake config, fake placement records. |
| `adaptive-forex-mt5/tests/test_state_db.py` | Unit tests for state_db module. |
| `adaptive-forex-mt5/tests/test_fingerprint.py` | Unit tests for fingerprint stability + collision behavior. |
| `adaptive-forex-mt5/tests/test_journal_kinds.py` | Unit tests for new journal kinds. |
| `adaptive-forex-mt5/tests/test_trade_manager.py` | Unit tests for manager: bootstrap, BE math, Chandelier math, modify state machine. |
| `adaptive-forex-mt5/tests/test_dispatch.py` | Unit tests for dispatch wrapper (mocked subprocess). |
| `.ehukaiconnect/skills/ClaudeReviewer/SKILL.md` | Reviewer agent skill: verdict schema, tool list, output path. |

**Modified files:**

| Path | Changes |
|---|---|
| `pytest.ini` | Extend `testpaths` to include `adaptive-forex-mt5/tests`. |
| `adaptive-forex-mt5/.gitignore` | Add `state.db`, `state.db-wal`, `state.db-shm`. |
| `adaptive-forex-mt5/journal.py` | Add `log_llm_verdict`, `log_manage_action`, `log_manage_skip`, `log_unmanaged_poc_position`, `log_review_request`. Plus `kind` on `log_ready_alert` already exists; add `setup_fingerprint` field. |
| `adaptive-forex-mt5/agent.py` | Compute `setup_fingerprint` and pass it through `log_ready_alert`; in alerts-only branch call `dispatch.create_review_task`; new `poll_verdicts` loop in `run`. |
| `adaptive-forex-mt5/dashboard.py` | Three new sections: managed positions, heartbeat panel, unmanaged-poc-position banner. |
| `adaptive-forex-mt5/config.example.json` | Add `manager` and `agent.reviewer_agent` / `agent.review_enabled` keys. |
| `adaptive-forex-mt5/config.json` | Operator's local file — example values. |
| `adaptive-forex-mt5/test_e2e.py` | Add a fourth scenario: managed-position lifecycle with `--allow-live`. |
| `adaptive-forex-mt5/README.md` | Document trade_manager + reviewer launch (`Start-Process` snippets). |

---

## Conventions

- **TDD throughout.** Every task starts with a failing test, then minimum implementation to pass.
- **Pytest** for unit tests under `adaptive-forex-mt5/tests/`. The existing `test_e2e.py` stays a stand-alone script (live-gated).
- **No real MT5 in unit tests.** Mock `subprocess.run` (the existing pattern in `agent._run`).
- **Commits per task.** Imperative-mood subject ≤72 chars. No `feat:` prefix (project style — see `git log`).
- **Run from repo root:** `pytest adaptive-forex-mt5/tests -v`.
- **No `mkdir` step.** `Write` creates parent dirs.

---

## Task 1: Pytest scaffolding for adaptive-forex-mt5

**Files:**
- Modify: `pytest.ini`
- Create: `adaptive-forex-mt5/tests/__init__.py`
- Create: `adaptive-forex-mt5/tests/conftest.py`
- Create: `adaptive-forex-mt5/tests/test_smoke.py`

- [ ] **Step 1: Write the smoke test (failing — module not yet on path)**

`adaptive-forex-mt5/tests/test_smoke.py`:

```python
"""Smoke test: confirm pytest can import adaptive-forex-mt5 modules."""
def test_journal_importable():
    import journal  # noqa: F401

def test_agent_importable():
    import agent  # noqa: F401
```

- [ ] **Step 2: Add pytest config and conftest**

`adaptive-forex-mt5/tests/__init__.py`:

```python
```

(empty file — marker only)

`adaptive-forex-mt5/tests/conftest.py`:

```python
"""Pytest fixtures for adaptive-forex-mt5 unit tests.

We add the parent directory to sys.path so tests can `import journal`,
`import agent`, etc., the same way the production scripts do.
"""
from __future__ import annotations

import sys
from pathlib import Path

PARENT = Path(__file__).resolve().parent.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))
```

`pytest.ini` — append `adaptive-forex-mt5/tests` to testpaths:

```ini
[pytest]
testpaths =
    metatrader5_cli/mt5/tests
    adaptive-forex-mt5/tests
markers =
    integration: tests requiring a live MT5 terminal (deselect with -m "not integration")
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add pytest.ini adaptive-forex-mt5/tests/__init__.py adaptive-forex-mt5/tests/conftest.py adaptive-forex-mt5/tests/test_smoke.py
git commit -m "Add pytest scaffolding for adaptive-forex-mt5 unit tests"
```

---

## Task 2: New journal event kinds

**Files:**
- Modify: `adaptive-forex-mt5/journal.py`
- Create: `adaptive-forex-mt5/tests/test_journal_kinds.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_journal_kinds.py`:

```python
"""Unit tests for new journal event kinds added in phase 1."""
from __future__ import annotations

import json
from pathlib import Path

import journal


def _read_kinds(tmp_log: Path) -> list[str]:
    return [json.loads(l)["kind"] for l in tmp_log.read_text().splitlines() if l.strip()]


def test_log_llm_verdict_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_llm_verdict("USDJPY", {"alert_id": "abc", "decision": "take", "confidence": 0.8})
    assert _read_kinds(log) == ["llm_verdict"]


def test_log_manage_action_includes_required_fields(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_manage_action(ticket=42, stage_from="init", stage_to="be_armed",
                              old_sl=1.20, new_sl=1.205, trigger="be_r")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "manage_action"
    assert rec["ticket"] == 42
    assert rec["stage_from"] == "init"
    assert rec["stage_to"] == "be_armed"
    assert rec["old_sl"] == 1.20
    assert rec["new_sl"] == 1.205
    assert rec["trigger"] == "be_r"
    assert "ts" in rec


def test_log_manage_skip_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_manage_skip(ticket=42, reason="spread_cap")
    assert _read_kinds(log) == ["manage_skip"]


def test_log_unmanaged_poc_position(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_unmanaged_poc_position(ticket=42, symbol="USDJPY", magic=128461,
                                       reason="no_journal_match")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["kind"] == "unmanaged_poc_position"
    assert rec["reason"] == "no_journal_match"


def test_log_review_request_writes_kind(tmp_path, monkeypatch):
    log = tmp_path / "trades.jsonl"
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.log_review_request(alert_id="abc", task_id="t-1", pair="USDJPY")
    assert _read_kinds(log) == ["review_request"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_journal_kinds.py -v`
Expected: FAIL with `AttributeError: module 'journal' has no attribute 'log_llm_verdict'` (or similar for each new function).

- [ ] **Step 3: Add the new functions to journal.py**

Note: `journal.py` currently writes to a hard-coded path. Add a module-level
`_LOG_PATH` constant so tests can monkeypatch. Refactor `append` to use it.

In `adaptive-forex-mt5/journal.py`, find the existing path-derivation logic
near the top of the file and replace it with:

```python
_LOG_PATH = Path(__file__).resolve().parent / "logs" / "trades.jsonl"


def append(record: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", _ts())
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

(If `append` already takes this shape, the refactor is just exposing
`_LOG_PATH`.)

Then, append the new logger functions to the bottom of the file:

```python
def log_llm_verdict(pair: str, verdict: dict) -> None:
    """Record a reviewer-agent verdict joined back from the dispatcher pipeline."""
    append({"kind": "llm_verdict", "pair": pair, **verdict})


def log_manage_action(ticket: int, stage_from: str, stage_to: str,
                      old_sl: float, new_sl: float, trigger: str) -> None:
    """Record a confirmed BE move or trail tighten."""
    append({
        "kind": "manage_action",
        "ticket": ticket,
        "stage_from": stage_from,
        "stage_to": stage_to,
        "old_sl": old_sl,
        "new_sl": new_sl,
        "trigger": trigger,
    })


def log_manage_skip(ticket: int, reason: str, detail: dict | None = None) -> None:
    """Record a guard-rejected modify (rate-limited at call site)."""
    rec = {"kind": "manage_skip", "ticket": ticket, "reason": reason}
    if detail:
        rec["detail"] = detail
    append(rec)


def log_unmanaged_poc_position(ticket: int, symbol: str, magic: int, reason: str) -> None:
    """Record a poc-magic position the manager cannot bootstrap (rate-limited at call site)."""
    append({
        "kind": "unmanaged_poc_position",
        "ticket": ticket,
        "symbol": symbol,
        "magic": magic,
        "reason": reason,
    })


def log_review_request(alert_id: str, task_id: str, pair: str) -> None:
    """Record that agent.py created a trade_review task for this alert."""
    append({
        "kind": "review_request",
        "alert_id": alert_id,
        "task_id": task_id,
        "pair": pair,
    })
```

Also extend `log_ready_alert` to include `setup_fingerprint` if present in `scan` (Task 4 will populate it; for now just pass through if the caller adds it):

```python
def log_ready_alert(pair: str, scan: dict) -> None:
    record = {
        "kind": "ready_alert",
        "pair": pair,
        "status": "ready_alert",
        **_reasoning(scan),
    }
    if "setup_fingerprint" in scan:
        record["setup_fingerprint"] = scan["setup_fingerprint"]
    append(record)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_journal_kinds.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/journal.py adaptive-forex-mt5/tests/test_journal_kinds.py
git commit -m "Add journal kinds: llm_verdict, manage_action, manage_skip, unmanaged_poc_position, review_request"
```

---

## Task 3: state_db.py — schema, connect, helpers

**Files:**
- Create: `adaptive-forex-mt5/state_db.py`
- Create: `adaptive-forex-mt5/tests/test_state_db.py`
- Modify: `adaptive-forex-mt5/.gitignore`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_state_db.py`:

```python
"""Unit tests for state_db module."""
from __future__ import annotations

from pathlib import Path

import pytest

import state_db


@pytest.fixture
def db(tmp_path) -> Path:
    p = tmp_path / "state.db"
    state_db.init(p)
    return p


def test_init_creates_tables(db):
    with state_db.connect(db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"managed_position", "cursor", "heartbeat"} <= names


def test_init_is_idempotent(db):
    state_db.init(db)  # second call should be a no-op
    with state_db.connect(db) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert {"managed_position", "cursor", "heartbeat"} <= names


def test_upsert_managed_position_round_trip(db):
    row = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "init",
    }
    state_db.upsert_managed_position(db, row)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    assert rows[0]["ticket"] == 42
    assert rows[0]["symbol"] == "USDJPY"
    assert rows[0]["stage"] == "init"


def test_active_pos_uniq_index_blocks_duplicate_active(db):
    base = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "init",
    }
    state_db.upsert_managed_position(db, base)
    duplicate = {**base, "ticket": 43}
    with pytest.raises(state_db.DuplicateActiveError):
        state_db.upsert_managed_position(db, duplicate)


def test_active_pos_uniq_allows_new_after_close(db):
    base = {
        "ticket": 42, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": 41, "journal_anchor": "2026-05-08T12:00:00+00:00",
        "stage": "closed",
    }
    state_db.upsert_managed_position(db, base)
    new = {**base, "ticket": 43, "stage": "init"}
    state_db.upsert_managed_position(db, new)  # must not raise


def test_cursor_get_set(db):
    assert state_db.cursor_get(db, "last_verdict_seen") is None
    state_db.cursor_set(db, "last_verdict_seen", "2026-05-08T12:00:00+00:00")
    assert state_db.cursor_get(db, "last_verdict_seen") == "2026-05-08T12:00:00+00:00"


def test_heartbeat_upsert_get(db):
    state_db.heartbeat_upsert(db, "manager", pid=1234)
    rows = state_db.heartbeat_all(db)
    assert any(r["process"] == "manager" and r["pid"] == 1234 for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_state_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'state_db'`.

- [ ] **Step 3: Implement state_db.py**

`adaptive-forex-mt5/state_db.py`:

```python
"""SQLite layer for adaptive-forex-mt5 manager runtime state.

Schema reflects the 2026-05-08 design spec:
- managed_position: confirm-before-promote idempotency, broker-precision risk
  fields, active uniqueness via partial index.
- cursor: small key/value store (e.g. last_verdict_seen).
- heartbeat: per-process liveness for dashboard dead-process banner.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class DuplicateActiveError(Exception):
    """Raised when active_pos_uniq UNIQUE INDEX rejects a duplicate."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS managed_position (
    ticket              INTEGER PRIMARY KEY,
    account             INTEGER NOT NULL,
    symbol              TEXT    NOT NULL,
    magic               INTEGER NOT NULL,
    direction           TEXT    NOT NULL,
    entry_price         REAL    NOT NULL,
    initial_sl          REAL    NOT NULL,
    initial_tp          REAL,
    initial_risk_price  REAL    NOT NULL,
    initial_risk_points REAL    NOT NULL,
    point               REAL    NOT NULL,
    digits              INTEGER NOT NULL,
    opened_time         TEXT    NOT NULL,
    source_order_ticket INTEGER,
    journal_anchor      TEXT,
    stage               TEXT    NOT NULL,
    favorable_extreme_price REAL,
    last_sl_set         REAL,
    pending_action      TEXT,
    requested_sl        REAL,
    idempotency_key     TEXT,
    last_action_ts      TEXT,
    last_unmanaged_warning_ts TEXT,
    created_ts          TEXT    NOT NULL,
    updated_ts          TEXT    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS active_pos_uniq
    ON managed_position (account, symbol, magic)
    WHERE stage != 'closed';

CREATE TABLE IF NOT EXISTS cursor (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeat (
    process   TEXT PRIMARY KEY,
    last_seen TEXT NOT NULL,
    pid       INTEGER,
    notes     TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)


_MANAGED_COLS = [
    "ticket", "account", "symbol", "magic", "direction",
    "entry_price", "initial_sl", "initial_tp",
    "initial_risk_price", "initial_risk_points",
    "point", "digits", "opened_time", "source_order_ticket",
    "journal_anchor", "stage", "favorable_extreme_price",
    "last_sl_set", "pending_action", "requested_sl", "idempotency_key",
    "last_action_ts", "last_unmanaged_warning_ts",
]


def upsert_managed_position(db_path: Path, row: dict) -> None:
    """Insert or update a managed_position row.

    On INSERT we set created_ts and updated_ts to now. On UPDATE we refresh
    updated_ts only.
    """
    now = _now()
    cols = list(_MANAGED_COLS)
    values = [row.get(c) for c in cols]
    placeholders = ",".join(["?"] * len(cols))
    update_clause = ",".join(f"{c}=excluded.{c}" for c in cols if c != "ticket")
    sql = f"""
        INSERT INTO managed_position ({",".join(cols)}, created_ts, updated_ts)
        VALUES ({placeholders}, ?, ?)
        ON CONFLICT(ticket) DO UPDATE SET
            {update_clause},
            updated_ts = excluded.updated_ts
    """
    try:
        with connect(db_path) as conn:
            conn.execute(sql, [*values, now, now])
    except sqlite3.IntegrityError as e:
        if "active_pos_uniq" in str(e):
            raise DuplicateActiveError(str(e)) from e
        raise


def list_managed_positions(db_path: Path, *, only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM managed_position"
    if only_active:
        sql += " WHERE stage != 'closed'"
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_managed_position(db_path: Path, ticket: int) -> dict | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM managed_position WHERE ticket = ?", (ticket,)
        ).fetchone()
    return dict(row) if row else None


def cursor_get(db_path: Path, name: str) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM cursor WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


def cursor_set(db_path: Path, name: str, value: str) -> None:
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO cursor (name, value) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET value = excluded.value
        """, (name, value))


def heartbeat_upsert(db_path: Path, process: str, *, pid: int | None = None,
                     notes: str | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO heartbeat (process, last_seen, pid, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(process) DO UPDATE SET
                last_seen = excluded.last_seen,
                pid = excluded.pid,
                notes = excluded.notes
        """, (process, _now(), pid, notes))


def heartbeat_all(db_path: Path) -> list[dict]:
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM heartbeat").fetchall()]
```

- [ ] **Step 4: Update .gitignore**

Append to `adaptive-forex-mt5/.gitignore`:

```
state.db
state.db-wal
state.db-shm
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_state_db.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add adaptive-forex-mt5/state_db.py adaptive-forex-mt5/tests/test_state_db.py adaptive-forex-mt5/.gitignore
git commit -m "Add state_db module: managed_position + cursor + heartbeat with WAL mode"
```

---

## Task 4: setup_fingerprint module + integrate into ready_alert

**Files:**
- Create: `adaptive-forex-mt5/fingerprint.py`
- Create: `adaptive-forex-mt5/tests/test_fingerprint.py`
- Modify: `adaptive-forex-mt5/agent.py` (in alerts-only branch)

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_fingerprint.py`:

```python
"""Unit tests for setup_fingerprint computation."""
from __future__ import annotations

import pytest

import fingerprint


def _scan(**overrides):
    base = {
        "pair": "USDJPY",
        "direction": "buy",
        "setup": {"entry": 156.500, "sl": 156.300, "tp": 157.000},
        "poi": {"id": "FVG-1", "top": 156.520, "bottom": 156.480},
        "reasoning": {
            "structure": {"last_confirmed_event": {
                "type": "BOS",
                "level": {"time": "2026-05-08T12:00:00+00:00"},
            }},
        },
        "bar_time": "2026-05-08T12:05:00+00:00",
        "digits": 3,
    }
    base.update(overrides)
    return base


def test_fingerprint_is_deterministic():
    a = fingerprint.compute(_scan())
    b = fingerprint.compute(_scan())
    assert a == b
    assert isinstance(a, str)
    assert len(a) == 16  # 64-bit hex


def test_fingerprint_changes_when_levels_change():
    base = fingerprint.compute(_scan())
    moved_entry = fingerprint.compute(_scan(setup={"entry": 156.501, "sl": 156.300, "tp": 157.000}))
    assert base != moved_entry


def test_fingerprint_stable_under_irrelevant_field():
    base = fingerprint.compute(_scan())
    base_with_extra = _scan()
    base_with_extra["unrelated_field"] = "noise"
    assert base == fingerprint.compute(base_with_extra)


def test_fingerprint_changes_on_direction_flip():
    base = fingerprint.compute(_scan())
    flipped = fingerprint.compute(_scan(direction="sell"))
    assert base != flipped


def test_fingerprint_changes_on_poi_id():
    base = fingerprint.compute(_scan())
    other_poi = fingerprint.compute(_scan(poi={"id": "FVG-2", "top": 156.520, "bottom": 156.480}))
    assert base != other_poi


def test_fingerprint_rounds_to_digits():
    """Sub-point noise must not change the fingerprint."""
    base = fingerprint.compute(_scan(setup={"entry": 156.5000001, "sl": 156.300, "tp": 157.000}))
    same = fingerprint.compute(_scan(setup={"entry": 156.500, "sl": 156.300, "tp": 157.000}))
    assert base == same
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_fingerprint.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement fingerprint.py**

`adaptive-forex-mt5/fingerprint.py`:

```python
"""Compute a stable hash of the deterministic setup the bot has produced.

The fingerprint pins reviewer verdicts to the exact setup snapshot — without
it, the autopilot executor (phase 2) could re-confirm READY against a
different cousin setup that arrived a few bars later.
"""
from __future__ import annotations

import hashlib
import json


def _round(value, digits: int):
    if value is None:
        return None
    return round(float(value), digits)


def compute(scan: dict) -> str:
    """Return a 16-hex-char fingerprint of the setup defined by `scan`.

    Inputs (must be present unless explicitly optional):
      pair, direction
      setup.{entry, sl, tp}
      poi.{id, top, bottom}                 (optional — None-safe)
      reasoning.structure.last_confirmed_event.{type, level.time}  (optional)
      bar_time
      digits                                (defaults to 5 if not provided)
    """
    digits = int(scan.get("digits") or 5)
    setup = scan.get("setup") or {}
    poi = scan.get("poi") or {}
    reasoning = (scan.get("reasoning") or {}).get("structure") or {}
    last_event = reasoning.get("last_confirmed_event") or {}
    level = last_event.get("level") or {}

    payload = {
        "pair": scan.get("pair"),
        "direction": scan.get("direction"),
        "entry": _round(setup.get("entry"), digits),
        "sl": _round(setup.get("sl"), digits),
        "tp": _round(setup.get("tp"), digits),
        "poi_id": poi.get("id"),
        "poi_top": _round(poi.get("top"), digits),
        "poi_bottom": _round(poi.get("bottom"), digits),
        "event_type": last_event.get("type"),
        "event_time": level.get("time"),
        "bar_time": scan.get("bar_time"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_fingerprint.py -v`
Expected: 6 passed.

- [ ] **Step 5: Wire fingerprint into agent.py's ready_alert path**

In `adaptive-forex-mt5/agent.py`, find the alerts-only branch (the block
starting around the existing `if a.get("alerts_only"):`). At the start of
that block, before any journal/ntfy call, compute and stamp the fingerprint:

```python
        if a.get("alerts_only"):
            # ... existing extraction of setup/direction/digits/etc unchanged ...

            # Stamp the deterministic setup fingerprint so reviewers + the
            # phase-2 autopilot executor can pin verdicts to THIS setup,
            # not a fresh cousin a few bars later.
            import fingerprint  # local import to keep top-of-file imports stable
            data["setup_fingerprint"] = fingerprint.compute({
                "pair": pair,
                "direction": direction.lower(),
                "setup": setup,
                "poi": data.get("poi"),
                "reasoning": data.get("reasoning"),
                "bar_time": (data.get("reasoning") or {}).get("bar_time"),
                "digits": digits,
            })
            # ... existing body_lines / push / log_ready_alert calls follow ...
            # log_ready_alert already passes through setup_fingerprint (Task 2).
```

- [ ] **Step 6: Run all tests to verify still green**

Run: `pytest adaptive-forex-mt5/tests -v`
Expected: prior tests still pass; agent.py change is exercised by the integration tests later.

- [ ] **Step 7: Commit**

```bash
git add adaptive-forex-mt5/fingerprint.py adaptive-forex-mt5/tests/test_fingerprint.py adaptive-forex-mt5/agent.py
git commit -m "Add setup_fingerprint module and stamp it on every ready_alert"
```

---

## Task 5: dispatch.py — task creation + payload write

**Files:**
- Create: `adaptive-forex-mt5/dispatch.py`
- Create: `adaptive-forex-mt5/tests/test_dispatch.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_dispatch.py`:

```python
"""Unit tests for dispatch wrapper. Real ehukaiconnect calls are mocked."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dispatch


def test_alert_payload_path_is_alert_id_keyed(tmp_path):
    payload = {"alert_id": "2026-05-08T16:37:15Z-USDJPY", "pair": "USDJPY"}
    path = dispatch.alert_payload_path(tmp_path, payload["alert_id"])
    assert path == tmp_path / "2026-05-08T16:37:15Z-USDJPY.json"


def test_write_alert_payload_creates_file(tmp_path):
    payload = {"alert_id": "abc", "pair": "USDJPY", "direction": "buy"}
    path = dispatch.write_alert_payload(tmp_path, payload)
    assert path.exists()
    assert json.loads(path.read_text()) == payload


def test_create_review_task_calls_ehukaiconnect(tmp_path):
    payload = {"alert_id": "abc", "pair": "USDJPY", "setup_fingerprint": "deadbeef"}
    fake = MagicMock(returncode=0, stdout="task-123 created\n")
    with patch("dispatch.subprocess.run", return_value=fake) as run:
        task_id = dispatch.create_review_task(
            payload, alerts_dir=tmp_path, reviewer="ClaudeReviewer"
        )
    assert task_id == "task-123"
    args, kwargs = run.call_args
    cmd = args[0]
    assert cmd[0] == "ehukaiconnect"
    assert cmd[1] == "task" and cmd[2] == "create"
    assert "--type" in cmd and "trade_review" in cmd
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
    out = json.dumps([
        {"id": "t-1", "type": "trade_review", "status": "done",
         "description": str(tmp_path / "verdicts" / "abc.json"),
         "updated_ts": "2026-05-08T16:00:00Z"},
        {"id": "t-2", "type": "trade_review", "status": "done",
         "description": str(tmp_path / "verdicts" / "def.json"),
         "updated_ts": "2026-05-08T16:05:00Z"},
    ])
    fake = MagicMock(returncode=0, stdout=out)
    with patch("dispatch.subprocess.run", return_value=fake):
        tasks = dispatch.list_done_review_tasks(since=None)
    assert len(tasks) == 2
    assert tasks[0]["id"] == "t-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_dispatch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement dispatch.py**

`adaptive-forex-mt5/dispatch.py`:

```python
"""Wrap ehukaiconnect task and shared-file payload calls used by the agent."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


# Same workspace-shared file root used by ehukaiconnect. Resolved relative
# to the repo root (the adaptive-forex-mt5 cwd is two levels deep so we
# walk up).
def _shared_root() -> Path:
    here = Path(__file__).resolve()
    # adaptive-forex-mt5/ → repo root
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


_TASK_ID_RE = re.compile(r"\b(task-[A-Za-z0-9_-]+|t-[A-Za-z0-9_-]+|[A-Za-z0-9_-]{8,})\b")


def create_review_task(payload: dict, *, alerts_dir: Path, reviewer: str,
                       priority: str = "high") -> str | None:
    """Write the alert payload to shared files, create an ehukaiconnect task,
    and return the parsed task id (None on failure)."""
    path = write_alert_payload(alerts_dir, payload)
    cmd = [
        "ehukaiconnect", "task", "create",
        "--type", "trade_review",
        "--priority", priority,
        "--assignee", reviewer,
        "--description", str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None
    m = _TASK_ID_RE.search(res.stdout or "")
    return m.group(1) if m else None


def list_done_review_tasks(since: str | None) -> list[dict]:
    cmd = ["ehukaiconnect", "task", "list", "--type", "trade_review",
           "--status", "done", "--json"]
    if since:
        cmd += ["--since", since]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else data.get("tasks", [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_dispatch.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/dispatch.py adaptive-forex-mt5/tests/test_dispatch.py
git commit -m "Add dispatch wrapper for ehukaiconnect task create + list"
```

---

## Task 6: ClaudeReviewer skill template

**Files:**
- Create: `.ehukaiconnect/skills/ClaudeReviewer/SKILL.md`

- [ ] **Step 1: Write the skill**

`.ehukaiconnect/skills/ClaudeReviewer/SKILL.md`:

````markdown
# ClaudeReviewer Skill

Persistent review agent for `adaptive-forex-mt5` trade alerts. Wakes on
`dispatch_wake` events for tasks of type `trade_review` and emits an
advisory verdict on the deterministic setup the bot produced.

## Invariants (non-negotiable)

- **Advisory only.** Never call any `mt5 order ...`, `mt5 position
  modify`, or any command that mutates broker state.
- **Vote on the original levels.** Your job is to evaluate the
  bot's deterministic `entry / sl / tp` exactly as supplied. If you
  believe different levels would be better, vote `adjust` and put your
  proposed levels in `adjusted_*` — phase 1 surfaces that to the
  operator; phase 2 treats `adjust` as an automatic skip.
- **Never modify the alert payload.** Read-only.

## On wake (dispatch_wake event for a trade_review task)

1. Read the task description — it's a path to an alert JSON file under
   `.ehukaiconnect/shared/files/alerts/`.
2. Open that file. Note `alert_id`, `setup_fingerprint`, `pair`,
   `direction`, `setup.entry/sl/tp`, `poi`, `reasoning`.
3. Run top-down analysis using the MT5 CLI:
   ```
   mt5 --json ehukai topdown <pair>
   mt5 --json rates <pair> M1 200
   mt5 --json rates <pair> M5 200
   mt5 --json rates <pair> M15 200
   ```
   Optionally screenshot if available:
   ```
   mt5 ehukai screenshot <pair> --tf M5
   ```
4. Emit the verdict by writing
   `.ehukaiconnect/shared/files/verdicts/<alert_id>-claude.json`
   with the schema below, then close the task:
   ```
   ehukaiconnect task update <task_id> --status done --description <verdict_path>
   ```

## Verdict schema

```json
{
  "alert_id": "<from alert>",
  "reviewed_fingerprint": "<from alert.setup_fingerprint>",
  "decision": "take" | "skip" | "adjust",
  "adjusted_entry": null | <number>,
  "adjusted_sl":    null | <number>,
  "adjusted_tp":    null | <number>,
  "confidence": 0.0..1.0,
  "reasoning_summary": "<= 280 chars",
  "reasoning_full": "string",
  "model": "claude-opus-4-7",
  "ts": "<iso>"
}
```

`reviewed_fingerprint` MUST equal the alert's `setup_fingerprint`. If
something forces you to read a different fingerprint, set
`decision="skip"` with `reasoning_summary="fingerprint_mismatch"`.

## Bus rules

- One ACK per assignment, then work, then close. No mid-task chatter.
- If you cannot make a decision in 90s, close as `skip` with
  `reasoning_summary="timeout"`.
````

- [ ] **Step 2: Verify file is in place**

Run: `ls .ehukaiconnect/skills/ClaudeReviewer/SKILL.md`
Expected: file exists.

- [ ] **Step 3: Commit**

```bash
git add .ehukaiconnect/skills/ClaudeReviewer/SKILL.md
git commit -m "Add ClaudeReviewer skill template for advisory trade-alert verdicts"
```

(Note: `.ehukaiconnect/` is currently untracked workspace state. If the
file ends up gitignored at the workspace level, save the skill template
as `docs/skills/ClaudeReviewer-SKILL.md` instead and have the launch
script copy it into place. Adjust this step if so.)

---

## Task 7: agent.py — wire dispatch_review into the alerts-only branch

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_agent_dispatch.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_agent_dispatch.py`:

```python
"""Verify agent.py dispatches a review task in the alerts-only path."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import agent


def _cfg(tmp_path):
    return {
        "pairs": ["USDJPY"],
        "agent": {
            "alerts_only": True,
            "review_enabled": True,
            "reviewer_agent": "ClaudeReviewer",
            "min_quality_score": 0.85,
            "min_rr": 3.0,
            "min_stop_points": 80,
            "max_fvg_age_bars": 40,
            "max_concurrent_positions": 50,
            "max_trades_per_day": 500,
            "volume": 0.001,
            "strategy_id_prefix": "ehukai-poc",
            "scan_interval_seconds": 60,
            "outcome_poll_seconds": 30,
        },
        "ntfy": {"topic": "test", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
        "dashboard": {"bind_host": "127.0.0.1", "bind_port": 8765, "refresh_seconds": 5},
    }


@patch("agent.dispatch")
@patch("agent.alerts")
@patch("agent.journal")
@patch("agent.sniper_poc")
def test_alerts_only_creates_review_task(mock_sniper, mock_journal, mock_alerts,
                                         mock_dispatch, tmp_path):
    mock_sniper.return_value = {
        "ok": True,
        "data": {
            "status": "ready",
            "direction": "BUY",
            "quality_score": 0.9,
            "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
            "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
            "reasoning": {"structure": {"last_confirmed_event": {
                "type": "BOS",
                "level": {"time": "2026-05-08T12:00:00+00:00"},
            }}},
            "explain": ["BOS confirmed"],
        },
    }
    mock_dispatch.create_review_task.return_value = "task-xyz"
    mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
    cfg = _cfg(tmp_path)
    with patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        agent.place_new_orders(cfg)
    assert mock_dispatch.create_review_task.called
    payload = mock_dispatch.create_review_task.call_args.args[0]
    assert payload["alert_id"]
    assert payload["setup_fingerprint"]
    assert payload["pair"] == "USDJPY"
    mock_journal.log_ready_alert.assert_called_once()
    mock_journal.log_review_request.assert_called_once_with(
        alert_id=payload["alert_id"], task_id="task-xyz", pair="USDJPY"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_agent_dispatch.py -v`
Expected: FAIL — `dispatch` not imported in agent.py, or `create_review_task`
not invoked.

- [ ] **Step 3: Modify agent.py**

In `adaptive-forex-mt5/agent.py`, add at the top of the imports:

```python
import dispatch
```

In the alerts-only branch (inside `place_new_orders`), AFTER computing
`data["setup_fingerprint"]` (Task 4), AFTER `journal.log_ready_alert(pair, data)`,
add:

```python
            alert_id = f"{data.get('ts') or _now_iso()}-{pair}"
            payload = {
                "alert_id": alert_id,
                "pair": pair,
                "direction": direction.lower(),
                "setup_fingerprint": data["setup_fingerprint"],
                "setup": setup,
                "poi": data.get("poi"),
                "reasoning": data.get("reasoning"),
                "explain": data.get("explain"),
                "rr": rr,
                "ts": data.get("ts"),
            }
            if a.get("review_enabled"):
                task_id = dispatch.create_review_task(
                    payload,
                    alerts_dir=dispatch.alerts_dir_default(),
                    reviewer=a.get("reviewer_agent", "ClaudeReviewer"),
                )
                if task_id:
                    journal.log_review_request(
                        alert_id=alert_id, task_id=task_id, pair=pair
                    )
```

Add the helper if not already present at the top of `agent.py`:

```python
from datetime import datetime, timezone

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_agent_dispatch.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/agent.py adaptive-forex-mt5/tests/test_agent_dispatch.py
git commit -m "Dispatch trade_review task on every alerts-only READY"
```

---

## Task 8: agent.py — verdict poller

**Files:**
- Modify: `adaptive-forex-mt5/agent.py`
- Create: `adaptive-forex-mt5/tests/test_verdict_poller.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_verdict_poller.py`:

```python
"""Verify agent.poll_verdicts journals + ntfy-pushes closed reviews."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import agent


def _cfg(tmp_path):
    return {
        "agent": {"reviewer_agent": "ClaudeReviewer"},
        "ntfy": {"topic": "test", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


@patch("agent.alerts")
@patch("agent.journal")
@patch("agent.dispatch")
@patch("agent.state_db")
def test_poll_verdicts_journals_and_advances_cursor(mock_state, mock_dispatch,
                                                    mock_journal, mock_alerts,
                                                    tmp_path):
    verdict_path = tmp_path / "abc-claude.json"
    verdict_path.write_text(json.dumps({
        "alert_id": "abc",
        "decision": "take",
        "confidence": 0.84,
        "reviewed_fingerprint": "deadbeef",
        "reasoning_summary": "clean BOS, M1 trap absent",
    }))
    mock_state.cursor_get.return_value = None
    mock_dispatch.list_done_review_tasks.return_value = [
        {"id": "t-1", "type": "trade_review", "status": "done",
         "description": str(verdict_path),
         "updated_ts": "2026-05-08T16:05:00+00:00"},
    ]
    cfg = _cfg(tmp_path)
    db_path = tmp_path / "state.db"
    agent.poll_verdicts(cfg, db_path)
    # journaled
    mock_journal.log_llm_verdict.assert_called_once()
    args, kwargs = mock_journal.log_llm_verdict.call_args
    # arg 0 is pair (derived from alert_id)
    assert args[0]
    assert args[1]["alert_id"] == "abc"
    # ntfy push
    mock_alerts.push.assert_called_once()
    # cursor advanced
    mock_state.cursor_set.assert_called_once_with(
        db_path, "last_verdict_seen", "2026-05-08T16:05:00+00:00"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_verdict_poller.py -v`
Expected: FAIL — `agent.poll_verdicts` does not exist.

- [ ] **Step 3: Add poll_verdicts to agent.py**

Add to `adaptive-forex-mt5/agent.py`:

```python
import state_db


def poll_verdicts(cfg: dict, db_path) -> int:
    """Poll closed trade_review tasks since last_verdict_seen cursor.
    Journal each and push enriched ntfy. Return count processed."""
    cursor_name = "last_verdict_seen"
    since = state_db.cursor_get(db_path, cursor_name)
    tasks = dispatch.list_done_review_tasks(since=since)
    if not tasks:
        return 0
    last_ts = since
    count = 0
    for task in tasks:
        verdict_path_str = task.get("description")
        if not verdict_path_str:
            continue
        try:
            verdict = json.loads(Path(verdict_path_str).read_text())
        except Exception as e:
            journal.log_error("agent", "poll_verdicts_read", str(e))
            continue
        alert_id = verdict.get("alert_id") or ""
        pair = alert_id.split("-")[-1] if "-" in alert_id else ""
        verdict["task_id"] = task.get("id")
        verdict["task_updated_ts"] = task.get("updated_ts")
        journal.log_llm_verdict(pair, verdict)
        body = (
            f"{verdict.get('decision','?').upper()} conf={verdict.get('confidence','?')}\n"
            f"{verdict.get('reasoning_summary','')}"
        )
        alerts.push(cfg, f"Reviewer verdict: {pair}", body, tags=["robot"])
        last_ts = task.get("updated_ts") or last_ts
        count += 1
    if last_ts and last_ts != since:
        state_db.cursor_set(db_path, cursor_name, last_ts)
    return count
```

Also import `from pathlib import Path` and `import json` if not already at
the top of agent.py.

In `agent.run()`, after the existing scan loop body (where
`scan_once(cfg)` is called), add a verdict-poll call gated on
`review_enabled`:

```python
        if cfg["agent"].get("review_enabled"):
            try:
                processed = poll_verdicts(cfg, _state_db_path())
                if processed:
                    print(f"[agent] processed {processed} verdicts")
            except Exception as e:
                journal.log_error("agent", "poll_verdicts", str(e))
```

Helper near the top of agent.py:

```python
def _state_db_path() -> Path:
    return Path(__file__).resolve().parent / "state.db"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_verdict_poller.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/agent.py adaptive-forex-mt5/tests/test_verdict_poller.py
git commit -m "Add verdict poller: journal llm_verdict + push enriched ntfy each scan"
```

---

## Task 9: trade_manager.py skeleton with heartbeat

**Files:**
- Create: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_trade_manager_skeleton.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_trade_manager_skeleton.py`:

```python
"""Skeleton tests: trade_manager initializes state.db and writes heartbeat."""
from __future__ import annotations

from unittest.mock import patch

import state_db
import trade_manager


def test_init_creates_state_db(tmp_path):
    db = tmp_path / "state.db"
    trade_manager.init_state(db)
    rows = state_db.heartbeat_all(db)
    assert isinstance(rows, list)


def test_loop_once_upserts_heartbeat(tmp_path):
    db = tmp_path / "state.db"
    trade_manager.init_state(db)
    cfg = {"manager": {"loop_seconds": 1}, "pairs": [], "agent": {"strategy_id_prefix": "x"},
           "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60}}
    with patch("trade_manager.list_positions", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.heartbeat_all(db)
    procs = {r["process"] for r in rows}
    assert "manager" in procs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_trade_manager_skeleton.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement trade_manager.py skeleton**

`adaptive-forex-mt5/trade_manager.py`:

```python
"""Python-side post-fill trade manager — replaces AdaptiveTrailEA for our magics.

Runs as a separate process. Each loop:
  1. Heartbeat upsert to state.db.
  2. List MT5 positions, filter to poc-magic set.
  3. For each: bootstrap if needed, then BE/Chandelier/modify state machine.

Confirm-before-promote idempotency: last_sl_set is only set after MT5 confirms
the modify. Pending modifies retry on next loop with the same idempotency key.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import journal
import state_db


HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "state.db"


def init_state(db_path: Path = DB_PATH) -> None:
    state_db.init(db_path)


def _cli(cfg: dict) -> list[str]:
    base = [cfg["mt5_cli"]["command"]]
    if cfg["mt5_cli"].get("live"):
        base.append("--live")
    return base


def _run(cfg: dict, args: list[str]) -> dict | None:
    cmd = _cli(cfg) + ["--json"] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=cfg["mt5_cli"]["subprocess_timeout_seconds"])
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def list_positions(cfg: dict) -> list[dict]:
    out = _run(cfg, ["position", "list"])
    if not out or not out.get("ok"):
        return []
    return out.get("data") or []


def loop_once(cfg: dict, db_path: Path = DB_PATH) -> None:
    """One iteration: heartbeat + scan-and-manage. Subsequent tasks fill in
    bootstrap / BE / Chandelier / modify."""
    state_db.heartbeat_upsert(db_path, "manager", pid=os.getpid())
    # placeholder: positions handled in later tasks
    list_positions(cfg)


def run() -> None:
    cfg_path = HERE / "config.json"
    cfg = json.loads(cfg_path.read_text())
    init_state()
    interval = float(cfg.get("manager", {}).get("loop_seconds", 1))
    print(f"[trade_manager] starting · loop={interval}s · live={cfg['mt5_cli']['live']}")
    while True:
        try:
            loop_once(cfg)
        except Exception as e:
            journal.log_error("trade_manager", "loop", str(e))
        time.sleep(interval)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_trade_manager_skeleton.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_trade_manager_skeleton.py
git commit -m "Add trade_manager.py skeleton with heartbeat upsert"
```

---

## Task 10: poc-magic set derivation + bootstrap two-phase match

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_bootstrap.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_bootstrap.py`:

```python
"""Bootstrap matches MT5 positions to journal placements; fail-closed on
ambiguity or missing data."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY", "GBPJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"loop_seconds": 1, "be_buffer_points": 5},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_poc_magics_derived_from_pairs():
    cfg = _cfg()
    magics = trade_manager.poc_magics(cfg)
    assert len(magics) == 2
    assert all(isinstance(m, int) for m in magics)


def test_bootstrap_ticket_match(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    # Seed a placement record
    journal.append({
        "kind": "placement", "pair": "USDJPY",
        "ticket": 99, "magic": 128461,
        "entry": 156.50, "sl": 156.30, "tp": 157.00,
        "direction": "buy",
    })
    cfg = _cfg()
    pos = {
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "volume": 0.001, "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    assert rows[0]["ticket"] == 99
    assert rows[0]["initial_sl"] == 156.30
    assert rows[0]["stage"] == "init"


def test_bootstrap_fail_closed_no_match(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    cfg = _cfg()
    pos = {
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "volume": 0.001, "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert rows == []  # nothing managed
    # Warning event written to journal
    lines = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    kinds = [r["kind"] for r in lines]
    assert "unmanaged_poc_position" in kinds


def test_bootstrap_ambiguous_magic_symbol_fails_closed(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)

    # Two open placements with same magic+symbol but different tickets
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 50, "magic": 128461,
                    "entry": 156.20, "sl": 156.00, "tp": 156.80, "direction": "buy"})
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 60, "magic": 128461,
                    "entry": 156.30, "sl": 156.10, "tp": 156.90, "direction": "buy"})
    cfg = _cfg()
    pos = {  # ticket doesn't match either; falls back to (magic, symbol)
        "ticket": 99, "symbol": "USDJPY", "magic": 128461,
        "type": "buy", "open_price": 156.50,
        "sl": 156.30, "tp": 157.00, "time": "2026-05-08T12:00:00+00:00",
    }
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(cfg, db, pos, account=9999)
    rows = state_db.list_managed_positions(db)
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_bootstrap.py -v`
Expected: FAIL — `poc_magics` / `bootstrap_position` not implemented.

- [ ] **Step 3: Implement poc_magics + bootstrap_position**

In `adaptive-forex-mt5/trade_manager.py`, add:

```python
import journal as _journal_mod  # for read_all
from journal import derive_magic


def poc_magics(cfg: dict) -> set[int]:
    prefix = cfg["agent"]["strategy_id_prefix"]
    return {derive_magic(f"{prefix}-{pair}") for pair in cfg["pairs"]}


def _symbol_point_digits(cfg: dict, symbol: str) -> tuple[float, int]:
    """Look up the broker's `point` and `digits` for a symbol via the CLI.
    Falls back to JPY/non-JPY heuristics if the call fails."""
    out = _run(cfg, ["symbol", "info", symbol])
    if out and out.get("ok"):
        d = out.get("data") or {}
        point = float(d.get("point") or (0.001 if symbol.endswith("JPY") else 0.00001))
        digits = int(d.get("digits") or (3 if symbol.endswith("JPY") else 5))
        return point, digits
    return (0.001, 3) if symbol.endswith("JPY") else (0.00001, 5)


def _open_journal_placements() -> list[dict]:
    """All `kind=placement` records in trades.jsonl that have no later
    `kind=outcome` record for the same ticket."""
    rows = _journal_mod.read_all()
    placements = {}
    closed = set()
    for r in rows:
        kind = r.get("kind")
        ticket = r.get("ticket")
        if kind == "placement" and ticket is not None:
            placements[ticket] = r
        elif kind == "outcome" and ticket is not None:
            closed.add(ticket)
    return [p for tk, p in placements.items() if tk not in closed]


def _match_placement(pos: dict, placements: list[dict]) -> dict | None:
    """Two-phase match: ticket exact, then (magic, symbol) unambiguous."""
    by_ticket = {p.get("ticket"): p for p in placements if p.get("ticket")}
    if pos["ticket"] in by_ticket:
        return by_ticket[pos["ticket"]]
    candidates = [
        p for p in placements
        if p.get("magic") == pos["magic"] and p.get("pair") == pos["symbol"]
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None  # zero or ambiguous


_UNMANAGED_WARN_INTERVAL_SECONDS = 60


def _should_warn_unmanaged(db_path: Path, ticket: int) -> bool:
    """Rate-limit the unmanaged_poc_position warning to once per minute per ticket."""
    row = state_db.get_managed_position(db_path, ticket)
    if not row:
        return True
    last = row.get("last_unmanaged_warning_ts")
    if not last:
        return True
    from datetime import datetime
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    delta = (datetime.now(last_dt.tzinfo) - last_dt).total_seconds()
    return delta >= _UNMANAGED_WARN_INTERVAL_SECONDS


def bootstrap_position(cfg: dict, db_path: Path, pos: dict, *, account: int) -> dict | None:
    """Match an MT5 position to a journal placement and seed managed_position.

    Returns the seeded row dict on success, None on fail-closed (no match,
    ambiguous, or already-closed in journal).
    """
    if pos["magic"] not in poc_magics(cfg):
        return None
    existing = state_db.get_managed_position(db_path, pos["ticket"])
    if existing and existing["stage"] != "closed":
        return existing
    placement = _match_placement(pos, _open_journal_placements())
    if placement is None:
        if _should_warn_unmanaged(db_path, pos["ticket"]):
            journal.log_unmanaged_poc_position(
                ticket=pos["ticket"], symbol=pos["symbol"],
                magic=pos["magic"], reason="no_journal_match_or_ambiguous",
            )
        return None
    point, digits = _symbol_point_digits(cfg, pos["symbol"])
    initial_sl = float(placement.get("sl") or pos["sl"])
    entry_price = float(placement.get("entry") or pos["open_price"])
    initial_risk_price = abs(entry_price - initial_sl)
    initial_risk_points = initial_risk_price / point if point else 0.0
    row = {
        "ticket": pos["ticket"],
        "account": account,
        "symbol": pos["symbol"],
        "magic": pos["magic"],
        "direction": pos["type"],
        "entry_price": entry_price,
        "initial_sl": initial_sl,
        "initial_tp": placement.get("tp") or pos.get("tp"),
        "initial_risk_price": initial_risk_price,
        "initial_risk_points": initial_risk_points,
        "point": point,
        "digits": digits,
        "opened_time": pos.get("time") or "",
        "source_order_ticket": placement.get("ticket"),
        "journal_anchor": placement.get("ts"),
        "stage": "init",
    }
    state_db.upsert_managed_position(db_path, row)
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_bootstrap.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_bootstrap.py
git commit -m "Add bootstrap with two-phase match + fail-closed unmanaged warning"
```

---

## Task 11: Stage inference on bootstrap (never loosen SL)

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_stage_inference.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_stage_inference.py`:

```python
"""Bootstrap should infer stage from current SL relative to entry, never loosen."""
from __future__ import annotations

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"be_buffer_points": 5},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def _seed_placement(monkeypatch, tmp_path, sl=156.30, entry=156.50):
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": entry, "sl": sl, "tp": 157.00,
                    "direction": "buy"})


def test_init_stage_when_sl_below_entry_buy(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.30, "tp": 157.00,
           "time": "2026-05-08T12:00:00+00:00"}
    from unittest.mock import patch
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
    assert row["last_sl_set"] is None  # no confirmed move yet


def test_be_armed_when_sl_at_or_above_entry_buy(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
           "open_price": 156.50, "sl": 156.505, "tp": 157.00,  # SL above entry+buffer
           "time": "2026-05-08T12:00:00+00:00"}
    from unittest.mock import patch
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "be_armed"
    assert row["last_sl_set"] == 156.505  # known-good SL pinned


def test_init_stage_for_sell_when_sl_above_entry_only_marginally(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    _seed_placement(monkeypatch, tmp_path, sl=156.70, entry=156.50)
    pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "sell",
           "open_price": 156.50, "sl": 156.70, "tp": 156.00,
           "time": "2026-05-08T12:00:00+00:00"}
    from unittest.mock import patch
    with patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)):
        trade_manager.bootstrap_position(_cfg(), db, pos, account=9999)
        trade_manager.infer_stage_after_bootstrap(_cfg(), db, pos)
    row = state_db.get_managed_position(db, 99)
    assert row["stage"] == "init"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_stage_inference.py -v`
Expected: FAIL — `infer_stage_after_bootstrap` not defined.

- [ ] **Step 3: Add infer_stage_after_bootstrap**

Append to `adaptive-forex-mt5/trade_manager.py`:

```python
def infer_stage_after_bootstrap(cfg: dict, db_path: Path, pos: dict) -> None:
    """After bootstrap_position, look at the live SL relative to entry and
    promote stage if it's already at or beyond breakeven. Never loosen.

    Buy: position.sl >= entry + BE_buffer*point  → at least be_armed.
    Sell: position.sl <= entry - BE_buffer*point → at least be_armed.
    """
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None or row["stage"] != "init":
        return
    point = row["point"]
    entry = row["entry_price"]
    buffer_points = float(cfg["manager"].get("be_buffer_points", 5))
    threshold = entry + buffer_points * point if pos["type"] == "buy" else entry - buffer_points * point
    sl = float(pos["sl"])
    is_at_be = (sl >= threshold) if pos["type"] == "buy" else (sl <= threshold)
    if is_at_be:
        row["stage"] = "be_armed"
        row["last_sl_set"] = sl
        state_db.upsert_managed_position(db_path, row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_stage_inference.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_stage_inference.py
git commit -m "Bootstrap stage inference: promote to be_armed if SL already past entry"
```

---

## Task 12: BE-move computation (R-based + fixed-point fallback)

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_be_move.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_be_move.py`:

```python
"""BE-move math: trigger when favorable distance >= BE_R * initial_risk."""
from __future__ import annotations

import trade_manager


def _row(direction="buy", entry=156.50, initial_risk_price=0.20, point=0.001):
    return {
        "direction": direction, "entry_price": entry,
        "initial_risk_price": initial_risk_price,
        "initial_risk_points": initial_risk_price / point,
        "point": point,
    }


def test_be_target_buy_below_threshold():
    row = _row()
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 + 0.10  # 0.10 / 0.20 = 0.5R, below 0.8 trigger
    assert trade_manager.compute_be_target(row, cfg, favorable_price) is None


def test_be_target_buy_at_threshold():
    row = _row()
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 + 0.16  # 0.80R
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.505  # entry + 5 points


def test_be_target_sell_at_threshold():
    row = _row(direction="sell", entry=156.50, initial_risk_price=0.20)
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 - 0.16
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.495  # entry - 5 points


def test_be_target_uses_fallback_when_risk_zero():
    row = _row()
    row["initial_risk_price"] = 0.0
    row["initial_risk_points"] = 0.0
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5,
                       "be_trigger_points_fallback": 80}}
    # 80 points = 0.080 in JPY pairs
    favorable_price = 156.50 + 0.080
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.505
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_be_move.py -v`
Expected: FAIL — `compute_be_target` not defined.

- [ ] **Step 3: Implement compute_be_target**

Append to `adaptive-forex-mt5/trade_manager.py`:

```python
def compute_be_target(row: dict, cfg: dict, favorable_price: float) -> float | None:
    """Return the BE-move SL target if R-trigger met, else None.

    For a buy: favorable_price > entry. We require
    `(favorable_price - entry) / initial_risk_price >= be_trigger_r`.
    Target SL = entry + be_buffer_points * point.
    Mirror for sell.
    """
    m = cfg["manager"]
    trigger_r = float(m.get("be_trigger_r", 0.80))
    buffer_points = float(m.get("be_buffer_points", 5))
    fallback_points = float(m.get("be_trigger_points_fallback", 80))
    point = row["point"]
    entry = row["entry_price"]
    risk_price = row["initial_risk_price"]
    if row["direction"] == "buy":
        favorable_distance = favorable_price - entry
        target = entry + buffer_points * point
    else:
        favorable_distance = entry - favorable_price
        target = entry - buffer_points * point
    if favorable_distance <= 0:
        return None
    if risk_price > 0:
        achieved_r = favorable_distance / risk_price
        if achieved_r < trigger_r:
            return None
    else:
        achieved_points = favorable_distance / point if point else 0
        if achieved_points < fallback_points:
            return None
    return round(target, row.get("digits", 5))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_be_move.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_be_move.py
git commit -m "Add BE-move target math with R-trigger and fixed-point fallback"
```

---

## Task 13: Chandelier trail computation

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_chandelier.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_chandelier.py`:

```python
"""Chandelier trail: highest_high - ATR*multiplier (buy), mirror for sell."""
from __future__ import annotations

import trade_manager


def _bars(highs, lows, closes):
    return [{"high": h, "low": l, "close": c} for h, l, c in zip(highs, lows, closes)]


def test_chandelier_buy_simple():
    # 3 bars to keep math obvious. ATR(2) ≈ TR-mean over the last 2 bars.
    bars = _bars(
        highs=[1.10, 1.11, 1.12],
        lows=[1.08, 1.09, 1.105],
        closes=[1.09, 1.10, 1.115],
    )
    cfg = {"manager": {"chandelier_atr_period": 2, "chandelier_atr_multiplier": 1.0,
                       "chandelier_extreme_lookback": 3}}
    stop = trade_manager.compute_chandelier(bars, direction="buy", cfg=cfg)
    # highest_high = 1.12. ATR over last 2 TRs: TR2 = max(1.11-1.09, |1.11-1.09|, |1.09-1.09|) = 0.02
    # TR3 = max(1.12-1.105, |1.12-1.10|, |1.105-1.10|) = 0.02. ATR = 0.02. stop = 1.12 - 0.02 = 1.10.
    assert stop == 1.10


def test_chandelier_sell_simple():
    bars = _bars(
        highs=[1.12, 1.11, 1.10],
        lows=[1.10, 1.09, 1.08],
        closes=[1.11, 1.10, 1.085],
    )
    cfg = {"manager": {"chandelier_atr_period": 2, "chandelier_atr_multiplier": 1.0,
                       "chandelier_extreme_lookback": 3}}
    stop = trade_manager.compute_chandelier(bars, direction="sell", cfg=cfg)
    # lowest_low = 1.08. TR2 = 0.02. TR3 ≈ 0.02. ATR = 0.02. stop = 1.08 + 0.02 = 1.10.
    assert stop == 1.10


def test_chandelier_too_few_bars_returns_none():
    bars = _bars(highs=[1.10], lows=[1.08], closes=[1.09])
    cfg = {"manager": {"chandelier_atr_period": 22, "chandelier_atr_multiplier": 3.0,
                       "chandelier_extreme_lookback": 22}}
    assert trade_manager.compute_chandelier(bars, direction="buy", cfg=cfg) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_chandelier.py -v`
Expected: FAIL — function not defined.

- [ ] **Step 3: Implement compute_chandelier**

Append to `adaptive-forex-mt5/trade_manager.py`:

```python
def compute_chandelier(bars: list[dict], *, direction: str, cfg: dict) -> float | None:
    """Chandelier exit on a list of OHLC bars (oldest first).

    bars: [{ "high", "low", "close" }, ...] — closed bars only.
    Returns: trail SL price, or None if not enough data.
    """
    m = cfg["manager"]
    period = int(m.get("chandelier_atr_period", 22))
    mult = float(m.get("chandelier_atr_multiplier", 3.0))
    lookback = int(m.get("chandelier_extreme_lookback", 22))

    if len(bars) < max(period, lookback) - 0:  # need at least period+1 for a TR window
        return None
    if len(bars) < 2:
        return None

    # True Range series. We need at least `period` TRs to take an average,
    # so total bars must be >= period + 1.
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]; l = bars[i]["low"]; pc = bars[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    atr = sum(trs[-period:]) / period

    extremes_window = bars[-lookback:]
    if direction == "buy":
        highest_high = max(b["high"] for b in extremes_window)
        return highest_high - mult * atr
    else:
        lowest_low = min(b["low"] for b in extremes_window)
        return lowest_low + mult * atr
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_chandelier.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_chandelier.py
git commit -m "Add Chandelier trail math (ATR-based, magic-scoped)"
```

---

## Task 14: Confirm-before-promote modify state machine

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_modify_state_machine.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_modify_state_machine.py`:

```python
"""Confirm-before-promote: last_sl_set is set only after MT5 confirms.

Pending modifies retry on next loop using the same idempotency key.
Live-intent gate (cfg.mt5_cli.live=False) → manage_skip reason=not_live.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import journal
import state_db
import trade_manager


def _seeded(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    state_db.upsert_managed_position(db, {
        "ticket": 99, "account": 9999, "symbol": "USDJPY", "magic": 128461,
        "direction": "buy", "entry_price": 156.50, "initial_sl": 156.30,
        "initial_tp": 157.00, "initial_risk_price": 0.20,
        "initial_risk_points": 200.0, "point": 0.001, "digits": 3,
        "opened_time": "2026-05-08T12:00:00+00:00",
        "source_order_ticket": None, "journal_anchor": None, "stage": "init",
    })
    return db, log


def test_live_false_skips_with_not_live(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    cfg = {"manager": {"min_sl_improvement_points": 5, "max_spread_points": 100},
           "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60}}
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    trade_manager.attempt_modify(cfg, db, pos, new_sl=156.40, reason="be_r")
    row = state_db.get_managed_position(db, 99)
    assert row["last_sl_set"] is None
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]
    assert "manage_skip" in kinds


def test_min_improvement_skips(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    cfg = {"manager": {"min_sl_improvement_points": 5, "max_spread_points": 100},
           "mt5_cli": {"command": "mt5", "live": True, "subprocess_timeout_seconds": 60}}
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    # 4 points improvement, below the 5-point floor
    trade_manager.attempt_modify(cfg, db, pos, new_sl=156.304, reason="trail")
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]
    assert "manage_skip" in kinds


def test_successful_modify_promotes_last_sl_set(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    cfg = {"manager": {"min_sl_improvement_points": 5, "max_spread_points": 100},
           "mt5_cli": {"command": "mt5", "live": True, "subprocess_timeout_seconds": 60}}
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    # Mock _run to return ok and then the confirm read returns the new SL.
    def fake_run(cfg, args):
        if args[:2] == ["position", "modify"]:
            return {"ok": True, "data": {"retcode": 10009}}
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.40,
                                          "symbol": "USDJPY", "type": "buy"}]}
        return None
    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(cfg, db, pos, new_sl=156.40, reason="be_r",
                                     stage_to="be_armed")
    row = state_db.get_managed_position(db, 99)
    assert row["last_sl_set"] == 156.40
    assert row["stage"] == "be_armed"
    assert row["pending_action"] is None
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines() if l.strip()]
    assert "manage_action" in kinds


def test_unknown_result_keeps_pending_for_retry(tmp_path, monkeypatch):
    db, log = _seeded(tmp_path, monkeypatch)
    cfg = {"manager": {"min_sl_improvement_points": 5, "max_spread_points": 100,
                       "modify_cooldown_seconds": 5},
           "mt5_cli": {"command": "mt5", "live": True, "subprocess_timeout_seconds": 60}}
    pos = {"ticket": 99, "symbol": "USDJPY", "type": "buy", "sl": 156.30, "spread": 10}
    # First call: modify "succeeds" but confirm read shows the OLD SL
    def fake_run(cfg, args):
        if args[:2] == ["position", "modify"]:
            return {"ok": True, "data": {"retcode": 10009}}
        if args[:2] == ["position", "list"]:
            return {"ok": True, "data": [{"ticket": 99, "sl": 156.30,
                                          "symbol": "USDJPY", "type": "buy"}]}
        return None
    with patch.object(trade_manager, "_run", side_effect=fake_run):
        trade_manager.attempt_modify(cfg, db, pos, new_sl=156.40, reason="be_r",
                                     stage_to="be_armed")
    row = state_db.get_managed_position(db, 99)
    assert row["pending_action"] == "modify_sl"
    assert row["requested_sl"] == 156.40
    assert row["last_sl_set"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_modify_state_machine.py -v`
Expected: FAIL — `attempt_modify` not defined.

- [ ] **Step 3: Implement attempt_modify**

Append to `adaptive-forex-mt5/trade_manager.py`:

```python
import hashlib
from datetime import datetime, timezone


def _idempotency_key(ticket: int, new_sl: float, stage_to: str) -> str:
    raw = f"{ticket}|{new_sl}|{stage_to}".encode()
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def _is_tightening(direction: str, current_sl: float, new_sl: float) -> bool:
    return new_sl > current_sl if direction == "buy" else new_sl < current_sl


def attempt_modify(cfg: dict, db_path: Path, pos: dict, *, new_sl: float,
                   reason: str, stage_to: str | None = None) -> None:
    """Stage → call → confirm → promote. Pending modifies retry next loop."""
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None:
        return
    m = cfg["manager"]
    point = row["point"]
    min_improvement = float(m.get("min_sl_improvement_points", 5))
    max_spread = float(m.get("max_spread_points", 100))

    # Spread guard
    spread = float(pos.get("spread") or 0)
    if max_spread > 0 and spread > max_spread:
        journal.log_manage_skip(ticket=pos["ticket"], reason="spread_cap",
                                detail={"spread": spread, "cap": max_spread})
        return

    # Tightening guard
    current_sl = float(pos.get("sl") or row.get("last_sl_set") or row["initial_sl"])
    if not _is_tightening(row["direction"], current_sl, new_sl):
        journal.log_manage_skip(ticket=pos["ticket"], reason="not_tightening")
        return
    improvement_points = abs(new_sl - current_sl) / point if point else 0
    if improvement_points < min_improvement:
        journal.log_manage_skip(ticket=pos["ticket"], reason="min_improvement",
                                detail={"points": improvement_points, "floor": min_improvement})
        return

    # Live-intent gate
    if not cfg["mt5_cli"].get("live"):
        journal.log_manage_skip(ticket=pos["ticket"], reason="not_live")
        return

    # Stage the request
    new_sl_rounded = round(new_sl, row["digits"])
    key = _idempotency_key(pos["ticket"], new_sl_rounded, stage_to or row["stage"])
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = new_sl_rounded
    row["idempotency_key"] = key
    row["last_action_ts"] = datetime.now(timezone.utc).isoformat()
    state_db.upsert_managed_position(db_path, row)

    # Call the broker
    res = _run(cfg, ["position", "modify", str(pos["ticket"]),
                     "--sl", f"{new_sl_rounded:.{row['digits']}f}",
                     "--filling", "fok"])
    # Confirm by reading position state
    confirm = _run(cfg, ["position", "list"])
    confirmed_sl = None
    if confirm and confirm.get("ok"):
        for p in confirm.get("data") or []:
            if p["ticket"] == pos["ticket"]:
                confirmed_sl = float(p["sl"])
                break

    if confirmed_sl == new_sl_rounded:
        old_sl = current_sl
        row["last_sl_set"] = new_sl_rounded
        if stage_to:
            row["stage"] = stage_to
        row["pending_action"] = None
        row["requested_sl"] = None
        row["idempotency_key"] = None
        state_db.upsert_managed_position(db_path, row)
        journal.log_manage_action(
            ticket=pos["ticket"], stage_from=row["stage"] if stage_to else row["stage"],
            stage_to=stage_to or row["stage"], old_sl=old_sl, new_sl=new_sl_rounded,
            trigger=reason,
        )
        return

    # Unknown / not yet confirmed: leave pending for next-loop retry.
    journal.log_manage_skip(ticket=pos["ticket"], reason="unconfirmed",
                            detail={"requested_sl": new_sl_rounded,
                                    "current_sl": confirmed_sl})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests/test_modify_state_machine.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_modify_state_machine.py
git commit -m "Add confirm-before-promote modify state machine"
```

---

## Task 15: trade_manager.loop_once — full integration

**Files:**
- Modify: `adaptive-forex-mt5/trade_manager.py`
- Create: `adaptive-forex-mt5/tests/test_loop_once.py`

- [ ] **Step 1: Write the failing test**

`adaptive-forex-mt5/tests/test_loop_once.py`:

```python
"""End-to-end (in-process) test of one loop iteration: bootstrap +
infer_stage + BE check + Chandelier trail + heartbeat."""
from __future__ import annotations

from unittest.mock import patch

import journal
import state_db
import trade_manager


def _cfg():
    return {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {
            "loop_seconds": 1,
            "be_trigger_r": 0.80,
            "be_buffer_points": 5,
            "be_trigger_points_fallback": 80,
            "chandelier_atr_period": 2,
            "chandelier_atr_multiplier": 1.0,
            "chandelier_extreme_lookback": 3,
            "chandelier_timeframe": "M5",
            "min_sl_improvement_points": 5,
            "max_spread_points": 100,
        },
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
    }


def test_loop_once_writes_heartbeat_and_bootstraps(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    journal.append({"kind": "placement", "pair": "USDJPY", "ticket": 99,
                    "magic": 128461, "entry": 156.50, "sl": 156.30, "tp": 157.00,
                    "direction": "buy"})
    fake_pos = {"ticket": 99, "symbol": "USDJPY", "magic": 128461, "type": "buy",
                "open_price": 156.50, "sl": 156.30, "tp": 157.00, "spread": 10,
                "time": "2026-05-08T12:00:00+00:00"}
    cfg = _cfg()
    with patch.object(trade_manager, "list_positions", return_value=[fake_pos]), \
         patch.object(trade_manager, "_account_login", return_value=9999), \
         patch.object(trade_manager, "_symbol_point_digits", return_value=(0.001, 3)), \
         patch.object(trade_manager, "poc_magics", return_value={128461}), \
         patch.object(trade_manager, "_recent_bars", return_value=[]):
        trade_manager.loop_once(cfg, db)
    rows = state_db.list_managed_positions(db)
    assert len(rows) == 1
    hb = state_db.heartbeat_all(db)
    assert any(h["process"] == "manager" for h in hb)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest adaptive-forex-mt5/tests/test_loop_once.py -v`
Expected: FAIL — loop_once is the skeleton from Task 9, doesn't yet call bootstrap.

- [ ] **Step 3: Update loop_once**

Replace `loop_once` in `adaptive-forex-mt5/trade_manager.py` with:

```python
def _account_login(cfg: dict) -> int:
    out = _run(cfg, ["account", "info"])
    if out and out.get("ok"):
        return int((out.get("data") or {}).get("login") or 0)
    return 0


def _recent_bars(cfg: dict, symbol: str, timeframe: str, count: int) -> list[dict]:
    out = _run(cfg, ["rates", symbol, timeframe, str(count)])
    if not out or not out.get("ok"):
        return []
    return out.get("data") or []


def _favorable_price(direction: str, pos: dict) -> float:
    """Use bid for buy MFE, ask for sell MFE — consistent with broker side."""
    bid = float(pos.get("bid") or pos.get("price_current") or pos.get("open_price"))
    ask = float(pos.get("ask") or pos.get("price_current") or pos.get("open_price"))
    return bid if direction == "buy" else ask


def manage_one(cfg: dict, db_path: Path, pos: dict) -> None:
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None or row["stage"] == "closed":
        return
    favorable = _favorable_price(row["direction"], pos)
    # Stage 1: BE move (only when stage == 'init')
    if row["stage"] == "init":
        target = compute_be_target(row, cfg, favorable)
        if target is not None:
            attempt_modify(cfg, db_path, pos, new_sl=target,
                           reason="be_r", stage_to="be_armed")
            return
    # Stage 2: Chandelier trail (when stage in {'be_armed', 'trailing'})
    if row["stage"] in {"be_armed", "trailing"}:
        bars = _recent_bars(cfg, pos["symbol"],
                            cfg["manager"].get("chandelier_timeframe", "M5"),
                            int(cfg["manager"].get("chandelier_extreme_lookback", 22)) + 5)
        if not bars:
            return
        new_sl = compute_chandelier(bars, direction=row["direction"], cfg=cfg)
        if new_sl is None:
            return
        attempt_modify(cfg, db_path, pos, new_sl=new_sl,
                       reason="chandelier", stage_to="trailing")


def loop_once(cfg: dict, db_path: Path = DB_PATH) -> None:
    state_db.heartbeat_upsert(db_path, "manager", pid=os.getpid())
    positions = list_positions(cfg)
    if not positions:
        return
    account = _account_login(cfg)
    magics = poc_magics(cfg)
    for pos in positions:
        if pos.get("magic") not in magics:
            continue
        # Bootstrap (idempotent if already in state.db)
        bootstrap_position(cfg, db_path, pos, account=account)
        infer_stage_after_bootstrap(cfg, db_path, pos)
        manage_one(cfg, db_path, pos)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest adaptive-forex-mt5/tests -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add adaptive-forex-mt5/trade_manager.py adaptive-forex-mt5/tests/test_loop_once.py
git commit -m "Wire trade_manager.loop_once: heartbeat + bootstrap + BE + Chandelier"
```

---

## Task 16: Dashboard — managed positions section

**Files:**
- Modify: `adaptive-forex-mt5/dashboard.py`

- [ ] **Step 1: Read current dashboard.py to find HTML render anchor**

Run: `head -80 adaptive-forex-mt5/dashboard.py`

- [ ] **Step 2: Add managed-positions section to dashboard render**

In `adaptive-forex-mt5/dashboard.py`, find the existing HTML render (likely
a function like `_render_html` or inline in a request handler). Add a new
section that calls into state_db. Insert near the other top-level
sections:

```python
import state_db as _state_db
from pathlib import Path as _Path

_STATE_DB = _Path(__file__).resolve().parent / "state.db"


def _render_managed_positions() -> str:
    if not _STATE_DB.exists():
        return "<section><h2>Managed positions</h2><p>state.db not initialized.</p></section>"
    rows = _state_db.list_managed_positions(_STATE_DB, only_active=True)
    if not rows:
        return "<section><h2>Managed positions</h2><p>None.</p></section>"
    parts = ['<section><h2>Managed positions</h2><table>']
    parts.append("<tr><th>Ticket</th><th>Symbol</th><th>Dir</th><th>Stage</th>"
                 "<th>Entry</th><th>Init SL</th><th>Cur SL</th><th>Pending</th></tr>")
    for r in rows:
        cur_sl = r["last_sl_set"] if r["last_sl_set"] is not None else r["initial_sl"]
        pending = r["pending_action"] or ""
        parts.append(
            f"<tr><td>{r['ticket']}</td><td>{r['symbol']}</td>"
            f"<td>{r['direction']}</td><td>{r['stage']}</td>"
            f"<td>{r['entry_price']:.{r['digits']}f}</td>"
            f"<td>{r['initial_sl']:.{r['digits']}f}</td>"
            f"<td>{cur_sl:.{r['digits']}f}</td>"
            f"<td>{pending}</td></tr>"
        )
    parts.append("</table></section>")
    return "".join(parts)
```

Then call `_render_managed_positions()` from the main HTML composition
(wherever the existing sections are concatenated).

- [ ] **Step 3: Smoke-test the page renders**

Manually:
1. Start dashboard: `python adaptive-forex-mt5/dashboard.py`
2. Open `http://127.0.0.1:8765/`
3. Confirm "Managed positions" section appears (empty if no positions).

- [ ] **Step 4: Commit**

```bash
git add adaptive-forex-mt5/dashboard.py
git commit -m "Dashboard: add managed positions section"
```

---

## Task 17: Dashboard — heartbeat panel + unmanaged banner

**Files:**
- Modify: `adaptive-forex-mt5/dashboard.py`

- [ ] **Step 1: Add heartbeat panel + unmanaged banner**

In `adaptive-forex-mt5/dashboard.py`, append two more render helpers:

```python
import datetime as _dt


def _render_heartbeat() -> str:
    if not _STATE_DB.exists():
        return ""
    rows = _state_db.heartbeat_all(_STATE_DB)
    if not rows:
        return ""
    now = _dt.datetime.now(_dt.timezone.utc)
    parts = ['<section><h2>Process heartbeat</h2><table>']
    parts.append("<tr><th>Process</th><th>PID</th><th>Last seen</th><th>Status</th></tr>")
    for r in rows:
        try:
            last = _dt.datetime.fromisoformat(r["last_seen"])
            age = (now - last).total_seconds()
        except Exception:
            age = float("inf")
        # Threshold: 2x the loop_seconds for the manager (default 1s); use 10s as
        # a generic floor for processes whose loop is slower (agent at 60s, dashboard at 5s).
        floor = 10 if r["process"] == "manager" else 120
        ok = age <= floor
        color = "green" if ok else "red"
        parts.append(
            f"<tr><td>{r['process']}</td><td>{r.get('pid','')}</td>"
            f"<td>{r['last_seen']}</td>"
            f"<td style='color:{color}'>{'OK' if ok else 'STALE'}</td></tr>"
        )
    parts.append("</table></section>")
    return "".join(parts)


def _render_unmanaged_banner() -> str:
    """Render a red banner if any managed_position has a fresh
    last_unmanaged_warning_ts (within 60s)."""
    if not _STATE_DB.exists():
        return ""
    rows = _state_db.list_managed_positions(_STATE_DB)
    fresh = []
    now = _dt.datetime.now(_dt.timezone.utc)
    for r in rows:
        ts = r.get("last_unmanaged_warning_ts")
        if not ts:
            continue
        try:
            dt = _dt.datetime.fromisoformat(ts)
            if (now - dt).total_seconds() <= 60:
                fresh.append(r)
        except Exception:
            pass
    if not fresh:
        return ""
    items = "; ".join(f"{r['symbol']}#{r['ticket']}" for r in fresh)
    return (f"<div style='background:#7f1d1d;color:white;padding:8px'>"
            f"⚠ Unmanaged poc-magic positions: {items}</div>")
```

Wire both into the main page render (banner at the very top, heartbeat
panel near managed positions).

- [ ] **Step 2: Smoke-test**

Manually verify the page renders without errors when state.db has rows
seeded by trade_manager.

- [ ] **Step 3: Commit**

```bash
git add adaptive-forex-mt5/dashboard.py
git commit -m "Dashboard: add heartbeat panel + unmanaged-poc-position banner"
```

---

## Task 18: Config additions — manager + reviewer keys

**Files:**
- Modify: `adaptive-forex-mt5/config.example.json`
- Modify: `adaptive-forex-mt5/config.json`

- [ ] **Step 1: Update config.example.json**

Replace `adaptive-forex-mt5/config.example.json` with the merged config:

```json
{
  "pairs": ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"],

  "agent": {
    "scan_interval_seconds": 60,
    "outcome_poll_seconds": 30,
    "volume": 0.001,
    "strategy_id_prefix": "ehukai-poc",
    "alerts_only": true,
    "review_enabled": true,
    "reviewer_agent": "ClaudeReviewer",
    "min_quality_score": 0.85,
    "min_rr": 3.0,
    "min_stop_points": 80,
    "max_fvg_age_bars": 40,
    "max_concurrent_positions": 50,
    "max_trades_per_day": 500
  },

  "manager": {
    "enabled": true,
    "loop_seconds": 1,
    "be_trigger_r": 0.80,
    "be_buffer_points": 5,
    "be_trigger_points_fallback": 80,
    "chandelier_atr_period": 22,
    "chandelier_atr_multiplier": 3.0,
    "chandelier_extreme_lookback": 22,
    "chandelier_timeframe": "M5",
    "min_sl_improvement_points": 5,
    "max_spread_points": 100,
    "modify_cooldown_seconds": 5,
    "allow_tp_removal": false
  },

  "ntfy": {
    "topic": "adaptive-forex-mt5",
    "url": "https://ntfy.sh"
  },

  "dashboard": {
    "bind_host": "127.0.0.1",
    "bind_port": 8765,
    "refresh_seconds": 5
  },

  "mt5_cli": {
    "command": "mt5",
    "live": false,
    "subprocess_timeout_seconds": 60
  }
}
```

- [ ] **Step 2: Merge into config.json**

Operator's `config.json` is gitignored. The implementer should manually
merge the new `manager` block + `agent.review_enabled` + `agent.reviewer_agent`
keys into the operator's local config.json without disturbing existing
overrides.

(If running this plan from a fresh clone, copy config.example.json to
config.json.)

- [ ] **Step 3: Commit**

```bash
git add adaptive-forex-mt5/config.example.json
git commit -m "Config: add manager block + agent review_enabled/reviewer_agent keys"
```

---

## Task 19: README — document trade_manager + reviewer launch

**Files:**
- Modify: `adaptive-forex-mt5/README.md`

- [ ] **Step 1: Add launch + management section to README**

Append to `adaptive-forex-mt5/README.md`:

````markdown
## Process layout (phase 1)

Three Python processes plus one persistent reviewer agent:

```powershell
cd C:\Users\arsen\OneDrive\Desktop\AI-Applications\Metatrader5-CLI\adaptive-forex-mt5
Start-Process powershell -ArgumentList '-NoExit','-Command','python dashboard.py'
Start-Process powershell -ArgumentList '-NoExit','-Command','python agent.py'
Start-Process powershell -ArgumentList '-NoExit','-Command','python trade_manager.py'
```

Then register the reviewer agent (one-time):

```powershell
ehukaiconnect agent create ClaudeReviewer --type reviewer --skill .ehukaiconnect/skills/ClaudeReviewer/SKILL.md
```

The reviewer agent's terminal must be launched separately (per your
ehukaiconnect platform docs); it reads its skill and waits for
`dispatch_wake` events.

## Trade manager (replaces AdaptiveTrailEA for our magics)

`trade_manager.py` replaces the EA for any position with a poc-magic
(derived from `cfg.pairs` + `cfg.agent.strategy_id_prefix`). It runs a
1-second loop:

1. Heartbeat upsert to `state.db`.
2. List MT5 positions, filter to poc-magic set.
3. For each: bootstrap from `trades.jsonl`, infer stage from current SL,
   then run BE-move (R-based) → Chandelier trail (ATR(22) × 3.0 on M5).

Manual trades (magic=0) are NEVER touched by the manager. Phase 3 will
add an explicit allowlist for adopting them.

The manager is fail-closed: a poc-magic position with no journal
placement record is logged as `kind=unmanaged_poc_position` and left
alone. Dashboard shows a red banner so silent failures are visible.

## LLM review pipeline (advisory only)

On every READY alert, `agent.py` writes the alert payload to
`.ehukaiconnect/shared/files/alerts/<alert_id>.json` and creates an
`ehukaiconnect` task assigned to `ClaudeReviewer`. The reviewer wakes,
runs `mt5 ehukai topdown / rates / screenshot`, and emits a verdict
(take / skip / adjust) into `.ehukaiconnect/shared/files/verdicts/`.
`agent.py` polls closed tasks each loop, journals
`kind=llm_verdict`, and pushes an enriched ntfy.

Reviewer verdicts are advisory. They never modify orders.
````

- [ ] **Step 2: Commit**

```bash
git add adaptive-forex-mt5/README.md
git commit -m "README: document trade_manager + reviewer launch and roles"
```

---

## Task 20: e2e test extension — managed-position lifecycle

**Files:**
- Modify: `adaptive-forex-mt5/test_e2e.py`

- [ ] **Step 1: Add a fourth scenario**

Append to `adaptive-forex-mt5/test_e2e.py` (after the existing scenarios,
before the `main()` argparse handling):

```python
def scenario_managed_lifecycle(cfg: dict) -> None:
    """Open a tiny micro-lot position, run trade_manager.loop_once a few
    times, verify state.db tracks it and BE/Chandelier targets compute.
    Closes the position at the end. Live-gated."""
    import trade_manager
    import state_db

    db = trade_manager.DB_PATH
    state_db.init(db)

    sym = "USDJPY"
    print(f"[e2e] managed_lifecycle: opening 0.001 buy on {sym}")
    res = subprocess.run(
        [cfg["mt5_cli"]["command"], "--live", "--json", "order", "market",
         sym, "buy", "0.001", "--magic", str(agent.derive_magic(
             f"{cfg['agent']['strategy_id_prefix']}-{sym}"
         ))],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, res.stderr
    placed = json.loads(res.stdout)
    ticket = placed["data"]["placement"]["ticket"]
    journal.log_placement(sym, placed)

    try:
        for _ in range(3):
            trade_manager.loop_once(cfg, db)
            time.sleep(1)
        rows = state_db.list_managed_positions(db, only_active=True)
        managed = [r for r in rows if r["ticket"] == ticket]
        assert len(managed) == 1, f"expected 1 managed row for ticket {ticket}, got {rows}"
        print(f"[e2e] managed_lifecycle: state.db has ticket={ticket} stage={managed[0]['stage']}")
    finally:
        # Close the position regardless of outcome
        subprocess.run(
            [cfg["mt5_cli"]["command"], "--live", "--json", "position", "close",
             "--ticket", str(ticket)],
            capture_output=True, text=True, timeout=60,
        )
```

Add a CLI flag and dispatch:

```python
parser.add_argument("--managed", action="store_true",
                    help="Run managed-lifecycle scenario (requires --allow-live)")
# ... in main():
if args.managed:
    if not args.allow_live:
        sys.exit("--managed requires --allow-live")
    scenario_managed_lifecycle(cfg)
```

- [ ] **Step 2: Smoke-run on demo**

Operator runs (after setting `mt5_cli.live=true` in config.json on the demo
account):

```
python adaptive-forex-mt5/test_e2e.py --allow-live --managed
```

Expected: a 0.001 USDJPY buy is opened, three manager loops execute,
state.db has the ticket tracked, then the position is closed.

- [ ] **Step 3: Commit**

```bash
git add adaptive-forex-mt5/test_e2e.py
git commit -m "test_e2e: add managed-lifecycle scenario behind --managed --allow-live"
```

---

## Self-Review

After all tasks are complete, run:

```
pytest adaptive-forex-mt5/tests metatrader5_cli/mt5/tests -v
```

Expected: all green. The existing 216 CLI tests must still pass.

**Spec coverage check** (cross against
`docs/superpowers/specs/2026-05-08-bot-managed-trades-and-llm-review-design.md`):

| Spec section | Plan task |
|---|---|
| state.db schema | Task 3 |
| journal kinds (llm_verdict, manage_action, manage_skip, unmanaged_poc_position, review_request) | Task 2 |
| setup_fingerprint | Task 4 |
| dispatch_review hook | Task 7 |
| verdict poller | Task 8 |
| ClaudeReviewer skill | Task 6 |
| trade_manager.py skeleton + heartbeat | Task 9 |
| poc-magic derivation | Task 10 |
| Bootstrap two-phase + fail-closed + warning | Task 10 |
| Stage inference (never loosen) | Task 11 |
| BE-move | Task 12 |
| Chandelier trail | Task 13 |
| Confirm-before-promote | Task 14 |
| Live-intent gate | Task 14 |
| loop_once integration | Task 15 |
| Dashboard managed positions | Task 16 |
| Dashboard heartbeat | Task 17 |
| Dashboard unmanaged banner | Task 17 |
| Config keys | Task 18 |
| README | Task 19 |
| e2e managed-lifecycle | Task 20 |

Phase 2 (autopilot consensus) is OUT of scope for this plan — separate plan
to follow once phase 1 is shipped and a few days of `kind=llm_verdict`
records have accumulated.

---

## Plan complete

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-trade-manager-and-llm-review.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
