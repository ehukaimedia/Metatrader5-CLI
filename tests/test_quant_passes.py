"""Quant passes: project optimization passes into {params, is} records.

Uses a SYNTHETIC fixture (tests/fixtures/quant/optimization_synthetic.xml) — not
a real MT5 capture; see that dir's README. These tests pin the projection logic;
the real-artifact shape is verified in plan Task 0.
"""
from pathlib import Path

from mt5_cli.quant import passes

FIX = Path(__file__).parent / "fixtures" / "quant" / "optimization_synthetic.xml"


def test_read_projects_params_and_is_metrics():
    rows = passes.read(FIX, param_names=["FastPeriod", "SlowPeriod"])
    assert len(rows) == 3
    r = rows[0]
    assert r["params"] == {"FastPeriod": "9", "SlowPeriod": "21"}
    assert r["is"]["profit_factor"] == 1.20
    assert r["is"]["trades"] == 420
    assert r["is"]["net_profit"] == 300.0


def test_read_rows_over_already_parsed_list():
    parsed = [{"FastPeriod": 9, "ProfitFactor": 1.5, "Trades": 400, "Sharpe": 1.1, "Result": 600}]
    rows = passes.read_rows(parsed, param_names=["FastPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9"}        # params stringified for .set
    assert rows[0]["is"]["profit_factor"] == 1.5
    assert rows[0]["is"]["net_profit"] == 600.0


def test_missing_columns_become_none():
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod"])
    assert rows[0]["is"] == {"profit_factor": None, "trades": None, "sharpe": None, "net_profit": None}


def test_absent_requested_param_surfaces_as_none():
    # a requested input missing from the report row is surfaced, not omitted
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod", "SlowPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9", "SlowPeriod": None}
