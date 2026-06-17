"""mt5 quant run / list / show CLI wiring (no terminal — dry-run + manifest I/O)."""
from click.testing import CliRunner

from mt5.cli import main
from mt5_cli.quant import store


def test_quant_run_dry_run_emits_envelope():
    r = CliRunner().invoke(main, [
        "--json", "quant", "run", "--expert", "demo", "--symbols", "EURUSD,XAUUSD",
        "--tf", "H1,H2", "--from", "2022-01-01", "--to", "2024-12-31", "--split", "0.70",
        "--dry-run"])
    assert r.exit_code == 0
    assert '"schema": "quant.v1"' in r.output
    assert '"dry_run": true' in r.output
    assert '"planned_launches": 12' in r.output  # 4 cells * 3 launches


def test_quant_run_accepts_min_is_trades_option():
    # the option parses and forwards into campaign.run (a missing kwarg would TypeError)
    r = CliRunner().invoke(main, [
        "--json", "quant", "run", "--expert", "demo", "--symbols", "EURUSD", "--tf", "H1",
        "--from", "2022-01-01", "--to", "2024-12-31", "--split", "0.70",
        "--min-is-trades", "150", "--dry-run"])
    assert r.exit_code == 0
    assert '"schema": "quant.v1"' in r.output


def test_quant_run_bad_rank_by_emits_invalid_rank_by():
    r = CliRunner().invoke(main, [
        "--json", "quant", "run", "--expert", "demo", "--symbols", "EURUSD", "--tf", "H1",
        "--from", "2022-01-01", "--to", "2024-12-31", "--split", "0.70",
        "--rank-by", "sortino", "--dry-run"])
    assert r.exit_code == 0 and "INVALID_RANK_BY" in r.output


def test_quant_list_and_show_roundtrip():
    runner = CliRunner()
    with runner.isolated_filesystem():
        cid = "2026-06-16T19-40-00_quant_demo"
        store.write_manifest(cid, {"schema": "quant.v1", "ranked": []}, root="results")
        listed = runner.invoke(main, ["--json", "quant", "list"])
        assert cid in listed.output
        shown = runner.invoke(main, ["--json", "quant", "show", cid])
        assert '"schema": "quant.v1"' in shown.output
        missing = runner.invoke(main, ["--json", "quant", "show", "nope"])
        assert "RUN_NOT_FOUND" in missing.output
