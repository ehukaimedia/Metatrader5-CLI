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
import journal


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


def find_close_deal(deals: list[dict], *, magic: int, symbol: str, after_time: str) -> dict | None:
    """Find the closing deal for a netting position.

    The closing-deal record has its own order ticket (NOT the placement ticket),
    so matching by deal.order == placement_ticket misses closures. Trading.com
    netting + FIFO guarantees at most one position per (symbol, magic) at a time,
    so the closing deal is the first deal with profit != 0 on that strategy
    after the placement time.
    """
    if not magic:
        return None
    matches = [
        d for d in deals
        if d.get("magic") == magic
        and (d.get("symbol") or "").upper() == symbol.upper()
        and (d.get("time") or "") > after_time
        and (d.get("profit") or 0) != 0
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


def scan_once(cfg: dict) -> None:
    a = cfg["agent"]

    # Resolve outcomes for closed positions. Match closing deals by
    # (magic, symbol, time>placement_time, profit!=0) — the deal.order on a
    # closing deal is the close-order ticket, NOT the original placement.
    open_records = open_journal_records()
    if open_records:
        live_tickets = {p.get("ticket") for p in list_positions(cfg)}
        closed_records = [r for r in open_records if r.get("ticket") not in live_tickets]
        if closed_records:
            deals = recent_deals(cfg, days=3)
            for r in closed_records:
                ticket = r["ticket"]
                # Prefer magic stored at placement time. Fall back to local
                # derivation only if older journal entries pre-date this fix.
                magic = r.get("magic")
                if not isinstance(magic, int):
                    strategy_id = r.get("strategy_id") or f"{a['strategy_id_prefix']}-{r.get('pair','')}"
                    magic = derive_magic(strategy_id)
                placement_time = r.get("ts") or "1970-01-01"
                deal = find_close_deal(deals, magic=magic, symbol=r.get("pair","").upper(), after_time=placement_time)
                if deal:
                    profit = float(deal.get("profit") or 0)
                    swap = float(deal.get("swap") or 0)
                    commission = float(deal.get("commission") or 0)
                    net = profit + swap + commission
                    result = "tp" if profit > 0 else ("sl" if profit < 0 else "even")

                    # Realized R: how many SL-distances of profit (in price terms) we got.
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

    # Concurrency caps
    if len(list_positions(cfg)) >= a["max_concurrent_positions"]:
        return
    if trades_today() >= a["max_trades_per_day"]:
        return

    # One active strategy per (symbol, magic): if we already have a pending
    # limit OR open position with our magic on this pair, don't fire another
    # placement until it resolves.
    active = active_strategies(cfg)
    placed_this_cycle = 0

    for pair in cfg["pairs"]:
        if (len(list_positions(cfg)) + placed_this_cycle) >= a["max_concurrent_positions"]:
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

        placement = place_ready_limit(cfg, pair)
        if placement and placement.get("ok"):
            journal.log_placement(pair, placement)
            placement_data = (placement.get("data") or {}).get("placement") or {}
            ticket = placement_data.get("ticket")
            placed_magic = placement_data.get("magic")
            if isinstance(placed_magic, int):
                active.add((pair.upper(), placed_magic))
            placed_this_cycle += 1
            push(
                cfg,
                f"{pair} placed {data.get('direction')}",
                f"ticket {ticket} q={quality} -- {(data.get('explain') or [''])[0]}",
                tags=["heavy_check_mark"], priority=4,
            )
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
