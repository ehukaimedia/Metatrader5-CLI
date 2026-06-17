"""Project a native in-sample optimization report into per-pass records.

``results.parse_optimization_xml`` yields each ``<pass>``'s child tags as a flat
dict (tag -> scalar). This module projects the columns the feature needs: the EA
input parameters (by name) and the in-sample metrics. Pure / stdlib-only.

Column tag names
----------------
``ProfitFactor``, ``Trades``, and ``Profit`` match the repo's canonical
``tests/fixtures/sample_optimization.xml`` and the shape
``results.parse_optimization_xml`` reads. ``Sharpe`` is provisional — the
canonical fixture has no Sharpe column and real MT5 may name it differently, so
in-sample sharpe is ``None`` until confirmed. The real report shape is verified
in plan Task 0; if tag names differ, adjust the four constants below — the
projection/selection logic is unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.tester import results

#: ProfitFactor/Trades/Profit match tests/fixtures/sample_optimization.xml;
#: Sharpe is provisional (absent there). Confirm against a real capture (Task 0).
_PF = "ProfitFactor"
_TRADES = "Trades"
_SHARPE = "Sharpe"
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
