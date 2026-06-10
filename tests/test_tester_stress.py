"""Tests for mt5_cli/tester/stress.py - pure delay-ladder + robustness scoring.

No filesystem, no launcher, no MT5 SDK: parsing, normalization, and scoring only.
"""
import pytest

from mt5_cli.tester import stress


# --- parse_delays -----------------------------------------------------------

def test_parse_delays_maps_tokens_to_execution_modes():
    assert stress.parse_delays("0,100,500,random") == [0, 100, 500, -1]


def test_parse_delays_is_whitespace_tolerant():
    assert stress.parse_delays(" 100 , random ") == [100, -1]


def test_parse_delays_rejects_non_numeric_token():
    with pytest.raises(ValueError):
        stress.parse_delays("0,junk")


def test_parse_delays_rejects_out_of_range_value():
    with pytest.raises(ValueError):
        stress.parse_delays("700000")


def test_parse_delays_rejects_raw_negative_token():
    """`random` is the only way to ask for -1; a literal negative is invalid."""
    with pytest.raises(ValueError):
        stress.parse_delays("-1")


def test_parse_delays_rejects_empty_input():
    """A stress run needs at least one rung; no-token input is invalid."""
    for spec in ("", "   ", ","):
        with pytest.raises(ValueError):
            stress.parse_delays(spec)


# --- normalize_ladder -------------------------------------------------------

def test_normalize_ladder_dedupes_and_orders():
    assert stress.normalize_ladder([500, 100, -1, 100]) == [0, 100, 500, -1]


def test_normalize_ladder_prepends_missing_baseline():
    assert stress.normalize_ladder([-1]) == [0, -1]


def test_normalize_ladder_keeps_lone_baseline():
    assert stress.normalize_ladder([0]) == [0]


def test_normalize_ladder_puts_random_last():
    assert stress.normalize_ladder([-1, 300, 0, 50]) == [0, 50, 300, -1]


def test_normalize_ladder_rejects_out_of_range_values():
    """The library path must enforce the same -1 / 0..600000 contract as the CLI."""
    for bad in ([-2], [600001]):
        with pytest.raises(ValueError):
            stress.normalize_ladder(bad)


def test_normalize_ladder_rejects_empty_ladder():
    with pytest.raises(ValueError):
        stress.normalize_ladder([])


# --- score ------------------------------------------------------------------

def _stats(net_profit, **extra):
    base = {
        "net_profit": net_profit,
        "profit_factor": 1.5,
        "max_drawdown_pct": 8.0,
        "total_trades": 100,
        "win_rate": 0.55,
    }
    base.update(extra)
    return base


def test_score_uses_worst_case_retention_and_rounds():
    out = stress.score(
        baseline_net_profit=4180.0,
        stressed=[
            {"delay_ms": 100, "stats": _stats(3990.5)},
            {"delay_ms": 500, "stats": _stats(3920.3)},
            {"delay_ms": -1, "stats": _stats(3804.9)},
        ],
    )
    assert out["score"] == 0.9103  # min(0.9547, 0.9379, 0.9103)
    assert out["verdict"] == "robust"
    assert out["baseline_net_profit"] == 4180.0
    assert out["incomplete"] is False
    assert [row["delay_ms"] for row in out["per_delay"]] == [100, 500, -1]
    assert out["per_delay"][0]["retention"] == 0.9547


def test_score_verdict_bands():
    degraded = stress.score(
        baseline_net_profit=1000.0,
        stressed=[{"delay_ms": 100, "stats": _stats(600.0)}],
    )
    assert degraded["score"] == 0.6
    assert degraded["verdict"] == "degraded"

    fragile = stress.score(
        baseline_net_profit=1000.0,
        stressed=[{"delay_ms": 100, "stats": _stats(400.0)}],
    )
    assert fragile["verdict"] == "fragile"


def test_score_clamps_both_ends():
    low = stress.score(
        baseline_net_profit=1000.0,
        stressed=[{"delay_ms": 100, "stats": _stats(-500.0)}],
    )
    assert low["score"] == 0.0
    assert low["verdict"] == "fragile"

    high = stress.score(
        baseline_net_profit=1000.0,
        stressed=[
            {"delay_ms": 100, "stats": _stats(1500.0)},
            {"delay_ms": 500, "stats": _stats(1200.0)},
        ],
    )
    assert high["score"] == 1.0
    assert high["verdict"] == "robust"


def test_score_ungraded_when_baseline_not_positive():
    for baseline in (0.0, -250.0, None):
        out = stress.score(
            baseline_net_profit=baseline,
            stressed=[{"delay_ms": 100, "stats": _stats(500.0)}],
        )
        assert out["score"] is None
        assert out["verdict"] == "ungraded"


def test_score_ungraded_when_no_stressed_scenario_succeeds():
    out = stress.score(baseline_net_profit=4180.0, stressed=[])
    assert out["score"] is None
    assert out["verdict"] == "ungraded"


def test_score_incomplete_when_some_stressed_scenario_fails():
    out = stress.score(
        baseline_net_profit=4180.0,
        stressed=[
            {"delay_ms": 100, "stats": _stats(3990.5)},
            {"delay_ms": 500, "stats": None},  # this rung's run failed
        ],
    )
    assert out["score"] == 0.9547
    assert out["verdict"] == "robust"
    assert out["incomplete"] is True
    assert [row["delay_ms"] for row in out["per_delay"]] == [100]


def test_score_all_stressed_failing_is_ungraded_and_incomplete():
    out = stress.score(
        baseline_net_profit=4180.0,
        stressed=[
            {"delay_ms": 100, "stats": None},
            {"delay_ms": -1, "stats": None},
        ],
    )
    assert out["score"] is None
    assert out["verdict"] == "ungraded"
    assert out["incomplete"] is True
