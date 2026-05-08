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


def log_placement(pair: str, setup: dict, placement: dict) -> None:
    """Record a successful order placement with the full reasoning."""
    data = placement.get("data") or {}
    final = data.get("final_setup") or {}
    final_setup = final.get("setup") or {}
    ticket = (data.get("placement") or {}).get("ticket")
    append({
        "kind": "placement",
        "pair": pair,
        "ticket": ticket,
        "direction": setup.get("direction"),
        "entry": final_setup.get("entry"),
        "sl": final_setup.get("sl"),
        "tp": final_setup.get("tp"),
        "rr": final_setup.get("rr"),
        "volume": final_setup.get("volume"),
        "strategy_id": data.get("strategy_id"),
        "reasoning": {
            "structure": setup.get("structure"),
            "poi": setup.get("poi"),
            "liquidity": setup.get("liquidity"),
            "entry": setup.get("entry"),
            "gates_passed": [g["name"] for g in setup.get("gates", []) if g.get("ok")],
            "explain": setup.get("explain"),
            "quality_score": setup.get("quality_score"),
        },
    })


def log_skip(pair: str, status: str, reason: str, setup: dict | None = None) -> None:
    append({
        "kind": "skip",
        "pair": pair,
        "status": status,
        "reason": reason,
        "explain": (setup or {}).get("explain"),
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
