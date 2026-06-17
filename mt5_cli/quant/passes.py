"""Project a native in-sample optimization report into per-pass records.

``results.parse_optimization_xml`` yields each ``<pass>``'s child tags as a flat
dict (tag -> scalar). This module projects the columns the feature needs: the EA
input parameters (by name) and the in-sample metrics. Pure / stdlib-only.

PROVISIONAL column tag names
----------------------------
The metric tag names below are the *expected* MT5 optimization-report columns,
but they are unverified against a real artifact. Task 0 of the plan captures a
real ``optimization.xml``; if MT5's tag names differ, adjust these four
constants — nothing else changes. The projection/selection logic is what the
tests pin down; the exact tag strings are a one-line map.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.tester import results

#: PROVISIONAL — confirm against a captured optimization.xml (plan Task 0).
_PF = "ProfitFactor"
_TRADES = "Trades"
_SHARPE = "Sharpe"
_NET = "Result"


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_rows(parsed: list[dict[str, Any]], *, param_names: list[str]) -> list[dict[str, Any]]:
    """Project already-parsed optimization passes into {params, is} records."""
    rows: list[dict[str, Any]] = []
    for raw in parsed:
        rows.append({
            # project EVERY requested name: absent -> None (surfaced, not hidden),
            # so the campaign can refuse to build a .set from a missing input.
            "params": {n: (str(raw[n]) if n in raw else None) for n in param_names},
            "is": {
                "profit_factor": _as_float(raw.get(_PF)),
                "trades": _as_int(raw.get(_TRADES)),
                "sharpe": _as_float(raw.get(_SHARPE)),
                "net_profit": _as_float(raw.get(_NET)),
            },
        })
    return rows


def read(path: Path | str, *, param_names: list[str]) -> list[dict[str, Any]]:
    """Parse the in-sample optimization.xml at ``path`` and project its passes."""
    return read_rows(results.parse_optimization_xml(path), param_names=param_names)
