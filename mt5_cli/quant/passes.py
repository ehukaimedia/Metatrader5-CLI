"""Project a native in-sample optimization report into per-pass records.

``results.parse_optimization_xml`` yields one dict per optimization pass (from
MT5's SpreadsheetML report — column header -> value). This module projects the
columns the feature needs: the EA input parameters (by name) and the in-sample
metrics. Pure / stdlib-only.

Column names (verified against real MT5)
----------------------------------------
Captured by dog-fooding a live optimization (plan Task 0, now closed): MT5 writes
a SpreadsheetML report whose pass columns are ``Profit Factor``, ``Sharpe Ratio``,
``Trades``, ``Profit`` (net), ``Result`` (final balance), plus the EA input
parameters. These are spreadsheet headers, so they contain spaces.
``results.parse_optimization_xml`` parses that shape;
``tests/fixtures/sample_optimization.xml`` is a trimmed real capture.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.tester import results

#: Real MT5 optimization-report column headers (spreadsheet columns -> spaces),
#: confirmed by a live capture. See tests/fixtures/sample_optimization.xml.
_PF = "Profit Factor"
_TRADES = "Trades"
_SHARPE = "Sharpe Ratio"
_NET = "Profit"


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
