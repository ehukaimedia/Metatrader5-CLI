"""Delay-ladder parsing and robustness scoring for the stress matrix.

Pure and stdlib-only: it turns trader-facing delay tokens into MT5
ExecutionMode values, normalizes the ladder, and grades how much profit
survives execution delay. No filesystem, no launcher, no MT5 SDK — the
orchestration in `ea.py` feeds it already-parsed numbers.

A delay token is a non-negative millisecond integer or the word ``random``
(MT5's randomized-delay mode, ExecutionMode -1). The robustness score is the
worst-case profit retention across the stressed rungs, clamped to [0, 1]: a
gate must fail on the worst path, never average a collapse away.
"""
from __future__ import annotations

from typing import Any

# Verdict bands on the worst-case retention score.
_ROBUST_AT = 0.85
_DEGRADED_AT = 0.50

# Mirrors the ExecutionMode ceiling enforced in ini_builder.
_RANDOM = -1
_MAX_FIXED_MS = 600000


def _validate_ladder_value(value: int) -> int:
    """Enforce the single delay contract: -1 (random) or a 0..600000 ms integer.

    This is the one gate both the string path (`parse_delays`) and the typed
    library path (`normalize_ladder`) run through, so a direct
    `ea.stress(delays=[...])` caller cannot bypass the range the CLI enforces.
    """
    if value != _RANDOM and not (0 <= value <= _MAX_FIXED_MS):
        raise ValueError(
            f"Invalid delay {value}. Use 'random' (-1) or an integer "
            f"0..{_MAX_FIXED_MS} ms."
        )
    return value


def parse_delays(spec: str) -> list[int]:
    """Parse ``"0,100,500,random"`` into ExecutionMode values ``[0, 100, 500, -1]``.

    Tokens are non-negative millisecond integers or ``random``. A literal
    negative, a non-numeric token, a value above the 600000 ms ceiling, or a
    no-token spec raises ValueError — ``random`` is the only way to request -1,
    and a stress run needs at least one rung.
    """
    delays: list[int] = []
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            continue
        if token.lower() == "random":
            delays.append(_RANDOM)
            continue
        try:
            value = int(token)
        except ValueError:
            raise ValueError(
                f"Invalid delay {token!r}. Use 'random' or an integer "
                f"0..{_MAX_FIXED_MS} ms."
            ) from None
        if value < 0:
            raise ValueError(
                f"Invalid delay {token!r}. Use 'random' for a random delay, "
                f"not a negative number."
            )
        delays.append(_validate_ladder_value(value))
    if not delays:
        raise ValueError("No delays given. Provide at least one rung, e.g. '0,100,random'.")
    return delays


def normalize_ladder(delays: list[int]) -> list[int]:
    """Dedupe and order a ladder: baseline 0 first, fixed delays ascending, random last.

    Every value is validated against the -1 / 0..600000 contract, and an empty
    ladder is rejected — the typed library path gets the same guarantees as the
    CLI. The ideal-execution baseline (0) is always present (it anchors every
    retention ratio), so it is prepended when missing. The order is
    deterministic so the resulting envelope is too.
    """
    if not delays:
        raise ValueError("No delays given. Provide at least one rung, e.g. [0, 100, -1].")
    for value in delays:
        _validate_ladder_value(value)
    unique = set(delays)
    unique.add(0)
    fixed = sorted(d for d in unique if d >= 0)
    has_random = _RANDOM in unique
    return fixed + ([_RANDOM] if has_random else [])


def _verdict(score: float | None) -> str:
    if score is None:
        return "ungraded"
    if score >= _ROBUST_AT:
        return "robust"
    if score >= _DEGRADED_AT:
        return "degraded"
    return "fragile"


def _detail_row(delay_ms: int, stats: dict[str, Any], retention: float) -> dict[str, Any]:
    return {
        "delay_ms": delay_ms,
        "net_profit": stats.get("net_profit"),
        "retention": retention,
        "profit_factor": stats.get("profit_factor"),
        "max_drawdown_pct": stats.get("max_drawdown_pct"),
        "total_trades": stats.get("total_trades"),
        "win_rate": stats.get("win_rate"),
    }


def score(
    *,
    baseline_net_profit: float | None,
    stressed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Grade execution robustness from the baseline and stressed-rung results.

    ``stressed`` is one dict per non-baseline rung: ``{"delay_ms": int,
    "stats": dict | None}``, where ``stats`` is the parsed stats of a
    successful run or None if that rung failed. The score is the worst-case
    ``net_profit / baseline_net_profit`` over successful rungs, clamped to
    [0, 1] and rounded to 4 dp. It is ungraded (None) when the baseline is
    missing or not positive — a losing baseline cannot anchor retention — or
    when no stressed rung succeeded. ``incomplete`` is true when any rung failed.
    """
    incomplete = False
    per_delay: list[dict[str, Any]] = []
    retentions: list[float] = []

    gradeable_baseline = baseline_net_profit is not None and baseline_net_profit > 0

    for rung in stressed:
        stats = rung.get("stats")
        net_profit = stats.get("net_profit") if stats else None
        if stats is None or net_profit is None:
            incomplete = True
            continue
        if gradeable_baseline:
            retention = round(net_profit / baseline_net_profit, 4)
            retentions.append(retention)
            per_delay.append(_detail_row(rung["delay_ms"], stats, retention))

    if not gradeable_baseline or not retentions:
        final_score: float | None = None
    else:
        final_score = round(min(1.0, max(0.0, min(retentions))), 4)

    return {
        "score": final_score,
        "verdict": _verdict(final_score),
        "baseline_net_profit": baseline_net_profit,
        "incomplete": incomplete,
        "per_delay": per_delay,
    }
