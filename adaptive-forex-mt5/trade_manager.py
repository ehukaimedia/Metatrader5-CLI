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


def compute_be_target(row: dict, cfg: dict, favorable_price: float) -> float | None:
    """Return the BE-move SL target if R-trigger met, else None.

    For a buy: favorable_price > entry. We require
    `(favorable_price - entry) / initial_risk_price >= be_trigger_r`.
    Target SL = entry + be_buffer_points * point.
    Mirror for sell.
    """
    m = cfg["manager"]
    trigger_r = float(m.get("be_trigger_r", 0.80))
    buffer_points = float(m.get("be_buffer_points", 5))
    fallback_points = float(m.get("be_trigger_points_fallback", 80))
    point = row["point"]
    entry = row["entry_price"]
    risk_price = row["initial_risk_price"]
    if row["direction"] == "buy":
        favorable_distance = favorable_price - entry
        target = entry + buffer_points * point
    else:
        favorable_distance = entry - favorable_price
        target = entry - buffer_points * point
    if favorable_distance <= 0:
        return None
    # Float-tolerant compares — 0.16 / 0.20 lands at 0.79999... so a strict
    # < check would miss exactly-at-threshold cases.
    eps = 1e-9
    if risk_price > 0:
        achieved_r = favorable_distance / risk_price
        if achieved_r + eps < trigger_r:
            return None
    else:
        achieved_points = favorable_distance / point if point else 0
        if achieved_points + eps < fallback_points:
            return None
    return round(target, row.get("digits", 5))


def compute_chandelier(bars: list[dict], *, direction: str, cfg: dict) -> float | None:
    """Chandelier exit on a list of OHLC bars (oldest first).

    bars: [{"high", "low", "close"}, ...] — closed bars only.
    Returns: trail SL price, or None if not enough data.
    """
    m = cfg["manager"]
    period = int(m.get("chandelier_atr_period", 22))
    mult = float(m.get("chandelier_atr_multiplier", 3.0))
    lookback = int(m.get("chandelier_extreme_lookback", 22))

    # Need at least period+1 bars to take period TRs.
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    atr = sum(trs[-period:]) / period

    extremes_window = bars[-lookback:]
    if direction == "buy":
        highest_high = max(b["high"] for b in extremes_window)
        return highest_high - mult * atr
    lowest_low = min(b["low"] for b in extremes_window)
    return lowest_low + mult * atr


def _idempotency_key(ticket: int, sl: float, stage_to: str | None) -> str:
    raw = f"{ticket}|{sl}|{stage_to or ''}".encode()
    return hashlib.blake2b(raw, digest_size=8).hexdigest()


def _is_tightening(direction: str, current_sl: float, new_sl: float) -> bool:
    return new_sl > current_sl if direction == "buy" else new_sl < current_sl


def _read_position_sl(cfg: dict, ticket: int) -> float | None:
    out = _run(cfg, ["position", "list"])
    if not out or not out.get("ok"):
        return None
    for p in out.get("data") or []:
        if p["ticket"] == ticket:
            return float(p["sl"])
    return None


def _promote(db_path: Path, row: dict, sl: float,
             stage_to: str | None, reason: str) -> None:
    stage_from = row["stage"]  # snapshot BEFORE update
    old_sl = row.get("last_sl_set") or row["initial_sl"]
    row["last_sl_set"] = sl
    if stage_to:
        row["stage"] = stage_to
    row["pending_action"] = None
    row["requested_sl"] = None
    row["idempotency_key"] = None
    state_db.upsert_managed_position(db_path, row)
    journal.log_manage_action(
        ticket=row["ticket"], stage_from=stage_from,
        stage_to=stage_to or stage_from, old_sl=old_sl, new_sl=sl,
        trigger=reason,
    )


def _issue_modify(cfg: dict, db_path: Path, pos: dict, row: dict,
                  new_sl: float, reason: str, stage_to: str | None,
                  *, existing_key: str | None = None) -> None:
    digits = row["digits"]
    eps = 10 ** -(digits + 1)
    key = existing_key or _idempotency_key(pos["ticket"], new_sl, stage_to)
    row["pending_action"] = "modify_sl"
    row["requested_sl"] = new_sl
    row["idempotency_key"] = key
    row["last_action_ts"] = datetime.now(timezone.utc).isoformat()
    state_db.upsert_managed_position(db_path, row)

    _run(cfg, ["position", "move-sl", str(pos["ticket"]),
               "--sl", f"{new_sl:.{digits}f}"])
    confirmed = _read_position_sl(cfg, pos["ticket"])
    if confirmed is not None and abs(confirmed - new_sl) < eps:
        _promote(db_path, row, new_sl, stage_to, reason)
        return
    journal.log_manage_skip(ticket=pos["ticket"], reason="unconfirmed",
                            detail={"requested_sl": new_sl, "current_sl": confirmed})


