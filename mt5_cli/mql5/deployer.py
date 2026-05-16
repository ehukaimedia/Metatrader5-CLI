"""Copy compiled MQL5 artifacts to the MT5 terminal's Experts/ or Indicators/.

Terminal data dir is the per-instance Roaming dir like
%APPDATA%\\MetaQuotes\\Terminal\\<HASH>\\MQL5\\. We pick the newest one
under the candidate root (most recently modified hash dir that has an
MQL5/ subdir) which matches how MT5 keeps state across reinstalls.

Bridge isolation: pure filesystem; never touches the MT5 Python SDK.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from mt5_cli.reports import fail, ok

# Module-level so tests can monkeypatch via `deployer._CANDIDATE_DATA_DIRS`.
_CANDIDATE_DATA_DIRS: list[Path] = [
    Path(os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal")),
]


def resolve_terminal_data_dir() -> Path | None:
    """Find the active MT5 terminal data dir (the parent of MQL5/).

    Resolution order:
      1. MT5_TERMINAL_DATA_DIR env var (must point at the hash dir itself)
      2. Newest hash dir under %APPDATA%\\MetaQuotes\\Terminal\\ that has
         an MQL5/ subdir

    Returns None when no candidate is reachable.
    """
    env = os.environ.get("MT5_TERMINAL_DATA_DIR")
    if env:
        p = Path(env)
        return p if p.exists() else None
    for root in _CANDIDATE_DATA_DIRS:
        if not root.exists():
            continue
        # MT5 keeps each terminal install under a 32-char hash dir. Pick the
        # newest one that has an MQL5/ subdir.
        try:
            candidates = sorted(
                (d for d in root.iterdir()
                 if d.is_dir() and (d / "MQL5").exists()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            continue
        if candidates:
            return candidates[0]
    return None


def _deploy(src: Path | str, subdir: str) -> dict:
    """Copy `src` (.mq5) and its sibling `.ex5` (if any) to MQL5/<subdir>/.

    Failure codes:
      SOURCE_NOT_FOUND              - the .mq5 path does not exist
      TERMINAL_DATA_DIR_NOT_FOUND   - resolve_terminal_data_dir() returned None
      NOTHING_TO_DEPLOY             - neither .mq5 nor .ex5 sibling exists
    """
    src = Path(src).resolve()
    if not src.exists():
        return fail("SOURCE_NOT_FOUND", f"Source file not found: {src}")
    data_dir = resolve_terminal_data_dir()
    if not data_dir:
        return fail(
            "TERMINAL_DATA_DIR_NOT_FOUND",
            "Could not locate MT5 terminal data dir. Set "
            "MT5_TERMINAL_DATA_DIR or run MT5 at least once.",
        )
    dest_dir = data_dir / "MQL5" / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for ext in (".mq5", ".ex5"):
        candidate = src.with_suffix(ext)
        if candidate.exists():
            dest = dest_dir / candidate.name
            shutil.copy2(candidate, dest)
            copied.append(str(dest))
    if not copied:
        return fail(
            "NOTHING_TO_DEPLOY",
            f"Found no .mq5 or .ex5 sibling of {src}",
        )
    return ok({"copied": copied, "data_dir": str(data_dir)})


def deploy_ea(src: Path | str) -> dict:
    """Deploy `src` and its .ex5 sibling to <data_dir>/MQL5/Experts/."""
    return _deploy(src, "Experts")


def deploy_indicator(src: Path | str) -> dict:
    """Deploy `src` and its .ex5 sibling to <data_dir>/MQL5/Indicators/."""
    return _deploy(src, "Indicators")
