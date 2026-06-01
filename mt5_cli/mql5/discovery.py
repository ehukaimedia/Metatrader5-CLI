"""Auto-discover user MQL5 EAs and indicators.

Search order (first match wins):
  1. ./ea/ or ./indicators/ (current working directory where the user
     runs `mt5`)
  2. ~/.local/share/metatrader5-cli/ea/ or /indicators/ (XDG_DATA_HOME
     convention; %APPDATA%/metatrader5-cli/ on Windows)

The fallback root is XDG_DATA_HOME-style (~/.local/share/...) NOT the
config dir, since EAs/indicators are user-authored DATA, not settings.

Bridge isolation: pure filesystem; never touches the MT5 Python SDK.
"""
from __future__ import annotations

import os
from pathlib import Path

# Kinds map to the directory names users see on disk.
_KIND_DIRS = {"ea": "ea", "indicators": "indicators"}


def _search_paths(kind: str) -> list[Path]:
    """Return the ordered list of existing search roots for `kind`.

    `kind` is 'ea' or 'indicators'. Non-existent roots are filtered so
    callers can iterate without per-path existence checks.
    """
    subdir = _KIND_DIRS.get(kind, kind)
    cwd = Path.cwd() / subdir
    user = (
        Path(os.path.expanduser("~"))
        / ".local" / "share" / "metatrader5-cli" / subdir
    )
    return [p for p in (cwd, user) if p.exists()]


def _list(kind: str) -> list[dict]:
    """Enumerate .mq5 sources under all search roots for `kind`.

    First-match-wins: if the same name appears in CWD and the user dir,
    only the CWD entry is returned.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for root in _search_paths(kind):
        for src in sorted(root.rglob("*.mq5")):
            name = src.stem
            if name in seen:
                continue
            seen.add(name)
            out.append({
                "name": name,
                "source": str(src),
                "compiled": src.with_suffix(".ex5").exists(),
            })
    return out


def _get(kind: str, name: str) -> dict | None:
    """Look up a specific .mq5 by name across search roots, first match wins."""
    for root in _search_paths(kind):
        # Direct hit at the root.
        candidate = root / f"{name}.mq5"
        if candidate.exists():
            return {
                "name": name,
                "source": str(candidate),
                "compiled": candidate.with_suffix(".ex5").exists(),
            }
        # Nested hit (e.g., examples/<name>.mq5). rglob returns generator;
        # take the first match within this root before falling through to
        # the next root.
        for src in root.rglob(f"{name}.mq5"):
            return {
                "name": name,
                "source": str(src),
                "compiled": src.with_suffix(".ex5").exists(),
            }
    return None


def list_eas() -> list[dict]:
    return _list("ea")


def list_indicators() -> list[dict]:
    return _list("indicators")


def get_ea(name: str) -> dict | None:
    return _get("ea", name)


def get_indicator(name: str) -> dict | None:
    return _get("indicators", name)
