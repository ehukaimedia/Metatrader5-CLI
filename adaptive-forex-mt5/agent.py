"""Multi-pair trading agent.

Loop:
  1. For each pair, run `mt5 analyze sniper-poc`
  2. If status == "ready" and quality clears the bar, place via `mt5 order ready-limit`
  3. Log placement + reasoning to journal
  4. Poll positions; when an open ticket disappears, query history and log outcome

Keep simple. No briefings, no level state machine. Lets the deterministic
sniper-poc gates pick high-ROI setups; we just orchestrate scanning.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import alerts
import consensus as _consensus
import dispatch
import fingerprint
import journal
import state_db


def derive_magic(strategy_id: str) -> int:
    """Match metatrader5_cli/mt5/core/risk.py::resolve_magic auto-derivation."""
    return int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000

ROOT = Path(__file__).parent


def load_config() -> dict:
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        sys.exit(f"missing {cfg_path} -- copy config.example.json to config.json first")
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _cli(cfg: dict) -> list[str]:
    base = [cfg["mt5_cli"]["command"]]
    if cfg["mt5_cli"].get("live"):
        base.append("--live")
    return base + ["--json"]


def _run(cfg: dict, args: list[str]) -> dict | None:
    cmd = _cli(cfg) + args
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg["mt5_cli"]["subprocess_timeout_seconds"],
        )
        return json.loads(r.stdout) if r.stdout else None
    except Exception as e:
        return {"ok": False, "error": {"code": "SUBPROCESS_FAIL", "message": str(e)}}


def sniper_poc(cfg: dict, pair: str) -> dict | None:
    a = cfg["agent"]
    return _run(cfg, [
        "analyze", "sniper-poc", pair,
        "--direction", "auto",
        "--min-rr", str(a.get("min_rr", 3.0)),
        "--min-stop-points", str(a.get("min_stop_points", 80)),
        "--max-fvg-age-bars", str(a.get("max_fvg_age_bars", 40)),
    ])


def place_ready_limit(cfg: dict, pair: str) -> dict | None:
    a = cfg["agent"]
    return _run(cfg, [
        "order", "ready-limit", pair,
        "--direction", "auto",
        "--volume", str(a["volume"]),
        "--strategy-id", f"{a['strategy_id_prefix']}-{pair}",
    ])


def list_positions(cfg: dict) -> list[dict]:
    r = _run(cfg, ["position", "list"])
    if not r or not r.get("ok"):
        return []
    data = r.get("data")
    if isinstance(data, list):
        return data
    return data.get("positions") or [] if isinstance(data, dict) else []


def list_pending_orders(cfg: dict) -> list[dict]:
    r = _run(cfg, ["order", "list"])
    if not r or not r.get("ok"):
        return []
    data = r.get("data")
    if isinstance(data, list):
        return data
    return data.get("orders") or [] if isinstance(data, dict) else []


def active_strategies(cfg: dict) -> set[tuple[str, int]]:
    """Set of (symbol, magic) currently held by us as a position OR a pending order.

    Used to enforce one active strategy per pair: if we already have a pending
    limit on EURUSD with our magic, we should not place another one this cycle
    even if sniper-poc returns ready again.
    """
    active: set[tuple[str, int]] = set()
    for p in list_positions(cfg) + list_pending_orders(cfg):
        sym = (p.get("symbol") or "").upper()
        magic = p.get("magic")
        if sym and isinstance(magic, int):
            active.add((sym, magic))
    return active


def recent_deals(cfg: dict, days: int = 3) -> list[dict]:
    """Pull deals from the last N days. data is a flat list."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    r = _run(cfg, [
        "history", "deals",
        "--from", start.isoformat(),
        "--to", (today + timedelta(days=1)).isoformat(),
    ])
    if not r or not r.get("ok"):
        return []
    data = r.get("data") or []
    return data if isinstance(data, list) else []


