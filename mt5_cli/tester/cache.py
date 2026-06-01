"""Per-run snapshot cache under <results_root>/<run-id>/.

Each tester invocation gets a deterministic run_id like
`2026-05-15T14-22-05_alpha_AUDUSD_M5`. The run dir holds the .ini that
drove terminal64, the report.html, the journal.csv, and (for optimize
runs) the optimization.xml — everything an agent needs to reconstruct
or re-analyze the run.

Bridge isolation: pure filesystem; no MT5 SDK access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def make_run_id(
    expert: str,
    symbol: str,
    timeframe: str,
    *,
    at: datetime | None = None,
) -> str:
    """Build a sortable run id: 'YYYY-MM-DDTHH-MM-SS_<expert>_<symbol>_<tf>'.

    The timestamp is UTC at second resolution so directory names sort
    chronologically and remain filesystem-safe on Windows (no `:`).
    """
    at = at or datetime.now(timezone.utc)
    stamp = at.strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{expert}_{symbol}_{timeframe}"


def run_dir(run_id: str, *, root: Path | str = "results") -> Path:
    """Return (and create if missing) the dir for `run_id` under `root`."""
    p = Path(root) / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_recent(*, root: Path | str = "results", limit: int = 20) -> list[dict]:
    """Return up to `limit` most-recent run dirs, newest first.

    Since run_ids are ISO-stamped and lex-sortable, the chronological
    order is just `sorted(..., reverse=True)`.
    """
    rp = Path(root)
    if not rp.exists():
        return []
    dirs = sorted(
        (d for d in rp.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )[:limit]
    return [{"run_id": d.name, "path": str(d)} for d in dirs]


def get_run(run_id: str, *, root: Path | str = "results") -> dict | None:
    """Return {run_id, path} when the run dir exists, else None."""
    p = Path(root) / run_id
    if not p.exists():
        return None
    return {"run_id": run_id, "path": str(p)}
