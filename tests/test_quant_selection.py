"""Quant selection: in-sample winner pick + cross-cell gate/rank."""
import pytest

from mt5_cli.quant import selection


def _pass(pf, fast):
    return {"params": {"FastPeriod": str(fast)},
            "is": {"profit_factor": pf, "trades": 400, "sharpe": 1.0, "net_profit": 100.0}}


def test_pick_winner_by_is_pf_among_gate_clearers():
    passes = [_pass(1.2, 9), _pass(1.9, 12), _pass(0.8, 5)]
    assert selection.pick_winner(passes, min_pf=1.0)["params"]["FastPeriod"] == "12"


def test_pick_winner_none_when_no_pass_clears():
    assert selection.pick_winner([_pass(0.8, 5)], min_pf=1.0) is None


def _cell(symbol, trades, net, oos_pf=1.5, oos_sharpe=1.0):
    return {"symbol": symbol, "timeframe": "H1",
            "full": {"trades": trades, "net_profit": net},
            "oos": {"profit_factor": oos_pf, "sharpe": oos_sharpe}}


def test_full_net_default_rank_no_caveat():
    out = selection.gate_and_rank(
        [_cell("GOLD", 800, 55000.0, oos_sharpe=1.8), _cell("EURUSD", 900, 13000.0, oos_sharpe=1.0)],
        min_trades=300, oos_min_pf=1.0, rank_by="full_net", per_asset=2)
    assert [c["symbol"] for c in out["ranked"]] == ["GOLD", "EURUSD"]
    assert out["rank_caveat"] is None


def test_oos_rank_sets_caveat():
    out = selection.gate_and_rank([_cell("X", 400, 1.0)], min_trades=300, oos_min_pf=1.0,
                                  rank_by="oos_sharpe", per_asset=2)
    assert out["rank_caveat"] == "oos_metric_can_reflect_asset_drift"


def test_min_trades_rejects():
    out = selection.gate_and_rank([_cell("X", 100, 1.0)], min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert out["ranked"] == []
    assert out["rejected"][0]["reason"] == "MIN_TRADES"


def test_validated_flag_does_not_gate_ranking():
    out = selection.gate_and_rank([_cell("X", 400, 5.0, oos_pf=0.9)], min_trades=300,
                                  oos_min_pf=1.0, rank_by="full_net", per_asset=2)
    assert out["ranked"][0]["validated"] is False  # still ranked


def test_per_asset_cap_trims_extra_survivors():
    cells = [_cell("GOLD", 800, n) for n in (90000.0, 80000.0, 70000.0)]
    out = selection.gate_and_rank(cells, min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert [c["full"]["net_profit"] for c in out["ranked"]] == [90000.0, 80000.0]


def test_none_metric_sorts_last_without_typeerror():
    a = _cell("A", 400, 100.0)
    b = {"symbol": "B", "timeframe": "H1",
         "full": {"trades": 400, "net_profit": None}, "oos": {}}
    out = selection.gate_and_rank([b, a], min_trades=300, oos_min_pf=1.0,
                                  rank_by="full_net", per_asset=2)
    assert [c["symbol"] for c in out["ranked"]] == ["A", "B"]  # None ranks last, no crash


def test_pick_winner_ignores_nonnumeric_pf_even_at_min_pf_zero():
    # a missing in-sample PF must never qualify, even when the gate is 0
    assert selection.pick_winner([{"params": {}, "is": {"profit_factor": None}}], min_pf=0.0) is None


def test_validated_false_when_oos_pf_missing_even_at_zero_floor():
    out = selection.gate_and_rank(
        [{"symbol": "X", "timeframe": "H1", "full": {"trades": 400, "net_profit": 1.0}, "oos": {}}],
        min_trades=300, oos_min_pf=0.0, rank_by="full_net", per_asset=2)
    assert out["ranked"][0]["validated"] is False


def test_bad_rank_by_raises():
    with pytest.raises(ValueError):
        selection.gate_and_rank([], min_trades=300, oos_min_pf=1.0, rank_by="nope", per_asset=2)