def find_close_deal(deals: list[dict], *, placement_ticket: int, magic: int, symbol: str, direction: str) -> dict | None:
    """Find the closing deal for a netting position.

    Anchors on the OPENING deal (matched by deal.order == placement_ticket),
    then takes the first opposite-direction deal on the same strategy after
    the opening deal's time. This avoids wall-clock vs broker-server-clock
    skew when comparing placement timestamps to deal timestamps.

    A buy position closes via a sell deal; a sell position closes via a buy
    deal. Direction-flip matching attributes breakeven/zero-profit closures
    correctly — important because AdaptiveTrailEA's breakeven trail can
    produce exact-zero closes.
    """
    if not magic or direction not in ("buy", "sell"):
        return None
    opening = next(
        (d for d in deals
         if d.get("order") == placement_ticket
         and d.get("magic") == magic
         and (d.get("type") or "").lower() == direction),
        None,
    )
    if not opening:
        return None
    open_time = opening.get("time") or ""
    close_type = "sell" if direction == "buy" else "buy"
    matches = [
        d for d in deals
        if d.get("magic") == magic
        and (d.get("symbol") or "").upper() == symbol.upper()
        and (d.get("time") or "") > open_time
        and (d.get("type") or "").lower() == close_type
    ]
    if not matches:
        return None
    return min(matches, key=lambda d: d.get("time", ""))


def trades_today() -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = 0
    for r in journal.read_all():
        if r.get("kind") == "placement" and r.get("ts", "").startswith(today):
            n += 1
    return n


def open_journal_tickets() -> set[int]:
    out: set[int] = set()
    for r in journal.folded_trades():
        if not r.get("outcome") and r.get("ticket") is not None:
            out.add(r["ticket"])
    return out


def open_journal_records() -> list[dict]:
    """Return placement records that have no recorded outcome yet."""
    return [r for r in journal.folded_trades() if not r.get("outcome") and r.get("ticket") is not None]


def push(cfg: dict, title: str, body: str, tags: list[str] | None = None, priority: int | None = None) -> None:
    n = cfg["ntfy"]
    alerts.push(base_url=n["url"], topic=n["topic"], title=title, body=body, tags=tags, priority=priority)


def resolve_outcomes(cfg: dict) -> int:
    """Resolve outcomes for journal placements whose position has closed.

    Read-only with respect to broker state — never places orders. Returns
    the number of outcomes newly logged. Safe for tests to call.
    """
    a = cfg["agent"]
    open_records = open_journal_records()
    if not open_records:
        return 0
    live_tickets = {p.get("ticket") for p in list_positions(cfg)}
    closed_records = [r for r in open_records if r.get("ticket") not in live_tickets]
    if not closed_records:
        return 0
    deals = recent_deals(cfg, days=3)
    resolved = 0
    for r in closed_records:
        ticket = r["ticket"]
        # Prefer magic stored at placement time. Fall back to local
        # derivation only if older journal entries pre-date this fix.
        magic = r.get("magic")
        if not isinstance(magic, int):
            strategy_id = r.get("strategy_id") or f"{a['strategy_id_prefix']}-{r.get('pair','')}"
            magic = derive_magic(strategy_id)
        direction = (r.get("direction") or "").lower()
        deal = find_close_deal(deals, placement_ticket=ticket, magic=magic, symbol=r.get("pair","").upper(), direction=direction)
        if not deal:
            continue
        profit = float(deal.get("profit") or 0)
        swap = float(deal.get("swap") or 0)
        commission = float(deal.get("commission") or 0)
        net = profit + swap + commission
        result = "tp" if profit > 0 else ("sl" if profit < 0 else "even")

        # Realized R: signed fraction of SL-distance captured (in price units).
        realized_r = None
        entry = r.get("entry"); sl = r.get("sl"); close = deal.get("price")
        if all(isinstance(v, (int, float)) for v in (entry, sl, close)):
            sl_distance = abs(float(entry) - float(sl))
            if sl_distance > 0:
                sign = 1 if r.get("direction") == "buy" else -1
                realized_r = round(sign * (float(close) - float(entry)) / sl_distance, 2)

        journal.log_outcome(ticket, {
            "profit": profit,
            "swap": swap,
            "commission": commission,
            "net": round(net, 2),
            "close_price": deal.get("price"),
            "close_time": deal.get("time"),
            "result": result,
            "deal_id": deal.get("ticket"),
            "magic": magic,
            "planned_rr": r.get("rr"),
            "realized_r": realized_r,
        })
        push(cfg, f"Trade closed {result.upper()}", f"ticket {ticket} profit {profit:+.2f} net {net:+.2f} R={realized_r}", tags=["heavy_check_mark"] if profit > 0 else ["x"])
        resolved += 1
    return resolved


