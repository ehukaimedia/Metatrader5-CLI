from pathlib import Path

from mt5_cli.tester import results

FIX = Path(__file__).parent / "fixtures"


def test_parse_optimization_xml_returns_passes():
    passes = results.parse_optimization_xml(FIX / "sample_optimization.xml")
    assert len(passes) == 2
    assert passes[0]["Profit"] == 1181.89          # SpreadsheetML "Profit" column
    assert passes[0]["Profit Factor"] == 2.817202  # spreadsheet headers carry spaces
    assert passes[0]["Trades"] == 49
    assert passes[0]["FastPeriod"] == 5             # EA input as a trailing column
    assert passes[1]["Trades"] == 42


def _cell(value, *, index=None, typ="String"):
    idx = f' ss:Index="{index}"' if index is not None else ""
    return f'<Cell{idx}><Data ss:Type="{typ}">{value}</Data></Cell>'


def _row(*cells: str) -> str:
    return "<Row>" + "".join(cells) + "</Row>"


def _sheet(name: str, *rows: str) -> str:
    return f'<Worksheet ss:Name="{name}"><Table>{"".join(rows)}</Table></Worksheet>'


def _workbook(*worksheets: str) -> str:
    return ('<?xml version="1.0"?>'
            '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
            'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
            f'{"".join(worksheets)}</Workbook>')


def test_parse_optimization_xml_honors_ss_index_gaps(tmp_path):
    # the data row skips the Trades column via ss:Index="4", so FastPeriod must
    # still align under its header rather than shifting left into Trades.
    header = _row(_cell("Pass"), _cell("Profit Factor"), _cell("Trades"), _cell("FastPeriod"))
    data = _row(_cell("7", typ="Number"), _cell("1.9", typ="Number"),
                _cell("12", index=4, typ="Number"))
    p = tmp_path / "opt.xml"
    p.write_text(_workbook(_sheet("Tester Optimizator Results", header, data)), encoding="utf-8")
    passes = results.parse_optimization_xml(p)
    assert len(passes) == 1
    assert passes[0]["Pass"] == 7 and passes[0]["Profit Factor"] == 1.9
    assert passes[0]["Trades"] is None    # skipped column stays empty, not shifted
    assert passes[0]["FastPeriod"] == 12  # ss:Index landed it under the right header


def test_parse_optimization_xml_prefers_named_results_worksheet(tmp_path):
    # a decoy worksheet precedes the real one; selecting the first sheet would read
    # Pass 999 — the parser must pick "Tester Optimizator Results" by name.
    decoy = _sheet("Tester Forward Results",
                   _row(_cell("Pass"), _cell("Profit Factor")),
                   _row(_cell("999", typ="Number"), _cell("0.1", typ="Number")))
    real = _sheet("Tester Optimizator Results",
                  _row(_cell("Pass"), _cell("Profit Factor"), _cell("Trades")),
                  _row(_cell("3", typ="Number"), _cell("2.5", typ="Number"), _cell("400", typ="Number")))
    p = tmp_path / "opt.xml"
    p.write_text(_workbook(decoy, real), encoding="utf-8")
    passes = results.parse_optimization_xml(p)
    assert len(passes) == 1
    assert passes[0]["Pass"] == 3 and passes[0]["Trades"] == 400  # from the named sheet


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
    assert len(data["equity_curve"]) >= 1
    assert len(data["journal_events"]) == 4
    assert data["optimization"] == []


def test_assemble_envelope_includes_optimization():
    env = results.assemble(
        run_id="opt-run-1",
        html_path=FIX / "sample_report.html",
        journal_path=None,
        optimization_path=FIX / "sample_optimization.xml",
    )
    assert env["data"]["optimization"][0]["FastPeriod"] == 5


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
    assert env["data"]["equity_curve"] == []
    assert env["data"]["journal_events"] == []
    assert env["data"]["optimization"] == []
