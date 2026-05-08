"""Verify agent.py dispatches a review task in the alerts-only path.

These tests use the REAL sniper-poc output shape (structure/poi/liquidity/
gates/explain at top level), not the journal-normalized `reasoning` shape.
"""
from __future__ import annotations

from unittest.mock import patch

import agent


def _cfg(tmp_path):
    return {
        "pairs": ["USDJPY"],
        "agent": {
            "alerts_only": True,
            "review_enabled": True,
            "reviewer_agent": "ClaudeReviewer",
            "min_quality_score": 0.85,
            "min_rr": 3.0,
            "min_stop_points": 80,
            "max_fvg_age_bars": 40,
            "max_concurrent_positions": 50,
            "max_trades_per_day": 500,
            "volume": 0.001,
            "strategy_id_prefix": "ehukai-poc",
            "scan_interval_seconds": 60,
            "outcome_poll_seconds": 30,
        },
        "ntfy": {"topic": "test", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
        "dashboard": {"bind_host": "127.0.0.1", "bind_port": 8765, "refresh_seconds": 5},
    }


def _ready_data(*, event_time="2026-05-08T12:00:00+00:00"):
    """Mimic the real top-level shape of sniper-poc's `data` block."""
    return {
        "status": "ready",
        "direction": "BUY",
        "quality_score": 0.9,
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
        "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
        "structure": {
            "last_confirmed_event": {
                "type": "BOS",
                "level": {"time": event_time},
            },
        },
        "liquidity": {},
        "entry": {},
        "gates": [],
        "explain": ["BOS confirmed"],
        "bias_counts": {"buy": 3, "sell": 1, "neutral": 0},
        "quote": {"bid": 156.499, "ask": 156.501, "spread_points": 20},
    }


def test_alerts_only_creates_review_task(tmp_path):
    with patch("agent.sniper_poc", return_value={"ok": True, "data": _ready_data()}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        # journal._reasoning is the canonical context builder; let it through
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        mock_dispatch.create_review_task.return_value = "task-xyz"
        mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
        cfg = _cfg(tmp_path)
        agent.place_new_orders(cfg)
    assert mock_dispatch.create_review_task.called
    payload = mock_dispatch.create_review_task.call_args.args[0]
    assert payload["alert_id"]
    assert payload["setup_fingerprint"]
    assert payload["pair"] == "USDJPY"
    # Canonical reasoning context must be present in the payload, not None
    assert payload["reasoning"] is not None
    assert payload["reasoning"].get("structure") is not None
    assert payload["reasoning"]["structure"].get("last_confirmed_event") is not None
    mock_journal.log_ready_alert.assert_called_once()
    mock_journal.log_review_request.assert_called_once()
    kwargs = mock_journal.log_review_request.call_args.kwargs
    assert kwargs["alert_id"] == payload["alert_id"]
    assert kwargs["task_id"] == "task-xyz"
    assert kwargs["pair"] == "USDJPY"


def test_alerts_only_skips_dispatch_when_review_disabled(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["agent"]["review_enabled"] = False
    with patch("agent.sniper_poc", return_value={"ok": True, "data": _ready_data()}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        agent.place_new_orders(cfg)
    assert not mock_dispatch.create_review_task.called
    mock_journal.log_review_request.assert_not_called()


def test_setup_fingerprint_changes_when_structure_event_changes(tmp_path):
    """The fingerprint must bind to the deterministic setup snapshot, including
    the structure last_confirmed_event time. This catches the audit-flagged
    failure where a fresh cousin setup with a later event would fingerprint
    identically and slip past the autopilot stale-setup gate."""
    captured = []

    def _capture(payload, **_kw):
        captured.append(dict(payload))
        return None  # task creation skipped

    with patch("agent.sniper_poc",
               return_value={"ok": True, "data": _ready_data(event_time="2026-05-08T12:00:00+00:00")}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        mock_dispatch.create_review_task.side_effect = _capture
        mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
        agent.place_new_orders(_cfg(tmp_path))

    with patch("agent.sniper_poc",
               return_value={"ok": True, "data": _ready_data(event_time="2026-05-08T12:30:00+00:00")}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        mock_dispatch.create_review_task.side_effect = _capture
        mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
        agent.place_new_orders(_cfg(tmp_path))

    assert len(captured) == 2
    assert captured[0]["setup_fingerprint"] != captured[1]["setup_fingerprint"]
