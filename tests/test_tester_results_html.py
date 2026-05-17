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