def place_new_orders(cfg: dict) -> int:
    """Scan pairs and place new orders where READY. Returns count placed."""
    a = cfg["agent"]
    # Concurrency caps — count BOTH open positions and pending limit orders
    # against max_concurrent_positions, otherwise pending limits across pairs
    # accumulate beyond the cap before any position appears.
    active = active_strategies(cfg)
    if len(active) >= a["max_concurrent_positions"]:
        return 0
    if trades_today() >= a["max_trades_per_day"]:
        return 0

    placed = 0
    for pair in cfg["pairs"]:
        # `active` is mutated in-place each iteration when a placement fires,
        # so its size IS the running concurrent count. No separate counter.
        if len(active) >= a["max_concurrent_positions"]:
            break
        if trades_today() >= a["max_trades_per_day"]:
            break

        strategy_id = f"{a['strategy_id_prefix']}-{pair}"
        magic = derive_magic(strategy_id)
        if (pair.upper(), magic) in active:
            journal.log_skip(pair, {"status": "active_strategy", "reason": "pending order or open position already exists for this strategy"})
            continue

        result = sniper_poc(cfg, pair)
        if not result or not result.get("ok"):
            journal.log_error(pair, "sniper_poc", (result or {}).get("error") or "no_response")
            continue
        data = result["data"]
        status = data.get("status")
        quality = float(data.get("quality_score") or 0)
        if status != "ready":
            journal.log_skip(pair, data)
            continue
        if quality < a["min_quality_score"]:
            data["status"] = "below_quality"
            data["reason"] = f"quality={quality} < {a['min_quality_score']}"
            journal.log_skip(pair, data)
            continue

        # Alerts-only mode: push the full trade idea to ntfy and journal it,
        # but do NOT place an order. Operator decides whether to take it.
        if a.get("alerts_only"):
            setup = data.get("setup") or {}
            direction = (data.get("direction") or "").upper()
            digits = 3 if pair.endswith("JPY") else 5
            pip = 0.01 if pair.endswith("JPY") else 0.0001
            entry = setup.get("entry")
            sl = setup.get("sl")
            tp = setup.get("tp")
            rr = setup.get("rr")
            sl_pips = abs(float(entry) - float(sl)) / pip if (entry and sl) else None
            tp_pips = abs(float(entry) - float(tp)) / pip if (entry and tp) else None
            why = (data.get("explain") or [""])[0]
            body_lines = [
                f"Entry: {entry:.{digits}f}" if entry is not None else "Entry: ?",
                f"SL: {sl:.{digits}f} ({sl_pips:.1f}p)" if sl is not None and sl_pips is not None else "SL: ?",
                f"TP: {tp:.{digits}f} ({tp_pips:.1f}p)" if tp is not None and tp_pips is not None else "TP: ?",
                f"R:R {rr:.2f}  Quality {quality:.2f}" if rr is not None else f"Quality {quality:.2f}",
                why,
            ]
            # Build the canonical reasoning context once (mirrors the shape
            # journal records use), then feed it to BOTH fingerprint and the
            # review payload. The raw sniper-poc output has structure / poi /
            # liquidity / entry / gates at the TOP level — `data["reasoning"]`
            # does not exist on raw output, only on already-journaled records.
            reasoning_ctx = journal._reasoning(data)
            structure_block = reasoning_ctx.get("structure") or {}
            bar_time = (
                structure_block.get("bar_time")
                or (structure_block.get("last_confirmed_event") or {}).get("level", {}).get("time")
            )
            data["setup_fingerprint"] = fingerprint.compute({
                "pair": pair,
                "direction": direction.lower(),
                "setup": setup,
                "poi": data.get("poi"),
                "reasoning": reasoning_ctx,
                "bar_time": bar_time,
                "digits": digits,
            })
            push(
                cfg,
                f"{pair} {direction} idea",
                "\n".join(body_lines),
                tags=["bell"], priority=5,
            )
            journal.log_ready_alert(pair, data)
            if a.get("review_enabled"):
                alert_id = f"{datetime.now(timezone.utc).isoformat(timespec='microseconds')}-{pair}"
                payload = {
                    "alert_id": alert_id,
                    "pair": pair,
                    "direction": direction.lower(),
                    "setup_fingerprint": data["setup_fingerprint"],
                    "setup": setup,
                    "poi": data.get("poi"),
                    "reasoning": reasoning_ctx,
                    "explain": data.get("explain"),
                    "rr": rr,
                }
                # autopilot is a TOP-LEVEL cfg block, NOT under cfg.agent.
                # Reading from a.get("autopilot") would silently fall back to
                # the single-reviewer phase-1 path (Codex1 caught this in the
                # plan orientation review).
                reviewers = (cfg.get("autopilot") or {}).get("reviewer_agents") \
                    or [a.get("reviewer_agent", "ClaudeReviewer")]
                for reviewer in reviewers:
                    task_id = dispatch.create_review_task(
                        payload,
                        alerts_dir=dispatch.alerts_dir_default(),
                        reviewer=reviewer,
                    )
                    if task_id:
                        journal.log_review_request(
                            alert_id=alert_id, task_id=task_id, pair=pair,
                        )
            continue

        placement = place_ready_limit(cfg, pair)
        if placement and placement.get("ok"):
            journal.log_placement(pair, placement)
            placement_data = (placement.get("data") or {}).get("placement") or {}
            ticket = placement_data.get("ticket")
            placed_magic = placement_data.get("magic")
            if isinstance(placed_magic, int):
                active.add((pair.upper(), placed_magic))
            placed += 1
            push(
                cfg,
                f"{pair} placed {data.get('direction')}",
                f"ticket {ticket} q={quality} -- {(data.get('explain') or [''])[0]}",
                tags=["heavy_check_mark"], priority=4,
            )
        else:
            err = (placement or {}).get("error") or {"code": "NO_PLACEMENT"}
            journal.log_error(pair, "ready_limit", err)
    return placed


