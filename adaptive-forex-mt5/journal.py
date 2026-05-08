"""Append-only trade journal.

Each trade is one record in logs/trades.jsonl. Updates (e.g. outcome) are
appended as new records keyed by ticket; readers fold them on read.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
_LOG_PATH = ROOT / "logs" / "trades.jsonl"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(record: dict) -> None:
    record.setdefault("ts", _ts())
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
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


def log_ready_alert(pair: str, scan: dict) -> None:
    """Record a setup that went READY but was NOT placed (alerts-only mode).

    Same shape as a placement record minus the broker fields. Lets the
    dashboard distinguish 'bot would have placed this' from 'skipped'
    without polluting the placement count.

    `alert_id` (if present in scan) is preserved so phase-2 autopilot can
    retrieve the EXACT original setup by id (Codex1's blocker #2 — the
    pair-fallback was unsafe when multiple READYs exist for the same pair).
    """
    scan = scan or {}
    setup = scan.get("setup") or {}
    record = {
        "kind": "ready_alert",
        "pair": pair,
        "direction": scan.get("direction"),
        "entry": setup.get("entry"),
        "sl": setup.get("sl"),
        "tp": setup.get("tp"),
        "rr": setup.get("rr"),
        "quality_score": scan.get("quality_score"),
        "reasoning": _reasoning(scan),
    }
    if "setup_fingerprint" in scan:
        record["setup_fingerprint"] = scan["setup_fingerprint"]
    if "alert_id" in scan:
        record["alert_id"] = scan["alert_id"]
    append(record)


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
    if not _LOG_PATH.exists():
        return []
    out = []
    for line in _LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def log_llm_verdict(pair: str, verdict: dict) -> None:
    """Record a reviewer-agent verdict joined back from the dispatcher pipeline."""
    append({"kind": "llm_verdict", "pair": pair, **verdict})


def log_manage_action(ticket: int, stage_from: str, stage_to: str,
                      old_sl: float, new_sl: float, trigger: str) -> None:
    """Record a confirmed BE move or trail tighten."""
    append({
        "kind": "manage_action",
        "ticket": ticket,
        "stage_from": stage_from,
        "stage_to": stage_to,
        "old_sl": old_sl,
        "new_sl": new_sl,
        "trigger": trigger,
    })


def log_manage_skip(ticket: int, reason: str, detail: dict | None = None) -> None:
    """Record a guard-rejected modify (rate-limited at call site)."""
    rec = {"kind": "manage_skip", "ticket": ticket, "reason": reason}
    if detail:
        rec["detail"] = detail
    append(rec)


def log_unmanaged_poc_position(ticket: int, symbol: str, magic: int, reason: str) -> None:
    """Record a poc-magic position the manager cannot bootstrap (rate-limited at call site)."""
    append({
        "kind": "unmanaged_poc_position",
        "ticket": ticket,
        "symbol": symbol,
        "magic": magic,
        "reason": reason,
    })


def log_review_request(alert_id: str, task_id: str, pair: str) -> None:
    """Record that agent.py created a trade_review task for this alert."""
    append({
        "kind": "review_request",
        "alert_id": alert_id,
        "task_id": task_id,
        "pair": pair,
    })


# --- Phase 2 (autopilot consensus) ----------------------------------------

def log_consensus_verdict(record: dict) -> None:
    """Record a 2-of-2 consensus result (joined from two reviewer verdicts).

    Whether or not autopilot.enabled is True, every joined verdict pair is
    recorded — this is the shadow-mode calibration data the operator needs
    before flipping the master flag.
    """
    append({"kind": "consensus_verdict", **record})


def log_autopilot_placement(*, pair: str, alert: dict, placement: dict,
                            consensus_alert_id: str,
                            reviewer_confidences: list[float],
                            strategy_id: str | None = None) -> None:
    """Record a successful autopilot auto-placement.

    Codex1 phase-2 audit fix: writes a `kind=placement` record (NOT a new
    kind) so it flows through every existing lifecycle consumer —
    `journal.folded_trades`, `agent.open_journal_records`,
    `agent.resolve_outcomes`, `trade_manager._open_journal_placements`.
    The `autopilot=true` flag plus `consensus_alert_id` and
    `reviewer_confidences` let the dashboard split autopilot trades from
    manual / phase-1 placements.
    """
    data = placement.get("data") or {}
    placement_data = data.get("placement") or {}
    setup = alert.get("setup") or {}
    append({
        "kind": "placement",
        "autopilot": True,
        "pair": pair,
        "ticket": placement_data.get("ticket"),
        "magic": placement_data.get("magic"),
        "direction": alert.get("direction"),
        "entry": setup.get("entry"),
        "sl": setup.get("sl"),
        "tp": setup.get("tp"),
        "rr": setup.get("rr"),
        "volume": placement_data.get("volume"),
        "strategy_id": strategy_id,
        "reasoning": alert.get("reasoning") or {},
        "consensus_alert_id": consensus_alert_id,
        "reviewer_confidences": reviewer_confidences,
    })


def log_autopilot_skip(alert_id: str, gate: str, reason: str) -> None:
    """Record an autopilot gate failure. `gate` is the failing gate name
    (e.g. 'enabled', 'kill_switch', 'consensus', 'news_blackout', ...)."""
    append({
        "kind": "autopilot_skip",
        "alert_id": alert_id,
        "gate": gate,
        "reason": reason,
    })


def log_autopilot_kill(prev: str, new: str, source: str) -> None:
    """Record a kill-switch state change. `source` is 'bus' or 'dashboard'."""
    append({
        "kind": "autopilot_kill",
        "prev": prev,
        "new": new,
        "source": source,
    })


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
    """Aggregate stats. Uses NET P/L (profit + swap + commission) for totals.

    realized_r aggregates capture how much of the planned R was actually
    achieved per trade, summed and averaged across closed trades.
    """
    rows = folded_trades()
    closed = [r for r in rows if r.get("outcome")]
    open_ct = len(rows) - len(closed)

    def net_of(r: dict) -> float:
        oc = r.get("outcome") or {}
        # Prefer net (which includes swap+commission); fall back to profit
        # for legacy outcome records without those fields.
        if oc.get("net") is not None:
            return float(oc["net"])
        return float(oc.get("profit") or 0)

    wins = [r for r in closed if net_of(r) > 0]
    losses = [r for r in closed if net_of(r) < 0]
    breakeven = [r for r in closed if net_of(r) == 0]
    win_rate = (len(wins) / len(closed)) if closed else 0.0
    realized_rs = [r["outcome"].get("realized_r") for r in closed if isinstance(r["outcome"].get("realized_r"), (int, float))]
    total_realized_r = sum(realized_rs) if realized_rs else 0
    avg_realized_r = (total_realized_r / len(realized_rs)) if realized_rs else 0

    by_pair: dict[str, dict] = {}
    for r in closed:
        p = r.get("pair", "?")
        bucket = by_pair.setdefault(p, {"wins": 0, "losses": 0, "total": 0, "net": 0.0, "realized_r_sum": 0.0})
        bucket["total"] += 1
        n = net_of(r)
        bucket["net"] += n
        rr = r["outcome"].get("realized_r")
        if isinstance(rr, (int, float)):
            bucket["realized_r_sum"] += rr
        if n > 0:
            bucket["wins"] += 1
        elif n < 0:
            bucket["losses"] += 1

    # Round per-pair fields for display
    for b in by_pair.values():
        b["net"] = round(b["net"], 2)
        b["realized_r_sum"] = round(b["realized_r_sum"], 2)

    return {
        "total": len(rows),
        "open": open_ct,
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": round(win_rate, 3),
        "total_net": round(sum(net_of(r) for r in closed), 2),
        "total_realized_r": round(total_realized_r, 2),
        "avg_realized_r": round(avg_realized_r, 2),
        "by_pair": by_pair,
    }
