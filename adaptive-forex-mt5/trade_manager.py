"""Python-side post-fill trade manager — replaces AdaptiveTrailEA for our magics.

Runs as a separate process. Each loop:
  1. Heartbeat upsert to state.db.
  2. List MT5 positions, filter to poc-magic set.
  3. For each: bootstrap if needed, then BE/Chandelier/modify state machine.

Confirm-before-promote idempotency: last_sl_set is only set after MT5 confirms
the modify. Pending modifies retry on next loop with the same idempotency key.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import hashlib
from datetime import datetime, timezone

import journal
import state_db


HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "state.db"


def _derive_magic(strategy_id: str) -> int:
    """Same magic-derivation function used in agent.py.

    Duplicated here rather than imported to avoid a cross-process import
    of the entire agent module (which pulls in alerts/dispatch/etc).
    Kept in lockstep with agent.derive_magic via tests.
    """
    return int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000


def init_state(db_path: Path = DB_PATH) -> None:
    state_db.init(db_path)


def _cli(cfg: dict) -> list[str]:
    base = [cfg["mt5_cli"]["command"]]
    if cfg["mt5_cli"].get("live"):
        base.append("--live")
    return base


def _run(cfg: dict, args: list[str]) -> dict | None:
    cmd = _cli(cfg) + ["--json"] + args
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=cfg["mt5_cli"]["subprocess_timeout_seconds"],
        )
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def list_positions(cfg: dict) -> list[dict]:
    out = _run(cfg, ["position", "list"])
    if not out or not out.get("ok"):
        return []
    return out.get("data") or []


def poc_magics(cfg: dict) -> set[int]:
    """Compute the poc-magic set from cfg.pairs + cfg.agent.strategy_id_prefix.

    Same derivation as agent.derive_magic so renaming pairs auto-propagates.
    """
    prefix = cfg["agent"]["strategy_id_prefix"]
    return {_derive_magic(f"{prefix}-{pair}") for pair in cfg["pairs"]}


def _symbol_point_digits(cfg: dict, symbol: str) -> tuple[float, int]:
    """Look up the broker's `point` and `digits` for a symbol via the CLI.

    Falls back to JPY/non-JPY heuristics if the call fails.
    """
    out = _run(cfg, ["symbol", "info", symbol])
    if out and out.get("ok"):
        d = out.get("data") or {}
        point = float(d.get("point") or (0.001 if symbol.endswith("JPY") else 0.00001))
        digits = int(d.get("digits") or (3 if symbol.endswith("JPY") else 5))
        return point, digits
    return (0.001, 3) if symbol.endswith("JPY") else (0.00001, 5)


def _open_journal_placements() -> list[dict]:
    """All `kind=placement` records in trades.jsonl that have no later
    `kind=outcome` record for the same ticket."""
    rows = journal.read_all()
    placements: dict[int, dict] = {}
    closed: set[int] = set()
    for r in rows:
        kind = r.get("kind")
        ticket = r.get("ticket")
        if kind == "placement" and ticket is not None:
            placements[ticket] = r
        elif kind == "outcome" and ticket is not None:
            closed.add(ticket)
    return [p for tk, p in placements.items() if tk not in closed]


def _match_placement(pos: dict, placements: list[dict]) -> dict | None:
    """Two-phase match: ticket exact, then (magic, symbol) unambiguous."""
    by_ticket = {p.get("ticket"): p for p in placements if p.get("ticket")}
    if pos["ticket"] in by_ticket:
        return by_ticket[pos["ticket"]]
    candidates = [
        p for p in placements
        if p.get("magic") == pos["magic"] and p.get("pair") == pos["symbol"]
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None  # zero or ambiguous


_UNMANAGED_WARN_INTERVAL_SECONDS = 60


def _should_warn_unmanaged(db_path: Path, ticket: int) -> bool:
    """Rate-limit the unmanaged_poc_position warning to once per minute per ticket."""
    row = state_db.get_managed_position(db_path, ticket)
    if not row:
        return True
    last = row.get("last_unmanaged_warning_ts")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    delta = (datetime.now(last_dt.tzinfo or timezone.utc) - last_dt).total_seconds()
    return delta >= _UNMANAGED_WARN_INTERVAL_SECONDS


def bootstrap_position(cfg: dict, db_path: Path, pos: dict, *, account: int) -> dict | None:
    """Match an MT5 position to a journal placement and seed managed_position.

    Returns the seeded row dict on success, None on fail-closed (no match,
    ambiguous, or out-of-scope magic).
    """
    if pos["magic"] not in poc_magics(cfg):
        return None
    existing = state_db.get_managed_position(db_path, pos["ticket"])
    if existing and existing.get("stage") != "closed":
        return existing
    placement = _match_placement(pos, _open_journal_placements())
    if placement is None:
        if _should_warn_unmanaged(db_path, pos["ticket"]):
            journal.log_unmanaged_poc_position(
                ticket=pos["ticket"], symbol=pos["symbol"],
                magic=pos["magic"], reason="no_journal_match_or_ambiguous",
            )
        return None
    point, digits = _symbol_point_digits(cfg, pos["symbol"])
    initial_sl = float(placement.get("sl") or pos["sl"])
    entry_price = float(placement.get("entry") or pos["open_price"])
    initial_risk_price = abs(entry_price - initial_sl)
    initial_risk_points = initial_risk_price / point if point else 0.0
    row = {
        "ticket": pos["ticket"],
        "account": account,
        "symbol": pos["symbol"],
        "magic": pos["magic"],
        "direction": pos["type"],
        "entry_price": entry_price,
        "initial_sl": initial_sl,
        "initial_tp": placement.get("tp") or pos.get("tp"),
        "initial_risk_price": initial_risk_price,
        "initial_risk_points": initial_risk_points,
        "point": point,
        "digits": digits,
        "opened_time": pos.get("time") or "",
        "source_order_ticket": placement.get("ticket"),
        "journal_anchor": placement.get("ts"),
        "stage": "init",
    }
    state_db.upsert_managed_position(db_path, row)
    return row


def infer_stage_after_bootstrap(cfg: dict, db_path: Path, pos: dict) -> None:
    """After bootstrap, look at the live SL relative to entry and promote
    stage if it is already at or beyond breakeven. Never loosen.

    Buy: position.sl >= entry + BE_buffer_points * point  → at least be_armed.
    Sell: position.sl <= entry - BE_buffer_points * point → at least be_armed.
    """
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None or row.get("stage") != "init":
        return
    point = row["point"]
    entry = row["entry_price"]
    buffer_points = float(cfg["manager"].get("be_buffer_points", 5))
    sl = float(pos["sl"])
    if pos["type"] == "buy":
        threshold = entry + buffer_points * point
        is_at_be = sl >= threshold
    else:
        threshold = entry - buffer_points * point
        is_at_be = sl <= threshold
    if is_at_be:
        row["stage"] = "be_armed"
        row["last_sl_set"] = sl
        state_db.upsert_managed_position(db_path, row)


def loop_once(cfg: dict, db_path: Path = DB_PATH) -> None:
    """One iteration: heartbeat + scan-and-manage. Subsequent tasks fill in
    BE / Chandelier / modify."""
    state_db.heartbeat_upsert(db_path, "manager", pid=os.getpid())
    list_positions(cfg)


def run() -> None:
    cfg_path = HERE / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    init_state()
    interval = float(cfg.get("manager", {}).get("loop_seconds", 1))
    print(f"[trade_manager] starting · loop={interval}s · live={cfg['mt5_cli']['live']}")
    while True:
        try:
            loop_once(cfg)
        except Exception as e:
            journal.log_error("trade_manager", "loop", str(e))
        time.sleep(interval)


if __name__ == "__main__":
    run()
