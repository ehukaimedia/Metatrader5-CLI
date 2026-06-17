"""Quant passes: project an MT5 optimization report into {params, is} records.

Tested against tests/fixtures/sample_optimization.xml — a trimmed REAL MT5
SpreadsheetML capture (see that fixture's header comment), so the column-name
mapping is pinned to what MT5 actually emits.
"""
from pathlib import Path

from mt5_cli.quant import passes

FIX = Path(__file__).parent / "fixtures" / "sample_optimization.xml"


def test_read_projects_params_and_is_metrics_from_real_report():
    rows = passes.read(FIX, param_names=["FastPeriod", "SlowPeriod"])
    assert len(rows) == 2
    first = rows[0]
    assert first["params"] == {"FastPeriod": "5", "SlowPeriod": "50"}
    assert first["is"]["profit_factor"] == 2.817202   # "Profit Factor" column
    assert first["is"]["trades"] == 49                 # "Trades"
    assert first["is"]["sharpe"] == 3.971008           # "Sharpe Ratio"
    assert first["is"]["net_profit"] == 1181.89        # "Profit" (net), not "Result"


def test_read_rows_over_already_parsed_list():
    parsed = [{"FastPeriod": 9, "Profit Factor": 1.5, "Trades": 400,
               "Sharpe Ratio": 1.1, "Profit": 600}]
    rows = passes.read_rows(parsed, param_names=["FastPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9"}    # params stringified for .set
    assert rows[0]["is"]["profit_factor"] == 1.5
    assert rows[0]["is"]["net_profit"] == 600.0


def test_missing_columns_become_none():
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod"])
    assert rows[0]["is"] == {"profit_factor": None, "trades": None, "sharpe": None, "net_profit": None}


def test_absent_requested_param_surfaces_as_none():
    rows = passes.read_rows([{"FastPeriod": 9}], param_names=["FastPeriod", "SlowPeriod"])
    assert rows[0]["params"] == {"FastPeriod": "9", "SlowPeriod": None}
