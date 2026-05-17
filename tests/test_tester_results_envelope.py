from pathlib import Path

from mt5_cli.tester import results

FIX = Path(__file__).parent / "fixtures"


def test_parse_optimization_xml_returns_passes():
    passes = results.parse_optimization_xml(FIX / "sample_optimization.xml")
    assert len(passes) == 2
    assert passes[0]["Profit"] == 1234.56
    assert passes[0]["FastPeriod"] == 9
    assert passes[1]["Trades"] == 389


def test_assemble_envelope_combines_html_journal_xml():
    env = results.assemble(
        run_id="run-id-123",
        html_path=FIX / "sample_report.html",
        journal_path=FIX / "sample_journal.csv",
        optimization_path=None,
    )
    assert env["ok"] is True
    data = env["data"]
    assert data["run_id"] == "run-id-123"
    assert data["stats"]["total_trades"] == 412
    assert len(data["deals"]) == 2
    assert len(data["journal_events"]) == 4
    assert data["optimization"] == []


def test_assemble_envelope_includes_optimization():
    env = results.assemble(
        run_id="opt-run-1",
        html_path=FIX / "sample_report.html",
        journal_path=None,
        optimization_path=FIX / "sample_optimization.xml",
    )
    assert env["data"]["optimization"][0]["FastPeriod"] == 9


def test_assemble_tolerates_missing_artifacts(tmp_path):
    env = results.assemble(
        run_id="empty-run",
        html_path=tmp_path / "missing.html",
        journal_path=tmp_path / "missing.csv",
        optimization_path=tmp_path / "missing.xml",
    )
    assert env["ok"] is True
    assert env["data"]["stats"] == {}
    assert env["data"]["deals"] == []
    assert env["data"]["journal_events"] == []
    assert env["data"]["optimization"] == []
