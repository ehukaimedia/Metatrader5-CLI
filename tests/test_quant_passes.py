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
    parsed = [{"FastPeriod": 9, "ProfitFactor": 1.5, "Trades": 400, "Sharpe": 1.1, "Profit": 600}]
    rows = passes.read_rows(parsed, param_names=["FastPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9"}        # params stringified for .set
    assert rows[0]["is"]["profit_factor"] == 1.5
    assert rows[0]["is"]["net_profit"] == 600.0


def test_read_against_repo_canonical_fixture():
    # the repo's own sample_optimization.xml is the closest thing to real MT5 shape;
    # projecting it must yield the load-bearing fields (PF/trades/net) with the SAME
    # tag constants, and document that it carries no Sharpe column.
    fix = Path(__file__).parent / "fixtures" / "sample_optimization.xml"
    rows = passes.read(fix, param_names=["FastPeriod", "SlowPeriod"])
    assert len(rows) == 2
    first = rows[0]
    assert first["params"] == {"FastPeriod": "9", "SlowPeriod": "21"}
    assert first["is"]["profit_factor"] == 1.42
    assert first["is"]["trades"] == 412
    assert first["is"]["net_profit"] == 1234.56     # <Profit>, not <Result>
    assert first["is"]["sharpe"] is None            # canonical fixture has no Sharpe column


def test_missing_columns_become_none():
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod"])
    assert rows[0]["is"] == {"profit_factor": None, "trades": None, "sharpe": None, "net_profit": None}


def test_absent_requested_param_surfaces_as_none():
    # a requested input missing from the report row is surfaced, not omitted
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod", "SlowPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9", "SlowPeriod": None}
