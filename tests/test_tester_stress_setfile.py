"""tester ea stress --set-file: the winning parameter set is threaded into every rung."""
from click.testing import CliRunner

from mt5.cli import main
from mt5_cli.tester import ea, ini_builder


def test_stress_threads_set_file_into_every_rung(monkeypatch, tmp_path):
    seen = []

    def fake_single(**kw):
        seen.append(kw.get("set_file"))
        return {"ok": True, "data": {"run_id": "r", "stats": {"net_profit": 100.0}}}

    monkeypatch.setattr(ea, "single", fake_single)
    set_file = tmp_path / "winner.set"
    set_file.write_text("Risk=1.0\n", encoding="utf-8")

    ea.stress(expert="demo", symbol="EURUSD", timeframe="H1", from_date="2024-01-01",
              to_date="2024-06-30", delays=[0, 100, 500], set_file=set_file, results_root=tmp_path)

    assert len(seen) == 3 and all(s == set_file for s in seen)


def test_stress_without_set_file_passes_none(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(ea, "single",
                        lambda **kw: seen.append(kw.get("set_file")) or {"ok": True, "data": {"stats": {"net_profit": 1.0}}})
    ea.stress(expert="demo", symbol="EURUSD", timeframe="H1", from_date="2024-01-01",
              to_date="2024-06-30", delays=[0, 100], results_root=tmp_path)
    assert seen == [None, None]


def test_build_ea_ini_emits_expert_parameters_for_set_file():
    # the rung's tester.ini carries ExpertParameters=<winner.set basename> (acceptance 15)
    ini = ini_builder.build_ea_ini(expert="demo", symbol="EURUSD", timeframe="H1",
                                   from_date="2024-01-01", to_date="2024-06-30",
                                   set_file="results/child/winner.set")
    assert "ExpertParameters=winner.set" in ini


def test_cli_stress_set_file_reaches_library(monkeypatch, tmp_path):
    import mt5.cli as cli
    captured = {}
    monkeypatch.setattr(cli._tester_ea, "stress",
                        lambda **kw: captured.update(kw) or {"ok": True, "data": {"schema": "stress.v1"}})
    setf = tmp_path / "w.set"
    setf.write_text("Risk=1.0\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["--json", "tester", "ea", "stress", "--expert", "demo",
        "--symbol", "EURUSD", "--tf", "H1", "--from", "2024-01-01", "--to", "2024-06-30",
        "--set-file", str(setf)])
    assert r.exit_code == 0 and captured.get("set_file") == str(setf)
