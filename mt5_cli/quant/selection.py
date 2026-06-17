"""Pure winner selection and cross-cell ranking. The tester/stress.py analog.

Two distinct operations:
- ``pick_winner`` chooses an optimization pass by an IN-SAMPLE criterion (it runs
  before any FULL re-run exists), so it can never use full_net.
- ``gate_and_rank`` orders the assembled cells AFTER their FULL/OOS metrics exist.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: rank key -> selector over an assembled cell. full_net is the default; the
#: oos_* keys are opt-in and flag a drift caveat.
_RANK_KEYS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "full_net": lambda c: (c.get("full") or {}).get("net_profit"),
    "oos_sharpe": lambda c: (c.get("oos") or {}).get("sharpe"),
    "oos_pf": lambda c: (c.get("oos") or {}).get("profit_factor"),
}
_OOS_KEYS = {"oos_sharpe", "oos_pf"}


def pick_winner(passes: list[dict[str, Any]], *, min_pf: float) -> dict[str, Any] | None:
    """Best in-sample pass clearing ``min_pf``, by in-sample profit factor.

    Returns None when no pass clears the gate (the cell is then rejected
    NO_WINNER). Never consults full_net — that does not exist at selection time.
    """
    def _pf(p: dict[str, Any]) -> float | None:
        v = (p.get("is") or {}).get("profit_factor")
        return float(v) if isinstance(v, (int, float)) else None

    # require a NUMERIC in-sample PF >= min_pf; a missing PF never qualifies
    # (so "report has no PF column" correctly yields no winner -> NO_WINNER).
    qualified = [p for p in passes if (pf := _pf(p)) is not None and pf >= min_pf]
    if not qualified:
        return None
    return max(qualified, key=lambda p: float(p["is"]["profit_factor"]))


def gate_and_rank(cells: list[dict[str, Any]], *, min_trades: int, oos_min_pf: float,
                  rank_by: str, per_asset: int) -> dict[str, Any]:
    """Gate assembled cells, rank survivors by ``rank_by``, cap per asset."""
    if rank_by not in _RANK_KEYS:
        raise ValueError("--rank-by must be one of full_net, oos_sharpe, oos_pf.")

    survivors: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for c in cells:
        full_trades = (c.get("full") or {}).get("trades") or 0
        if full_trades < min_trades:
            rejected.append({"symbol": c["symbol"], "timeframe": c["timeframe"],
                             "reason": "MIN_TRADES",
                             "full": {"trades": (c.get("full") or {}).get("trades")}})
            continue
        oos_pf = (c.get("oos") or {}).get("profit_factor")
        c["validated"] = isinstance(oos_pf, (int, float)) and oos_pf >= oos_min_pf
        survivors.append(c)

    key = _RANK_KEYS[rank_by]

    def _sort_key(c: dict[str, Any]) -> float:
        v = key(c)
        return v if isinstance(v, (int, float)) else float("-inf")

    survivors.sort(key=_sort_key, reverse=True)

    ranked: list[dict[str, Any]] = []
    capped: list[dict[str, Any]] = []
    per_asset_count: dict[str, int] = {}
    for c in survivors:
        n = per_asset_count.get(c["symbol"], 0) + 1
        per_asset_count[c["symbol"]] = n
        if n <= per_asset:
            c["rank"] = len(ranked) + 1
            ranked.append(c)
        else:
            # passed every gate but trimmed by --per-asset; surfaced (not dropped
            # silently, not "rejected") so the campaign output stays complete.
            capped.append({"symbol": c["symbol"], "timeframe": c["timeframe"]})

    return {
        "ranked": ranked,
        "rejected": rejected,
        "capped": capped,
        "rank_caveat": "oos_metric_can_reflect_asset_drift" if rank_by in _OOS_KEYS else None,
    }
