from pathlib import Path

from mt5_cli.tester import results

FIXTURE = Path(__file__).parent / "fixtures" / "sample_report.html"


def test_parse_html_extracts_stats():
    out = results.parse_html_report(FIXTURE)
    assert out["stats"]["total_trades"] == 412
    assert out["stats"]["win_rate"] == 0.5801
    assert out["stats"]["profit_factor"] == 1.42
    assert out["stats"]["max_drawdown_pct"] == 12.30
    assert out["stats"]["sharpe"] == 0.91
    assert out["stats"]["expectancy"] == 4.20


def test_parse_html_extracts_metadata():
    out = results.parse_html_report(FIXTURE)
    assert out["metadata"]["symbol"] == "AUDUSD"
    assert out["metadata"]["timeframe"] == "M5"
    assert out["metadata"]["from"] == "2024-01-01"
    assert out["metadata"]["to"] == "2024-06-30"
    assert out["metadata"]["initial_deposit"] == 10000.0


def test_parse_html_extracts_deals():
    out = results.parse_html_report(FIXTURE)
    deals = out["deals"]
    assert len(deals) == 2
    assert deals[0]["type"] == "buy"
    assert deals[0]["volume"] == 0.10
    assert deals[1]["profit"] == 12.34


def test_parse_html_includes_derived_equity_curve():
    out = results.parse_html_report(FIXTURE)
    curve = out["equity_curve"]
    assert curve[0]["balance"] == 10000.0
    assert curve[-1]["time"] == "2024.01.05 11:30:00"
    assert curve[-1]["balance"] == 10012.34
    assert curve[-1]["equity"] == 10012.34


def test_parse_html_prefers_explicit_equity_curve(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(
        "<html><body>"
        "<table><tr><td>Symbol</td><td>AUDUSD</td></tr></table>"
        "<table><tr><th>Time</th><th>Balance</th><th>Equity</th></tr>"
        "<tr><td>2024.01.05 10:00:00</td><td>10000.00</td><td>10002.50</td></tr>"
        "</table></body></html>",
        encoding="utf-8",
    )
    out = results.parse_html_report(report)
    assert out["equity_curve"] == [
        {"time": "2024.01.05 10:00:00", "balance": 10000.0, "equity": 10002.5}
    ]