def _state_db_path() -> Path:
    return Path(__file__).resolve().parent / "state.db"


def poll_verdicts(cfg: dict, db_path: Path | None = None) -> int:
    """Poll closed trade_review tasks since last_verdict_seen cursor.

    For each new closed task: read its verdict file, append a llm_verdict
    record to the journal, push an enriched ntfy. Advances the cursor to
    the latest task's `updated_at` (unix ts as string).

    Returns the count of verdicts processed.
    """
    if db_path is None:
        db_path = _state_db_path()
    cursor_name = "last_verdict_seen"
    since = state_db.cursor_get(db_path, cursor_name)
    tasks = dispatch.list_done_review_tasks(since=since)
    if not tasks:
        return 0
    last_ts = since
    count = 0
    for task in tasks:
        verdict_path_str = task.get("description")
        if not verdict_path_str:
            continue
        try:
            verdict = json.loads(Path(verdict_path_str).read_text(encoding="utf-8"))
        except Exception as e:
            journal.log_error("agent", "poll_verdicts_read", str(e))
            continue
        alert_id = verdict.get("alert_id") or ""
        # alert_id format: "<iso-ts>-<pair>" — pair is the trailing token
        pair = alert_id.rsplit("-", 1)[-1] if "-" in alert_id else ""
        verdict["task_id"] = task.get("id")
        verdict["task_updated_at"] = task.get("updated_at")
        journal.log_llm_verdict(pair, verdict)
        body = (
            f"{(verdict.get('decision') or '?').upper()} conf={verdict.get('confidence','?')}\n"
            f"{verdict.get('reasoning_summary','')}"
        )
        push(cfg, f"Reviewer verdict: {pair}", body, tags=["robot"])
        ts = task.get("updated_at")
        if ts is not None:
            last_ts = str(ts)
        count += 1
    if last_ts and last_ts != since:
        state_db.cursor_set(db_path, cursor_name, last_ts)
    return count


