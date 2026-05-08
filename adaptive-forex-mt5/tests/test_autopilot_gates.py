"""12-gate autopilot executor — fail-fast tests + all-pass placement.

CRITICAL invariants enforced by these tests:
- Every gate failure logs autopilot_skip and makes ZERO `order limit` calls.
- The all-pass placement uses alert['setup']['entry'/'sl'/'tp'] EXACTLY,
  even when the current `sniper_poc` would return different levels.
- Live-intent gate (#7) blocks BEFORE any broker call (no order limit, no
  market info, no rates).
- News blackout (#9) blocks even if all other gates pass.
- Reviewer adjusted_* fields are NEVER read by this module.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autopilot
import journal
import news
import state_db


_FP = "deadbeef"


def setup_function(_):
    news._SOURCES.clear()


def _alert(*, alert_id="2026-05-08T16:00:00.000000+00:00-USDJPY",
           pair="USDJPY", direction="buy",
           entry=156.50, sl=156.30, tp=157.00, fingerprint=_FP, ts=None):
    return {
        "alert_id": alert_id,
        "pair": pair,
        "direction": direction,
        "setup": {"entry": entry, "sl": sl, "tp": tp, "rr": 2.5},
        "setup_fingerprint": fingerprint,
        "ts": ts or datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }


def _consensus(*, take=True, votes=None):
    if votes is None:
        votes = [
            {"reviewer": "claude", "confidence": 0.84, "decision": "take"},
            {"reviewer": "codex", "confidence": 0.79, "decision": "take"},
        ]
    return {
        "consensus": "take" if take else "no_consensus",
        "consensus_reason": "2-of-2 take" if take else "test",
        "votes": votes,
    }


def _cfg(*, enabled=True, live=True, news_source="t",
         pair_allowlist=("USDJPY",), spread_now=10):
    cfg = {
        "pairs": ["USDJPY"],
        "agent": {"strategy_id_prefix": "ehukai-poc"},
        "manager": {"max_spread_points": 100},
        "autopilot": {
            "enabled": enabled,
            "pair_allowlist": list(pair_allowlist),
            "max_alert_age_seconds": 180,
            "max_entry_drift_points": 30,
            "lot_size": 0.001,
            "daily_trade_cap": 5,
            "daily_loss_cap_usd": 5.00,
            "news_source": news_source,
            "min_confidence": 0.75,
        },
        "mt5_cli": {"command": "mt5", "live": live, "subprocess_timeout_seconds": 60},
    }
    cfg["_spread_now"] = spread_now
    return cfg


def _setup_db_and_log(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    state_db.init(db)
    log = tmp_path / "logs" / "trades.jsonl"
    log.parent.mkdir(parents=True)
    monkeypatch.setattr(journal, "_LOG_PATH", log)
    return db, log


def _kinds(log):
    return [json.loads(l) for l in log.read_text().splitlines() if l.strip()]


def _last_skip(log):
    rows = [r for r in _kinds(log) if r["kind"] == "autopilot_skip"]
    return rows[-1] if rows else None


def _passing_run_factory(cfg, alert):
    """Build a side_effect that makes ALL gates 4-12 pass for an all-pass test."""
    def fake_run(cmd, **kwargs):
        class R: pass
        r = R()
        r.returncode = 0
        r.stderr = ""
        r.stdout = "{}"
        if "sniper-poc" in cmd or "analyze" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "status": "ready",
                "direction": alert["direction"],
                "setup": dict(alert["setup"]),
                "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
                "structure": {"last_confirmed_event": {"type": "BOS",
                              "level": {"time": "2026-05-08T12:00:00+00:00"}}},
                "setup_fingerprint": alert["setup_fingerprint"],
            }})
        elif "market" in cmd and "info" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "bid": 156.499, "ask": 156.500, "spread": cfg["_spread_now"],
                "digits": 3, "point": 0.001,
            }})
        elif "order" in cmd and "limit" in cmd:
            # Flat shape from `mt5 order limit` (per _finalize_order in
            # metatrader5_cli/mt5/core/order.py).
            r.stdout = json.dumps({"ok": True, "data": {
                "ticket": 1234, "magic": 128461, "volume": 0.001,
                "symbol": "USDJPY", "type": "buy",
                "price": 156.50, "sl": 156.30, "tp": 157.00,
            }})
        elif "position" in cmd and "list" in cmd:
            r.stdout = json.dumps({"ok": True, "data": []})
        return r
    return fake_run


# -------- Gate 1: enabled --------------------------------------------------

def test_gate1_disabled(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    cfg = _cfg(enabled=False)
    with patch("autopilot.subprocess.run") as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, _alert(), _consensus())
    assert out is None
    assert mock_run.call_count == 0
    assert _last_skip(log)["gate"] == "enabled"


# -------- Gate 2: kill_switch ---------------------------------------------

def test_gate2_kill_switch_on(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    autopilot.kill_switch_set(db, "on", source="test")
    cfg = _cfg()
    with patch("autopilot.subprocess.run") as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, _alert(), _consensus())
    assert out is None
    assert mock_run.call_count == 0
    assert _last_skip(log)["gate"] == "kill_switch"


# -------- Gate 3: consensus -----------------------------------------------

def test_gate3_no_consensus(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    cfg = _cfg()
    with patch("autopilot.subprocess.run") as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, _alert(),
                                                _consensus(take=False))
    assert out is None
    assert mock_run.call_count == 0
    assert _last_skip(log)["gate"] == "consensus"


# -------- Gate 4: pair allowlist -----------------------------------------

def test_gate4_pair_not_in_allowlist(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    cfg = _cfg(pair_allowlist=("EURUSD",))
    with patch("autopilot.subprocess.run") as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, _alert(), _consensus())
    assert out is None
    assert mock_run.call_count == 0
    assert _last_skip(log)["gate"] == "pair_allowlist"


# -------- Gate 5: alert age -----------------------------------------------

def test_gate5_alert_too_old(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    cfg = _cfg()
    old_alert = _alert(ts=(datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    with patch("autopilot.subprocess.run") as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, old_alert, _consensus())
    assert out is None
    assert mock_run.call_count == 0
    assert _last_skip(log)["gate"] == "alert_age"


# -------- Gate 6: fingerprint mismatch + drift over cap -------------------

def test_gate6_fingerprint_and_drift_fail(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    news.register_source("t", lambda p: [])
    cfg = _cfg()

    def fake_run(cmd, **kwargs):
        class R: pass
        r = R(); r.returncode = 0; r.stderr = ""; r.stdout = "{}"
        if "sniper-poc" in cmd or "analyze" in cmd:
            # different fingerprint AND different POI → drift fails too
            r.stdout = json.dumps({"ok": True, "data": {
                "status": "ready", "direction": "buy",
                "setup": {"entry": 200.0, "sl": 199.5, "tp": 201.0},
                "poi": {"id": "FVG-DIFFERENT", "top": 200.5, "bottom": 199.5},
                "structure": {"last_confirmed_event": {"type": "BOS",
                              "level": {"time": "2026-05-08T11:00:00+00:00"}}},
                "setup_fingerprint": "cafebabe",
            }})
        return r

    with patch("autopilot.subprocess.run", side_effect=fake_run):
        out = autopilot.attempt_autopilot_place(cfg, db, _alert(), _consensus())
    assert out is None
    skip = _last_skip(log)
    assert skip["gate"] == "fingerprint_or_drift"


# -------- Gate 7: live-intent BEFORE any broker call ----------------------

def test_gate7_not_live_zero_broker_calls(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    news.register_source("t", lambda p: [])
    cfg = _cfg(live=False)
    alert = _alert()
    with patch("autopilot.subprocess.run", side_effect=_passing_run_factory(cfg, alert)) as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, alert, _consensus())
    assert out is None
    # The not-live skip must happen BEFORE the order-limit broker call. We
    # may have hit sniper_poc / market info for the gates above #7, but
    # NEVER `order limit`.
    order_limit_calls = [c for c in mock_run.call_args_list
                         if "order" in c.args[0] and "limit" in c.args[0]]
    assert order_limit_calls == []
    assert _last_skip(log)["gate"] == "live"


# -------- Gate 9: news_blackout fails closed when source is null ----------

def test_gate9_news_blackout_null_source(tmp_path, monkeypatch):
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    cfg = _cfg(news_source=None)  # null source — fail closed
    alert = _alert()
    with patch("autopilot.subprocess.run", side_effect=_passing_run_factory(cfg, alert)) as mock_run:
        out = autopilot.attempt_autopilot_place(cfg, db, alert, _consensus())
    assert out is None
    order_limit_calls = [c for c in mock_run.call_args_list
                         if "order" in c.args[0] and "limit" in c.args[0]]
    assert order_limit_calls == []
    assert _last_skip(log)["gate"] == "news_blackout"


# -------- All-pass: places at the EXACT alert.setup levels ----------------

def test_all_pass_places_at_alert_setup_levels_exactly(tmp_path, monkeypatch):
    """The big invariant: even when the current sniper_poc returns
    DIFFERENT levels (within drift), the broker call must use
    alert.setup.entry/sl/tp EXACTLY — never re-evaluated levels."""
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    news.register_source("t", lambda p: [])
    cfg = _cfg()
    alert = _alert(entry=156.50, sl=156.30, tp=157.00)

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        class R: pass
        r = R(); r.returncode = 0; r.stderr = ""; r.stdout = "{}"
        captured.append(list(cmd))
        if "sniper-poc" in cmd or "analyze" in cmd:
            # Current setup has DIFFERENT levels but SAME fingerprint (so
            # the fingerprint gate passes via exact match). The placement
            # must still use the alert.setup levels, not these.
            r.stdout = json.dumps({"ok": True, "data": {
                "status": "ready", "direction": "buy",
                "setup": {"entry": 156.55, "sl": 156.35, "tp": 157.05},
                "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
                "structure": {"last_confirmed_event": {"type": "BOS",
                              "level": {"time": "2026-05-08T12:00:00+00:00"}}},
                "setup_fingerprint": _FP,
            }})
        elif "market" in cmd and "info" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "bid": 156.499, "ask": 156.500, "spread": 10,
                "digits": 3, "point": 0.001,
            }})
        elif "order" in cmd and "limit" in cmd:
            # Flat shape from `mt5 order limit` (per _finalize_order in
            # metatrader5_cli/mt5/core/order.py).
            r.stdout = json.dumps({"ok": True, "data": {
                "ticket": 1234, "magic": 128461, "volume": 0.001,
                "symbol": "USDJPY", "type": "buy",
                "price": 156.50, "sl": 156.30, "tp": 157.00,
            }})
        elif "position" in cmd and "list" in cmd:
            r.stdout = json.dumps({"ok": True, "data": []})
        return r

    with patch("autopilot.subprocess.run", side_effect=fake_run):
        out = autopilot.attempt_autopilot_place(cfg, db, alert, _consensus())
    assert out is not None
    assert out.get("ok"), out

    # Exactly one `order limit` call, with the original alert.setup levels.
    order_calls = [c for c in captured if "order" in c and "limit" in c]
    assert len(order_calls) == 1
    cmd = order_calls[0]
    price = cmd[cmd.index("--price") + 1]
    sl = cmd[cmd.index("--sl") + 1]
    tp = cmd[cmd.index("--tp") + 1]
    assert float(price) == 156.50  # alert.setup.entry, NOT the 156.55 current
    assert float(sl) == 156.30     # alert.setup.sl,    NOT the 156.35 current
    assert float(tp) == 157.00     # alert.setup.tp,    NOT the 157.05 current

    # Journal records a kind=placement with autopilot=true so the
    # existing trade lifecycle (manager bootstrap, resolve_outcomes,
    # folded_trades) consumes it natively (Codex1 phase-2 audit fix).
    rows = _kinds(log)
    assert any(r["kind"] == "placement" and r.get("autopilot") for r in rows)


def test_executor_never_reads_reviewer_adjusted_fields(tmp_path, monkeypatch):
    """Even if a vote carries adjusted_entry / adjusted_sl / adjusted_tp,
    those values must NEVER appear in the broker call — the executor only
    reads alert['setup'], not the verdicts."""
    db, log = _setup_db_and_log(tmp_path, monkeypatch)
    news.register_source("t", lambda p: [])
    cfg = _cfg()
    alert = _alert(entry=156.50, sl=156.30, tp=157.00)
    consensus_with_adjusted_in_vote = _consensus(votes=[
        {"reviewer": "claude", "confidence": 0.84, "decision": "take",
         "adjusted_entry": 999.00, "adjusted_sl": 998.00, "adjusted_tp": 1001.00},
        {"reviewer": "codex", "confidence": 0.79, "decision": "take"},
    ])
    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        class R: pass
        r = R(); r.returncode = 0; r.stderr = ""; r.stdout = "{}"
        captured.append(list(cmd))
        if "sniper-poc" in cmd or "analyze" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "status": "ready", "direction": "buy",
                "setup": dict(alert["setup"]),
                "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
                "structure": {"last_confirmed_event": {"type": "BOS",
                              "level": {"time": "2026-05-08T12:00:00+00:00"}}},
                "setup_fingerprint": _FP,
            }})
        elif "market" in cmd and "info" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {"bid": 156.499, "ask": 156.500, "spread": 10}})
        elif "order" in cmd and "limit" in cmd:
            r.stdout = json.dumps({"ok": True, "data": {
                "ticket": 1234, "magic": 128461, "volume": 0.001,
                "symbol": "USDJPY", "type": "buy",
                "price": 156.50, "sl": 156.30, "tp": 157.00,
            }})
        elif "position" in cmd and "list" in cmd:
            r.stdout = json.dumps({"ok": True, "data": []})
        return r

    with patch("autopilot.subprocess.run", side_effect=fake_run):
        autopilot.attempt_autopilot_place(cfg, db, alert,
                                          consensus_with_adjusted_in_vote)

    # The 999/998/1001 values from adjusted_* MUST NOT appear in any cmd
    flat = " ".join(" ".join(c) for c in captured)
    assert "999" not in flat
    assert "998" not in flat
    assert "1001" not in flat
