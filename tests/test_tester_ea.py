from pathlib import Path

from mt5_cli.tester import ea


def test_single_returns_envelope_with_run_id(monkeypatch, tmp_path):
    def fake_launch(*, ini_path, run_dir, timeout):
        run_path = Path(run_dir)
        (run_path / "report.html").write_text(
            "<html><body><table>"
            "<tr><td>Symbol</td><td>AUDUSD</td><td>Period</td>"
            "<td>M5 (2024.01.01-2024.06.30)</td></tr>"
            "<tr><td>Total Trades</td><td>10</td></tr>"
            "</table></body></html>",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_path)},
        }

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: {"name": name, "source": "x.mq5", "compiled": True},
    )

    out = ea.single(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="ohlc-1m",
        results_root=tmp_path,
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["expert"] == "alpha"
    assert data["symbol"] == "AUDUSD"
    assert "run_id" in data
    assert data["stats"]["total_trades"] == 10


def test_single_returns_fail_when_ea_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(ea.discovery, "get_ea", lambda name: None)
    out = ea.single(
        expert="missing",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "EA_NOT_FOUND"


def test_single_bad_modelling_returns_envelope_before_side_effects(monkeypatch, tmp_path):
    calls = {"launcher": 0, "discovery": 0}

    monkeypatch.setattr(ea.launcher, "run", lambda **kwargs: calls.__setitem__("launcher", 1))
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: calls.__setitem__("discovery", 1),
    )

    out = ea.single(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="bad-model",
        results_root=tmp_path,
    )

    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_MODELLING"
    assert calls == {"launcher": 0, "discovery": 0}
    assert not any(tmp_path.iterdir())


def test_single_fails_when_launch_succeeds_without_report(monkeypatch, tmp_path):
    def fake_launch(*, ini_path, run_dir, timeout):
        return {
            "ok": True,
            "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)},
        }

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: {"name": name, "source": "x.mq5", "compiled": True},
    )

    out = ea.single(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )

    assert out["ok"] is False
    assert out["error"]["code"] == "TESTER_REPORT_MISSING"


def test_single_requires_compiled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: {"name": name, "source": "x.mq5", "compiled": False},
    )
    out = ea.single(
        expert="uncompiled",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "EA_NOT_COMPILED"


def test_optimize_calls_launcher_with_optimization_flag(monkeypatch, tmp_path):
    captured_inis = []

    def fake_launch(*, ini_path, run_dir, timeout):
        captured_inis.append(Path(ini_path).read_bytes()[2:].decode("utf-16-le"))
        Path(run_dir, "report.html").write_text(
            "<html><body><table></table></body></html>",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)},
        }

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: {"name": name, "source": "x.mq5", "compiled": True},
    )

    out = ea.optimize(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        mode="complete",
        results_root=tmp_path,
    )

    assert out["ok"] is True
    assert "Optimization=1" in captured_inis[0]


def test_optimize_rejects_unknown_mode(monkeypatch, tmp_path):
    out = ea.optimize(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        mode="random",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_OPT_MODE"


def test_optimize_bad_modelling_returns_envelope(monkeypatch, tmp_path):
    out = ea.optimize(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="bad-model",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_MODELLING"
    assert not any(tmp_path.iterdir())


def test_optimize_generates_set_file_from_params(monkeypatch, tmp_path):
    captured_inis = []
    captured_run_dirs = []

    def fake_launch(*, ini_path, run_dir, timeout):
        captured_inis.append(Path(ini_path).read_bytes()[2:].decode("utf-16-le"))
        captured_run_dirs.append(Path(run_dir))
        Path(run_dir, "optimization.xml").write_text("<results></results>", encoding="utf-8")
        return {
            "ok": True,
            "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)},
        }

    monkeypatch.setattr(ea.launcher, "run", fake_launch)
    monkeypatch.setattr(
        ea.discovery,
        "get_ea",
        lambda name: {"name": name, "source": "x.mq5", "compiled": True},
    )

    out = ea.optimize(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        params=["Risk=1.0", "FastPeriod=9,5,1,21"],
        results_root=tmp_path,
    )

    assert out["ok"] is True
    set_file = captured_run_dirs[0] / "alpha.AUDUSD.M5.set"
    assert set_file.exists()
    assert "FastPeriod=9||5||1||21||Y" in set_file.read_text(encoding="utf-8")
    assert "ExpertParameters=alpha.AUDUSD.M5.set" in captured_inis[0]


def test_optimize_rejects_params_and_set_file_together(tmp_path):
    existing = tmp_path / "preset.set"
    existing.write_text("Risk=1.0\n", encoding="utf-8")
    out = ea.optimize(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        params=["Risk=1.0"],
        set_file=existing,
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "MT5_INVALID_PARAMS"


def test_scanner_runs_per_symbol(monkeypatch, tmp_path):
    runs = []

    def fake_single(**kwargs):
        runs.append(kwargs["symbol"])
        return {
            "ok": True,
            "data": {
                "run_id": kwargs["symbol"],
                "symbol": kwargs["symbol"],
                "stats": {"total_trades": 1},
            },
        }

    monkeypatch.setattr(ea, "single", fake_single)
    out = ea.scanner(
        expert="alpha",
        symbols=["AUDUSD", "EURUSD", "GBPUSD"],
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )

    assert out["ok"] is True
    assert sorted(runs) == ["AUDUSD", "EURUSD", "GBPUSD"]
    assert len(out["data"]["per_symbol"]) == 3


def test_stress_adds_delay_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ea,
        "single",
        lambda **kwargs: {"ok": True, "data": {"run_id": "r1", "symbol": kwargs["symbol"]}},
    )
    out = ea.stress(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        delays_ms=75,
        results_root=tmp_path,
    )
    assert out["ok"] is True
    assert out["data"]["stress_delay_ms"] == 75
