"""Phase-2 dual reviewer dispatch.

agent.py must create one trade_review task per `cfg.autopilot.reviewer_agents`
entry, each with the SAME alert payload (so reviewers vote on the same setup).
Falls back to single reviewer when autopilot block is absent.
"""
from __future__ import annotations

from unittest.mock import patch

import agent


def _ready():
    return {
        "status": "ready", "direction": "BUY", "quality_score": 0.9,
        "setup": {"entry": 156.50, "sl": 156.30, "tp": 157.00, "rr": 2.5},
        "poi": {"id": "FVG-1", "top": 156.52, "bottom": 156.48},
        "structure": {"last_confirmed_event": {
            "type": "BOS", "level": {"time": "2026-05-08T12:00:00+00:00"},
        }},
        "liquidity": {}, "entry": {}, "gates": [],
        "explain": ["BOS confirmed"], "bias_counts": {"buy": 3, "sell": 1, "neutral": 0},
        "quote": {"bid": 156.499, "ask": 156.501, "spread_points": 20},
    }


def _cfg(*, reviewer_agents=None, tmp_path=None):
    cfg = {
        "pairs": ["USDJPY"],
        "agent": {
            "alerts_only": True, "review_enabled": True,
            "reviewer_agent": "ClaudeReviewer",
            "min_quality_score": 0.85, "min_rr": 3.0, "min_stop_points": 80,
            "max_fvg_age_bars": 40, "max_concurrent_positions": 50,
            "max_trades_per_day": 500, "volume": 0.001,
            "strategy_id_prefix": "ehukai-poc",
            "scan_interval_seconds": 60, "outcome_poll_seconds": 30,
        },
        "ntfy": {"topic": "test", "url": "https://example.invalid"},
        "mt5_cli": {"command": "mt5", "live": False, "subprocess_timeout_seconds": 60},
        "dashboard": {"bind_host": "127.0.0.1", "bind_port": 8765, "refresh_seconds": 5},
    }
    if reviewer_agents is not None:
        cfg["autopilot"] = {"reviewer_agents": reviewer_agents}
    return cfg


def test_dual_dispatch_when_autopilot_reviewer_agents_set(tmp_path):
    """When cfg.autopilot.reviewer_agents has 2 entries, agent dispatches twice."""
    cfg = _cfg(reviewer_agents=["ClaudeReviewer", "CodexReviewer"], tmp_path=tmp_path)
    with patch("agent.sniper_poc", return_value={"ok": True, "data": _ready()}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
        mock_dispatch.create_review_task.side_effect = ["task-1", "task-2"]
        agent.place_new_orders(cfg)
    # Two dispatches, one per reviewer
    assert mock_dispatch.create_review_task.call_count == 2
    reviewers = [c.kwargs["reviewer"] for c in mock_dispatch.create_review_task.call_args_list]
    assert set(reviewers) == {"ClaudeReviewer", "CodexReviewer"}
    # Two review_request journal entries
    assert mock_journal.log_review_request.call_count == 2
    # Same alert_id + payload across both calls
    payloads = [c.args[0] for c in mock_dispatch.create_review_task.call_args_list]
    assert payloads[0]["alert_id"] == payloads[1]["alert_id"]
    assert payloads[0]["setup_fingerprint"] == payloads[1]["setup_fingerprint"]


def test_single_dispatch_when_autopilot_block_absent(tmp_path):
    """No autopilot block → fall back to single phase-1 reviewer (ClaudeReviewer).

    Codex1 caught a bug in the plan-as-written where `a.get('autopilot')`
    (under cfg.agent) silently returned None and the loop fell back to a
    1-reviewer dispatch. This test guards against that regression: with no
    cfg.autopilot, exactly one task is dispatched (the agent.reviewer_agent).
    """
    cfg = _cfg(reviewer_agents=None, tmp_path=tmp_path)
    with patch("agent.sniper_poc", return_value={"ok": True, "data": _ready()}), \
         patch("agent.dispatch") as mock_dispatch, \
         patch("agent.journal") as mock_journal, \
         patch("agent.push") as _mock_push, \
         patch("agent.active_strategies", return_value=set()), \
         patch("agent.trades_today", return_value=0):
        from journal import _reasoning as _real_reasoning
        mock_journal._reasoning.side_effect = _real_reasoning
        mock_dispatch.alerts_dir_default.return_value = tmp_path / "alerts"
        mock_dispatch.create_review_task.return_value = "task-1"
        agent.place_new_orders(cfg)
    assert mock_dispatch.create_review_task.call_count == 1
    assert mock_dispatch.create_review_task.call_args.kwargs["reviewer"] == "ClaudeReviewer"
