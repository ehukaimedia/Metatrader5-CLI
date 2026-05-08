"""Autopilot executor — gated 12-step pipeline that places trades when the
2-of-2 reviewer consensus says `take` and every safety gate passes.

This module starts with the kill-switch + bus-abort listener; the 12-gate
`attempt_autopilot_place` is added in plan §Task 9.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import journal
import state_db


# ehukaiconnect read output line shape: "HH:MM:SS AM/PM <from> → <to>: <text>"
_BUS_LINE_RE = re.compile(
    r"^\d{1,2}:\d{2}:\d{2}\s+(?:AM|PM)\s+(?P<sender>\S+)\s+→\s+(?P<recipient>\S+):\s+(?P<text>.*)$"
)
_ABORT_TOKEN = "AUTOPILOT ABORT"


def _resolve_ehukaiconnect() -> str:
    """Same fallback as dispatch.py — handle PATH not having ehukaiconnect."""
    found = shutil.which("ehukaiconnect")
    if found:
        return found
    home = Path.home()
    win = home / ".ehukaiconnect" / "bin" / "ehukaiconnect.cmd"
    nix = home / ".ehukaiconnect" / "bin" / "ehukaiconnect"
    if win.exists():
        return str(win)
    if nix.exists():
        return str(nix)
    return "ehukaiconnect"


_EHUKAICONNECT = _resolve_ehukaiconnect()


_KILL_CURSOR = "autopilot_kill"


def kill_switch_get(db_path: Path) -> str:
    """Return 'on' or 'off' (default 'off' for fresh DBs)."""
    val = state_db.cursor_get(db_path, _KILL_CURSOR)
    return val if val == "on" else "off"


def kill_switch_set(db_path: Path, new_state: str, *, source: str) -> None:
    """Flip the kill-switch and journal the change.

    Idempotent: a second set to the same state does NOT emit a duplicate
    `autopilot_kill` event. `source` should be 'bus' or 'dashboard'.
    """
    if new_state not in {"on", "off"}:
        raise ValueError(f"kill_switch state must be 'on' or 'off', got {new_state!r}")
    prev = kill_switch_get(db_path)
    if prev == new_state:
        return
    state_db.cursor_set(db_path, _KILL_CURSOR, new_state)
    journal.log_autopilot_kill(prev=prev, new=new_state, source=source)


def poll_bus_for_abort(db_path: Path, *, lookback: int = 20,
                       timeout_seconds: float = 30) -> bool:
    """Read the last `lookback` bus messages, scan for `AUTOPILOT ABORT`
    sent by the operator, and flip the kill-switch on if found.

    Returns True iff the kill-switch was flipped (i.e. an abort message was
    found AND the switch wasn't already on). The flip itself is idempotent
    via kill_switch_set, so repeated abort messages while already-on are
    no-ops in terms of journal events.
    """
    cmd = [_EHUKAICONNECT, "read", str(int(lookback))]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return False
    if res.returncode != 0:
        return False
    found_abort = False
    for line in (res.stdout or "").splitlines():
        m = _BUS_LINE_RE.match(line.strip())
        if not m:
            continue
        if m.group("sender") != "operator":
            continue
        if _ABORT_TOKEN in m.group("text"):
            found_abort = True
            break  # one match is enough
    if not found_abort:
        return False
    if kill_switch_get(db_path) == "on":
        return False  # already on, no flip
    kill_switch_set(db_path, "on", source="bus")
    return True


# --- 12-gate autopilot executor -------------------------------------------

import hashlib  # noqa: E402
import json as _json  # noqa: E402
from datetime import datetime as _datetime, timezone as _timezone  # noqa: E402

import news as _news  # noqa: E402


def _derive_magic(strategy_id: str) -> int:
    return int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000


def _run_cli_capture(cmd: list[str]) -> dict | None:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    if res.returncode != 0:
        return None
    try:
        return _json.loads(res.stdout or "{}")
    except _json.JSONDecodeError:
        return None


def _alert_age_seconds(alert: dict) -> float:
    ts = alert.get("ts")
    if not ts:
        return 0.0
    try:
        dt = _datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_timezone.utc)
    return (_datetime.now(_timezone.utc) - dt).total_seconds()


def _current_setup(cfg: dict, pair: str) -> dict | None:
    cmd = [cfg["mt5_cli"]["command"], "--json", "analyze", "sniper-poc", pair]
    out = _run_cli_capture(cmd)
    if not out or not out.get("ok"):
        return None
    return out.get("data") or None


def _fingerprint_or_drift_ok(cfg: dict, alert: dict, ap: dict) -> bool:
    current = _current_setup(cfg, alert["pair"])
    if not current:
        return False
    if current.get("setup_fingerprint") == alert.get("setup_fingerprint"):
        return True
    # Bounded drift fallback: same direction, same POI id, same structure
    # event, AND each level differs by ≤ max_entry_drift_points.
    if current.get("direction") != alert.get("direction"):
        return False
    a_poi = (alert.get("poi") or {}).get("id")
    c_poi = (current.get("poi") or {}).get("id")
    if a_poi and c_poi and a_poi != c_poi:
        return False
    a_evt = (((alert.get("reasoning") or {}).get("structure") or {})
             .get("last_confirmed_event") or {}).get("type")
    c_evt = ((current.get("structure") or {})
             .get("last_confirmed_event") or {}).get("type")
    if a_evt and c_evt and a_evt != c_evt:
        return False
    point_threshold = float(ap.get("max_entry_drift_points", 30))
    # Use current symbol info to get point value
    market = _run_cli_capture(
        [cfg["mt5_cli"]["command"], "--json", "market", "info", alert["pair"]]
    )
    point = 0.001 if alert["pair"].endswith("JPY") else 0.00001
    if market and market.get("ok"):
        point = float((market.get("data") or {}).get("point") or point)
    a_setup = alert.get("setup") or {}
    c_setup = current.get("setup") or {}
    for k in ("entry", "sl", "tp"):
        av = a_setup.get(k)
        cv = c_setup.get(k)
        if av is None or cv is None:
            return False
        drift_points = abs(float(cv) - float(av)) / point if point else 0
        if drift_points > point_threshold:
            return False
    return True


def _current_spread(cfg: dict, pair: str) -> float | None:
    out = _run_cli_capture(
        [cfg["mt5_cli"]["command"], "--json", "market", "info", pair]
    )
    if not out or not out.get("ok"):
        return None
    return float((out.get("data") or {}).get("spread") or 0)


def _within_caps(db_path, ap: dict) -> bool:
    """Daily caps scoped to AUTOPILOT placements only — manual /
    phase-1 placements never count toward autopilot.daily_loss_cap_usd
    (Codex1 audit point).
    """
    rows = journal.read_all()
    today_utc = _datetime.now(_timezone.utc).date()
    autopilot_placements_today: list[dict] = []
    outcomes_by_ticket: dict[int, dict] = {}
    for r in rows:
        kind = r.get("kind")
        if kind == "autopilot_placement":
            try:
                ts = _datetime.fromisoformat(r.get("ts") or "")
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=_timezone.utc)
                if ts.date() == today_utc:
                    autopilot_placements_today.append(r)
            except (ValueError, TypeError):
                pass
        elif kind == "outcome":
            tk = r.get("ticket")
            if tk is not None:
                outcomes_by_ticket[tk] = r
    if len(autopilot_placements_today) >= int(ap.get("daily_trade_cap", 0)):
        return False
    realized_loss = 0.0
    for p in autopilot_placements_today:
        oc = outcomes_by_ticket.get(p.get("ticket"))
        if not oc:
            continue
        net = oc.get("net") if oc.get("net") is not None else oc.get("profit") or 0
        try:
            net = float(net)
        except (TypeError, ValueError):
            net = 0.0
        if net < 0:
            realized_loss += abs(net)
    cap_usd = float(ap.get("daily_loss_cap_usd", 0))
    if cap_usd > 0 and realized_loss >= cap_usd:
        return False
    return True


def _already_active(cfg: dict, alert: dict) -> bool:
    """Re-uses the same active_strategies guard as agent.py: counts BOTH
    open positions AND pending limit orders for (pair, magic)."""
    import agent as _agent
    pair_upper = alert["pair"].upper()
    magic = _derive_magic(f"{cfg['agent']['strategy_id_prefix']}-{alert['pair']}")
    return (pair_upper, magic) in _agent.active_strategies(cfg)


def attempt_autopilot_place(cfg: dict, db_path, alert: dict,
                            consensus: dict) -> dict | None:
    """12-gate fail-fast executor. On all-pass, places via `mt5 order limit`
    using the EXACT levels stored on `alert['setup']` (not anything the
    reviewers said, not anything sniper_poc returns now)."""
    ap = cfg.get("autopilot") or {}
    aid = alert.get("alert_id")

    # Gate 1: enabled
    if not ap.get("enabled"):
        journal.log_autopilot_skip(aid, "enabled", "off")
        return None

    # Gate 2: kill switch
    if kill_switch_get(db_path) == "on":
        journal.log_autopilot_skip(aid, "kill_switch", "on")
        return None

    # Gate 3: consensus
    if (consensus or {}).get("consensus") != "take":
        journal.log_autopilot_skip(aid, "consensus",
                                   (consensus or {}).get("consensus_reason") or "no_consensus")
        return None

    # Gate 4: pair allowlist
    allowlist = ap.get("pair_allowlist") or []
    if alert["pair"] not in allowlist:
        journal.log_autopilot_skip(aid, "pair_allowlist", alert["pair"])
        return None

    # Gate 5: alert age
    max_age = float(ap.get("max_alert_age_seconds", 180))
    if _alert_age_seconds(alert) > max_age:
        journal.log_autopilot_skip(aid, "alert_age", "stale_setup")
        return None

    # Gate 6: fingerprint match OR bounded drift
    if not _fingerprint_or_drift_ok(cfg, alert, ap):
        journal.log_autopilot_skip(aid, "fingerprint_or_drift", "stale_setup")
        return None

    # Gate 7: live-intent (BEFORE any mutating broker call)
    if not cfg["mt5_cli"].get("live"):
        journal.log_autopilot_skip(aid, "live", "not_live")
        return None

    # Gate 8: spread cap (current quote)
    spread = _current_spread(cfg, alert["pair"])
    max_spread = float(cfg["manager"].get("max_spread_points", 100))
    if spread is None or spread > max_spread:
        journal.log_autopilot_skip(aid, "spread_cap", f"spread={spread}")
        return None

    # Gate 9: news blackout (fails closed when news_source is null)
    if _news.is_blackout_active(cfg, alert["pair"]):
        journal.log_autopilot_skip(aid, "news_blackout", "active_or_unavailable")
        return None

    # Gate 10: micro-lot only
    lot = float(ap.get("lot_size") or 0)
    if lot <= 0:
        journal.log_autopilot_skip(aid, "lot_size", "invalid")
        return None

    # Gate 11: daily caps
    if not _within_caps(db_path, ap):
        journal.log_autopilot_skip(aid, "daily_caps", "exceeded")
        return None

    # Gate 12: one active strategy per (pair, magic)
    if _already_active(cfg, alert):
        journal.log_autopilot_skip(aid, "active_strategy", "already_open")
        return None

    # All 12 pass. Place at the EXACT alert.setup levels via `mt5 order limit`.
    setup = alert["setup"]
    magic = _derive_magic(
        f"{cfg['agent']['strategy_id_prefix']}-{alert['pair']}"
    )
    cmd = [
        cfg["mt5_cli"]["command"], "--live", "--json",
        "order", "limit", alert["pair"], alert["direction"],
        "--price",  f"{setup['entry']}",
        "--sl",     f"{setup['sl']}",
        "--tp",     f"{setup['tp']}",
        "--volume", f"{lot}",
        "--magic",  str(magic),
        "--strategy-id", f"{cfg['agent']['strategy_id_prefix']}-{alert['pair']}",
    ]
    placement = _run_cli_capture(cmd)
    if placement and placement.get("ok"):
        journal.log_autopilot_placement(
            pair=alert["pair"], placement=placement,
            consensus_alert_id=aid,
            reviewer_confidences=[
                float(v.get("confidence") or 0)
                for v in (consensus.get("votes") or [])
            ],
        )
    return placement
