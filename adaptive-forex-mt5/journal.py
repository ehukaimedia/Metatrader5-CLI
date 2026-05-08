"""Append-only trade journal.

Each trade is one record in logs/trades.jsonl. Updates (e.g. outcome) are
appended as new records keyed by ticket; readers fold them on read.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
TRADES_FILE = LOGS / "trades.jsonl"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(record: dict) -> None:
    record.setdefault("ts", _ts())
    with open(TRADES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _reasoning(scan: dict) -> dict:
    """Extract the reasoning block from a sniper-poc scan dict."""
    if not scan:
        return {}
    return {
        "structure": scan.get("structure"),
        "poi": scan.get("poi"),
        "liquidity": scan.get("liquidity"),
        "entry": scan.get("entry"),
        "gates_passed": [g["name"] for g in (scan.get("gates") or []) if g.get("ok")],
        "gates_failed": [{"name": g["name"], "detail": g.get("detail")} for g in (scan.get("gates") or []) if not g.get("ok")],
        "explain": scan.get("explain"),
        "quality_score": scan.get("quality_score"),
        "bias_counts": scan.get("bias_counts"),
        "quote": scan.get("quote"),
    }


def log_placement(pair: str, placement: dict) -> None:
    """Record a successful order placement.

    Captures both the initial-scan and final-scan setup contracts so post-hoc
    analysis can see the reasoning that actually produced the placed entry/SL/TP
    (final scan), and compare against the first scan that triggered the place
    attempt (initial scan). The placement response from `mt5 order ready-limit`
    includes both internally.
    """
    data = placement.get("data") or {}
    initial = data.get("initial_setup") or {}
    final = data.get("final_setup") or initial
    final_order = final.get("setup") or {}
    placement_data = data.get("placement") or {}
    ticket = placement_data.get("ticket")
    magic = placement_data.get("magic")
    append({
        "kind": "placement",
        "pair": pair,
        "ticket": ticket,
        "magic": magic,
        "direction": final.get("direction") or initial.get("direction"),
        "entry": final_order.get("entry"),
        "sl": final_order.get("sl"),
        "tp": final_order.get("tp"),
        "rr": final_order.get("rr"),
        "volume": final_order.get("volume"),
        "strategy_id": data.get("strategy_id"),
        "reasoning": _reasoning(final),
        "initial_reasoning": _reasoning(initial) if initial is not final else None,
        "drift_points": data.get("drift_points") if isinstance(data.get("drift_points"), (int, float)) else None,
    })


def log_skip(pair: str, scan: dict | None) -> None:
    """Record a skip with the full setup contract for post-hoc false-negative review."""
    scan = scan or {}
    append({
        "kind": "skip",
        "pair": pair,
        "status": scan.get("status"),
        "direction": scan.get("direction"),
        "reason": scan.get("reason"),
        "reasoning": _reasoning(scan),
    })


def log_outcome(ticket: int, outcome: dict) -> None:
    """Record close / TP-hit / SL-hit / cancel for a placed ticket."""
    append({
        "kind": "outcome",
        "ticket": ticket,
        **outcome,
    })


def log_error(pair: str, where: str, error: dict | str) -> None:
    append({
        "kind": "error",
        "pair": pair,
        "where": where,
        "error": error,
    })


def read_all() -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    out = []
    for line in TRADES_FILE.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def folded_trades() -> list[dict]:
    """One row per ticket: placement + outcome merged."""
    by_ticket: dict[int, dict] = {}
    other: list[dict] = []
    for r in read_all():
        ticket = r.get("ticket")
        if r["kind"] == "placement" and ticket is not None:
            by_ticket[ticket] = {**r, "outcome": None}
        elif r["kind"] == "outcome" and ticket is not None and ticket in by_ticket:
            by_ticket[ticket]["outcome"] = r
        else:
            other.append(r)
    rows = list(by_ticket.values())
    rows.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return rows


def stats() -> dict:
    rows = folded_trades()
    closed = [r for r in rows if r.get("outcome")]
    open_ct = len(rows) - len(closed)
    wins = [r for r in closed if (r["outcome"].get("result") == "tp" or (r["outcome"].get("profit") or 0) > 0)]
    losses = [r for r in closed if (r["outcome"].get("result") == "sl" or (r["outcome"].get("profit") or 0) < 0)]
    win_rate = (len(wins) / len(closed)) if closed else 0.0
    by_pair: dict[str, dict] = {}
    for r in closed:
        p = r.get("pair", "?")
        bucket = by_pair.setdefault(p, {"wins": 0, "losses": 0, "total": 0, "profit": 0.0})
        bucket["total"] += 1
        profit = (r["outcome"].get("profit") or 0)
        bucket["profit"] += profit
        if profit > 0 or r["outcome"].get("result") == "tp":
            bucket["wins"] += 1
        elif profit < 0 or r["outcome"].get("result") == "sl":
            bucket["losses"] += 1
    return {
        "total": len(rows),
        "open": open_ct,
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 3),
        "total_profit": round(sum((r["outcome"].get("profit") or 0) for r in closed), 2),
        "by_pair": by_pair,
    }
