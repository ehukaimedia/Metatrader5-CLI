"""tester ea stress --set-file: the winning parameter set is threaded into every rung."""
from mt5_cli.tester import ea


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
