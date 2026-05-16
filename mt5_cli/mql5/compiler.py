"""Compile MQL5 source via metaeditor64.exe.

Resolves the MetaEditor binary in this order:
  1. MT5_METAEDITOR_PATH env var
  2. Common Windows install paths (Program Files / Program Files (x86) / AppData)
  3. shutil.which('metaeditor64')

Bridge isolation: pure subprocess + filesystem; never touches the MT5
Python SDK (the bridge singleton is reserved for the MetaTrader5 package).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mt5_cli.reports import fail, ok

# Module-level so tests can monkeypatch via `compiler._CANDIDATE_PATHS`.
_CANDIDATE_PATHS: list[Path] = [
    Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe"),
    Path(os.path.expanduser(
        r"~\AppData\Roaming\MetaQuotes\Terminal\Common\Files\metaeditor64.exe"
    )),
]


def locate_metaeditor() -> Path | None:
    """Find metaeditor64.exe. Returns None if no candidate exists."""
    env = os.environ.get("MT5_METAEDITOR_PATH")
    if env and Path(env).exists():
        return Path(env)
    for p in _CANDIDATE_PATHS:
        if p.exists():
            return p
    found = shutil.which("metaeditor64")
    return Path(found) if found else None


def _parse_log(log_path: Path) -> tuple[int, int, str]:
    """Returns (errors, warnings, full_text) from a MetaEditor log file.

    MetaEditor writes the compile log in UTF-16-LE by default (BOM
    \\xff\\xfe). Fall back to UTF-8 for the rare BOM-less log.
    """
    if not log_path.exists():
        return 0, 0, ""
    raw = log_path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    errors = sum(
        1 for line in text.splitlines()
        if "error" in line.lower() and " - " in line
    )
    warnings = sum(
        1 for line in text.splitlines()
        if "warning" in line.lower() and " - " in line
    )
    return errors, warnings, text


def compile_source(
    src: Path | str,
    *,
    include_dir: Path | None = None,
    timeout: int = 120,
) -> dict:
    """Compile a single .mq5 file via metaeditor64.exe.

    Returns the standard JSON envelope:

    Success:
      ok({"source": str, "ex5": str, "errors": int, "warnings": int,
          "log_path": str})

    Failure codes:
      SOURCE_NOT_FOUND     - the .mq5 path does not exist
      METAEDITOR_NOT_FOUND - no metaeditor64.exe via env/candidates/which
      COMPILE_TIMEOUT      - subprocess exceeded `timeout` seconds
      COMPILE_FAILED       - MetaEditor reported errors OR no .ex5 produced
    """
    src = Path(src).resolve()
    if not src.exists():
        return fail("SOURCE_NOT_FOUND", f"Source file not found: {src}")
    metaeditor = locate_metaeditor()
    if not metaeditor:
        return fail(
            "METAEDITOR_NOT_FOUND",
            "Could not locate metaeditor64.exe. Set MT5_METAEDITOR_PATH "
            "or install MT5.",
        )
    log_path = src.with_suffix(".log")
    cmd = [str(metaeditor), f"/compile:{src}", f"/log:{log_path}"]
    if include_dir:
        cmd.append(f"/inc:{include_dir}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return fail(
            "MQL5_COMPILE_TIMEOUT",
            f"metaeditor64.exe did not finish in {timeout}s",
        )
    errors, warnings, log_text = _parse_log(log_path)
    ex5 = src.with_suffix(".ex5")
    # Re-grade the result with three signals (live E2E proved
    # returncode alone is unreliable - MetaEditor exits 1 even on
    # warnings-only successful builds that DO produce an .ex5):
    #   1. error_count from the parsed log
    #   2. .ex5 existence
    #   3. .ex5 freshness vs the source mtime - keeps the P1
    #      protection against a stale .ex5 from a prior compile
    #      masking the current run's failure.
    # Success requires all three to be good: errors=0 AND .ex5 exists
    # AND .ex5 mtime >= source mtime.
    ex5_present = ex5.exists()
    ex5_fresh = (
        ex5_present
        and ex5.stat().st_mtime >= src.stat().st_mtime
    )
    if errors or not ex5_present or not ex5_fresh:
        reason_parts = [f"{errors} errors", f"{warnings} warnings"]
        if not ex5_present:
            reason_parts.append("no .ex5 produced")
        elif not ex5_fresh:
            reason_parts.append(".ex5 is stale (mtime < source)")
        return fail(
            "MQL5_COMPILE_FAILED",
            ", ".join(reason_parts) + f" (metaeditor exit={proc.returncode})",
            data={
                "log": log_text,
                "exit_code": proc.returncode,
                "stderr": proc.stderr or "",
            },
        )
    return ok({
        "source": str(src),
        "ex5": str(ex5),
        "errors": errors,
        "warnings": warnings,
        "log_path": str(log_path),
        "exit_code": proc.returncode,
    })
