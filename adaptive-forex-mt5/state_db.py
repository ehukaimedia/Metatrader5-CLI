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
        # SQLite reports the partial-index conflict by listing the indexed
        # columns rather than the index name, so match on either form.
        msg = str(e)
        if "active_pos_uniq" in msg or (
            "managed_position.account" in msg
            and "managed_position.symbol" in msg
            and "managed_position.magic" in msg
        ):
            raise DuplicateActiveError(msg) from e
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