def attempt_modify(cfg: dict, db_path: Path, pos: dict, *,
                   new_sl: float, reason: str,
                   stage_to: str | None = None) -> None:
    """Stage → call → confirm → promote with cooldown retry on unknown result.

    Codex1's must-fixes (NO-GO unless explicit):
    1. Live-gated: cfg.mt5_cli.live=False → not_live skip BEFORE any broker call.
    2. Confirm-existing-without-broker-call: pending_action set with same
       requested_sl + MT5 already at that SL → promote, no `move-sl` call.
    3. Cooldown-elapsed retry uses the SAME idempotency_key.
    """
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None:
        return

    # 1. Live gate (no broker call when live=false)
    if not cfg["mt5_cli"].get("live"):
        journal.log_manage_skip(ticket=pos["ticket"], reason="not_live")
        return

    m = cfg["manager"]
    point = row["point"]
    digits = row["digits"]
    new_sl_rounded = round(new_sl, digits)
    eps = 10 ** -(digits + 1)
    cooldown_seconds = float(m.get("modify_cooldown_seconds", 5))

    # 2. Confirm-existing path (no broker call yet)
    if row.get("pending_action") == "modify_sl":
        requested = row.get("requested_sl")
        if requested is not None and abs(float(requested) - new_sl_rounded) < eps:
            confirmed = _read_position_sl(cfg, pos["ticket"])
            if confirmed is not None and abs(confirmed - float(requested)) < eps:
                _promote(db_path, row, float(requested), stage_to, reason)
                return
            last_ts = row.get("last_action_ts")
            if last_ts:
                try:
                    last_dt = datetime.fromisoformat(last_ts)
                    elapsed = (datetime.now(last_dt.tzinfo or timezone.utc) - last_dt).total_seconds()
                    if elapsed < cooldown_seconds:
                        journal.log_manage_skip(ticket=pos["ticket"], reason="cooldown")
                        return
                except ValueError:
                    pass
            # 3. Cooldown elapsed → retry with SAME idempotency key
            _issue_modify(cfg, db_path, pos, row, new_sl_rounded, reason,
                          stage_to, existing_key=row.get("idempotency_key"))
            return

    # 4. Spread guard
    spread = float(pos.get("spread") or 0)
    max_spread = float(m.get("max_spread_points", 100))
    if max_spread > 0 and spread > max_spread:
        journal.log_manage_skip(ticket=pos["ticket"], reason="spread_cap",
                                detail={"spread": spread, "cap": max_spread})
        return

    # 5. Tightening + min_improvement
    current_sl = float(pos.get("sl") or row.get("last_sl_set") or row["initial_sl"])
    if not _is_tightening(row["direction"], current_sl, new_sl_rounded):
        journal.log_manage_skip(ticket=pos["ticket"], reason="not_tightening")
        return
    min_improvement = float(m.get("min_sl_improvement_points", 5))
    improvement_points = abs(new_sl_rounded - current_sl) / point if point else 0
    if improvement_points + 1e-9 < min_improvement:
        journal.log_manage_skip(ticket=pos["ticket"], reason="min_improvement",
                                detail={"points": improvement_points,
                                        "floor": min_improvement})
        return

    # 6. Fresh modify with new idempotency key
    _issue_modify(cfg, db_path, pos, row, new_sl_rounded, reason, stage_to)


def _account_login(cfg: dict) -> int:
    out = _run(cfg, ["account", "info"])
    if out and out.get("ok"):
        return int((out.get("data") or {}).get("login") or 0)
    return 0


def _recent_bars(cfg: dict, symbol: str, timeframe: str, count: int) -> list[dict]:
    out = _run(cfg, ["rates", symbol, timeframe, str(count)])
    if not out or not out.get("ok"):
        return []
    return out.get("data") or []


def _favorable_price(direction: str, pos: dict) -> float:
    """For a buy: max-favorable price = current bid. For sell: current ask.

    Falls back to open_price if quote unavailable.
    """
    bid = float(pos.get("bid") or pos.get("price_current") or pos.get("open_price"))
    ask = float(pos.get("ask") or pos.get("price_current") or pos.get("open_price"))
    return bid if direction == "buy" else ask


def manage_one(cfg: dict, db_path: Path, pos: dict) -> None:
    row = state_db.get_managed_position(db_path, pos["ticket"])
    if row is None or row.get("stage") == "closed":
        return
    favorable = _favorable_price(row["direction"], pos)
    # Stage 1: BE move (only when stage == 'init')
    if row["stage"] == "init":
        target = compute_be_target(row, cfg, favorable)
        if target is not None:
            attempt_modify(cfg, db_path, pos, new_sl=target,
                           reason="be_r", stage_to="be_armed")
            return
    # Stage 2: Chandelier trail (when stage in {be_armed, trailing})
    if row["stage"] in {"be_armed", "trailing"}:
        bars = _recent_bars(
            cfg, pos["symbol"],
            cfg["manager"].get("chandelier_timeframe", "M5"),
            int(cfg["manager"].get("chandelier_extreme_lookback", 22)) + 5,
        )
        if not bars:
            return
        new_sl = compute_chandelier(bars, direction=row["direction"], cfg=cfg)
        if new_sl is None:
            return
        attempt_modify(cfg, db_path, pos, new_sl=new_sl,
                       reason="chandelier", stage_to="trailing")


def loop_once(cfg: dict, db_path: Path = DB_PATH) -> None:
    """One iteration: heartbeat + scan-and-manage. Bootstraps unknown
    poc-magic positions, infers stage, then runs BE/Chandelier per row."""
    state_db.heartbeat_upsert(db_path, "manager", pid=os.getpid())
    positions = list_positions(cfg)
    if not positions:
        return
    account = _account_login(cfg)
    magics = poc_magics(cfg)
    for pos in positions:
        if pos.get("magic") not in magics:
            continue
        bootstrap_position(cfg, db_path, pos, account=account)
        infer_stage_after_bootstrap(cfg, db_path, pos)
        manage_one(cfg, db_path, pos)


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