def evaluate_pending_consensus(cfg: dict, db_path: Path | None = None) -> int:
    """Join llm_verdict records by alert_id and journal a consensus_verdict
    when both reviewers have weighed in.

    Records every joined pair regardless of `autopilot.enabled` — that's the
    shadow-mode calibration data the operator needs before flipping the
    master flag. Dedupes via state.db.cursor 'last_consensus_seen'.

    Returns the count of new consensus_verdict rows journaled this call.
    """
    if db_path is None:
        db_path = _state_db_path()
    cursor_name = "last_consensus_seen"
    last_seen = state_db.cursor_get(db_path, cursor_name) or ""

    rows = journal.read_all()
    # Group llm_verdicts by alert_id; capture each alert's setup_fingerprint
    verdicts_by_alert: dict[str, list[dict]] = {}
    fp_by_alert: dict[str, str] = {}
    for r in rows:
        kind = r.get("kind")
        if kind == "ready_alert":
            aid_match = r.get("alert_id")
            fp = r.get("setup_fingerprint")
            if fp:
                if aid_match:
                    fp_by_alert[aid_match] = fp
                # Also record the most recent fingerprint for this pair so we
                # can still match when alert_id wasn't stamped on ready_alert
                # (alert_id is generated AFTER log_ready_alert in agent.py).
                fp_by_alert.setdefault(f"_pair:{r.get('pair')}", fp)
        elif kind == "llm_verdict":
            aid = r.get("alert_id")
            if aid:
                verdicts_by_alert.setdefault(aid, []).append(r)

    min_conf = float((cfg.get("autopilot") or {}).get("min_confidence", 0.75))
    new_consensus = 0
    latest_aid = last_seen
    for aid in sorted(verdicts_by_alert):
        if aid <= last_seen:
            continue
        verdicts = verdicts_by_alert[aid]
        if len(verdicts) < 2:
            continue
        # Take the first 2 distinct-reviewer verdicts (model is the reviewer
        # discriminator since reviewers self-report `model`).
        seen_models = set()
        votes = []
        for v in verdicts:
            m = v.get("model")
            if m in seen_models:
                continue
            seen_models.add(m)
            votes.append({
                "reviewer": m,
                "decision": v.get("decision"),
                "direction": v.get("direction"),
                "confidence": v.get("confidence"),
                "accepted_levels": v.get("accepted_levels"),
                "reviewed_fingerprint": v.get("reviewed_fingerprint"),
            })
            if len(votes) == 2:
                break
        if len(votes) < 2:
            continue
        # Resolve the alert's setup_fingerprint: prefer the matching
        # ready_alert record, fall back to the per-pair fingerprint, fall
        # back to whatever the first verdict reviewed (so consensus can't
        # silently match anything).
        pair = aid.rsplit("-", 1)[-1] if "-" in aid else None
        fp = fp_by_alert.get(aid) or fp_by_alert.get(f"_pair:{pair}") \
             or votes[0]["reviewed_fingerprint"]
        result = _consensus.evaluate(votes, alert_fingerprint=fp,
                                     min_confidence=min_conf)
        journal.log_consensus_verdict({
            "alert_id": aid,
            "setup_fingerprint": fp,
            "reviewers": [v["reviewer"] for v in votes],
            "votes": votes,
            **result,
        })
        new_consensus += 1
        if aid > latest_aid:
            latest_aid = aid
    if latest_aid and latest_aid != last_seen:
        state_db.cursor_set(db_path, cursor_name, latest_aid)
    return new_consensus


def scan_once(cfg: dict) -> None:
    """One full scan cycle: resolve outcomes, then place new orders."""
    resolve_outcomes(cfg)
    place_new_orders(cfg)
    if cfg.get("agent", {}).get("review_enabled"):
        try:
            poll_verdicts(cfg)
        except Exception as e:
            journal.log_error("agent", "poll_verdicts", str(e))
        try:
            evaluate_pending_consensus(cfg)
        except Exception as e:
            journal.log_error("agent", "evaluate_pending_consensus", str(e))


def run() -> None:
    cfg = load_config()
    a = cfg["agent"]
    print(f"[agent] starting · pairs={cfg['pairs']} · scan={a['scan_interval_seconds']}s · live={cfg['mt5_cli']['live']}")
    push(cfg, "Agent started", f"pairs={','.join(cfg['pairs'])} live={cfg['mt5_cli']['live']}", tags=["rocket"])
    last_outcome_poll = 0.0
    while True:
        try:
            scan_once(cfg)
        except Exception as e:
            sys.stderr.write(f"[agent] scan failed: {e}\n")
            journal.log_error("*", "scan_loop", str(e))
        time.sleep(a["scan_interval_seconds"])


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[agent] stopped")
