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

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import alerts
import journal

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


def find_close_deal(deals: list[dict], order_ticket: int) -> dict | None:
    """Find the closing deal for a position. Match deal.order == placed order ticket.

    On Trading.com (netting), a position open + close share an order chain.
    The closing deal has profit != 0 (or matches by order/symbol/time).
    """
    matches = [d for d in deals if d.get("order") == order_ticket]
    if not matches:
        return None
    # Pick the latest with non-zero profit, or just the latest
    closing = [d for d in matches if (d.get("profit") or 0) != 0]
    if closing:
        return max(closing, key=lambda d: d.get("time", ""))
    return max(matches, key=lambda d: d.get("time", ""))


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


def push(cfg: dict, title: str, body: str, tags: list[str] | None = None, priority: int | None = None) -> None:
    n = cfg["ntfy"]
    alerts.push(base_url=n["url"], topic=n["topic"], title=title, body=body, tags=tags, priority=priority)


def scan_once(cfg: dict) -> None:
    a = cfg["agent"]

    # Resolve outcomes for closed positions
    open_tickets = open_journal_tickets()
    if open_tickets:
        live_tickets = {p.get("ticket") for p in list_positions(cfg)}
        closed = open_tickets - live_tickets
        if closed:
            deals = recent_deals(cfg, days=3)
            for ticket in closed:
                deal = find_close_deal(deals, ticket)
                if deal:
                    profit = float(deal.get("profit") or 0)
                    result = "tp" if profit > 0 else ("sl" if profit < 0 else "even")
                    journal.log_outcome(ticket, {
                        "profit": profit,
                        "close_price": deal.get("price"),
                        "close_time": deal.get("time"),
                        "result": result,
                        "deal_id": deal.get("ticket"),
                    })
                    push(cfg, f"Trade closed {result.upper()}", f"ticket {ticket} profit {profit:+.2f}", tags=["heavy_check_mark"] if profit > 0 else ["x"])

    # Concurrency cap
    open_now = len(list_positions(cfg))
    if open_now >= a["max_concurrent_positions"]:
        return
    if trades_today() >= a["max_trades_per_day"]:
        return

    for pair in cfg["pairs"]:
        if open_now >= a["max_concurrent_positions"]:
            break
        if trades_today() >= a["max_trades_per_day"]:
            break
        result = sniper_poc(cfg, pair)
        if not result or not result.get("ok"):
            journal.log_error(pair, "sniper_poc", (result or {}).get("error") or "no_response")
            continue
        data = result["data"]
        status = data.get("status")
        quality = float(data.get("quality_score") or 0)
        if status != "ready":
            journal.log_skip(pair, status or "unknown", data.get("reason") or "", data)
            continue
        if quality < a["min_quality_score"]:
            journal.log_skip(pair, "below_quality", f"quality={quality} < {a['min_quality_score']}", data)
            continue

        placement = place_ready_limit(cfg, pair)
        if placement and placement.get("ok"):
            journal.log_placement(pair, data, placement)
            ticket = (placement.get("data") or {}).get("placement", {}).get("ticket")
            push(
                cfg,
                f"{pair} placed {data.get('direction')}",
                f"ticket {ticket} q={quality} -- {(data.get('explain') or [''])[0]}",
                tags=["heavy_check_mark"], priority=4,
            )
            open_now += 1
        else:
            err = (placement or {}).get("error") or {"code": "NO_PLACEMENT"}
            journal.log_error(pair, "ready_limit", err)


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
