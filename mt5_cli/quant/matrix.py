"""Pure matrix expansion, split-date resolution, and param validation.

Stdlib-only; no MetaTrader5, no filesystem (the bridge-isolation rule the
tester package follows). Input errors are typed ``ValueError`` subclasses so the
campaign layer can map each to its envelope code without string-matching.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from mt5_cli.tester import ini_builder


class MatrixError(ValueError):
    """Base for matrix input errors (a ValueError so callers can catch broadly)."""


class EmptyMatrix(MatrixError):
    """No symbols or no timeframes."""


class InvalidSplit(MatrixError):
    """--split is neither a 0<f<1 fraction nor a valid in-range date."""


class InvalidParam(MatrixError):
    """A --param spec is malformed."""


def expand(symbols: list[str], timeframes: list[str]) -> list[tuple[str, str]]:
    """Ordered, de-duplicated (symbol, timeframe) cells. Raises EmptyMatrix if either is empty."""
    syms = list(dict.fromkeys(s.strip() for s in symbols if s and s.strip()))
    tfs = list(dict.fromkeys(t.strip() for t in timeframes if t and t.strip()))
    if not syms or not tfs:
        raise EmptyMatrix("A quant campaign needs at least one symbol and one timeframe.")
    return [(s, t) for s in syms for t in tfs]


def resolve_split(from_date: str, to_date: str, split: str) -> str:
    """Return the first out-of-sample day (YYYY-MM-DD).

    A ``0<f<1`` fraction resolves to ``from + floor(f*(to-from))`` days; an
    explicit ``YYYY-MM-DD`` strictly after ``from`` and on/before ``to`` is used
    as-is. Anything else raises InvalidSplit.
    """
    try:
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except (ValueError, TypeError) as exc:
        raise InvalidSplit(f"--from/--to must be YYYY-MM-DD: {exc}") from exc
    if end <= start:
        raise InvalidSplit("--from must precede --to.")

    if "-" in str(split):  # a date never... a fraction never contains '-'
        try:
            boundary = date.fromisoformat(split)
        except (ValueError, TypeError) as exc:
            raise InvalidSplit("--split must be a 0<f<1 fraction or a YYYY-MM-DD date.") from exc
    else:
        try:
            frac = float(split)
        except (ValueError, TypeError) as exc:
            raise InvalidSplit("--split must be a 0<f<1 fraction or a YYYY-MM-DD date.") from exc
        if not (0.0 < frac < 1.0):
            raise InvalidSplit("--split fraction must be 0<f<1.")
        boundary = start + timedelta(days=math.floor(frac * (end - start).days))

    if not (start < boundary <= end):
        raise InvalidSplit("--split must fall after --from and on/before --to.")
    return boundary.isoformat()


def is_end(split: str) -> str:
    """Last in-sample day = the day before the (first-OOS) split day."""
    return (date.fromisoformat(split) - timedelta(days=1)).isoformat()


def param_names(specs: list[str]) -> list[str]:
    """Extract the parameter names from ``NAME=...`` specs."""
    return [spec.split("=", 1)[0].strip() for spec in specs if "=" in spec]


def parse_params(specs: list[str]) -> list[str]:
    """Validate each ``NAME=value[,start,step,stop]`` spec via the .set grammar."""
    try:
        ini_builder.render_set(list(specs))
    except ValueError as exc:
        raise InvalidParam(str(exc)) from exc
    return list(specs)
