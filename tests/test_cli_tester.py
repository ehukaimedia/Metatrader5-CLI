import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner


def _purge_cli_cache():
    for name in list(sys.modules):
        if name == "mt5.cli" or name == "mt5.emit":
            sys.modules.pop(name, None)


@pytest.fixture
def cli():
    _purge_cli_cache()
    from mt5.cli import main
    yield CliRunner(), main
    _purge_cli_cache()


def test_tester_list_emits_envelope(tmp_path, monkeypatch, cli):
    runner, main = cli
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main, ["--json", "tester", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert isinstance(payload["data"], list)


def test_tester_show_unknown_run(tmp_path, monkeypatch, cli):
    runner, main = cli
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(main, ["--json", "tester", "show", "no_such_run"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "RUN_NOT_FOUND"


def test_tester_show_parses_existing_run(tmp_path, monkeypatch, cli):
    runner, main = cli
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "results" / "2026-05-15T10-00-00_alpha_AUDUSD_M5"
    run_dir.mkdir(parents=True)
    (run_dir / "report.html").write_text(
        "<html><body><table>"
        "<tr><td>Symbol</td><td>AUDUSD</td><td>Period</td>"
        "<td>M5 (2024.01.01-2024.06.30)</td></tr>"
        "<tr><td>Total Trades</td><td>7</td></tr>"
        "</table></body></html>",
        encoding="utf-8",
    )

    result = runner.invoke(main, ["--json", "tester", "show", run_dir.name])

    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["run_id"] == run_dir.name
    assert payload["data"]["stats"]["total_trades"] == 7


def test_tester_ea_single_threads_options(monkeypatch, cli):
    runner, main = cli
    import mt5.cli as cli_mod

    captured = {}

    def fake_single(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {"run_id": "r1"}}

    monkeypatch.setattr(cli_mod._tester_ea, "single", fake_single)

    result = runner.invoke(
        main,
        [
            "--json",
            "tester",
            "ea",
            "single",
            "--expert",
            "alpha",
            "--symbol",
            "AUDUSD",
            "--tf",
            "M5",
            "--from",
            "2024-01-01",
            "--to",
            "2024-06-30",
            "--modelling",
            "ohlc-1m",
            "--deposit",
            "25000",
            "--currency",
            "USD",
            "--leverage",
            "100",
            "--visual",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True
    assert captured["expert"] == "alpha"
    assert captured["timeframe"] == "M5"
    assert captured["modelling"] == "ohlc-1m"
    assert captured["deposit"] == 25000.0
    assert captured["leverage"] == 100
    assert captured["visual"] is True


def test_tester_ea_scanner_splits_symbols(monkeypatch, cli):
    runner, main = cli
    import mt5.cli as cli_mod

    captured = {}

    def fake_scanner(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {"per_symbol": []}}

    monkeypatch.setattr(cli_mod._tester_ea, "scanner", fake_scanner)

    runner.invoke(
        main,
        [
            "--json",
            "tester",
            "ea",
            "scanner",
            "--expert",
            "alpha",
            "--symbols",
            "AUDUSD, EURUSD,,GBPUSD",
            "--tf",
            "M5",
            "--from",
            "2024-01-01",
            "--to",
            "2024-06-30",
        ],
    )

    assert captured["symbols"] == ["AUDUSD", "EURUSD", "GBPUSD"]


def test_tester_indicator_visual_threads_options(monkeypatch, cli):
    runner, main = cli
    import mt5.cli as cli_mod

    captured = {}

    def fake_visual(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {"run_id": "i1"}}

    monkeypatch.setattr(cli_mod._tester_indicator, "visual", fake_visual)

    result = runner.invoke(
        main,
        [
            "--json",
            "tester",
            "indicator",
            "visual",
            "--indicator",
            "donchian",
            "--symbol",
            "AUDUSD",
            "--tf",
            "M5",
            "--from",
            "2024-01-01",
            "--to",
            "2024-06-30",
        ],
    )

    assert json.loads(result.output)["ok"] is True
    assert captured["indicator_name"] == "donchian"
    assert captured["timeframe"] == "M5"


def test_tester_invalid_choice_uses_envelope(cli):
    runner, main = cli
    result = runner.invoke(
        main,
        [
            "--json",
            "tester",
            "ea",
            "single",
            "--expert",
            "alpha",
            "--symbol",
            "AUDUSD",
            "--tf",
            "M5",
            "--from",
            "2024-01-01",
            "--to",
            "2024-06-30",
            "--modelling",
            "bad-model",
        ],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MT5_INVALID_PARAMS"
