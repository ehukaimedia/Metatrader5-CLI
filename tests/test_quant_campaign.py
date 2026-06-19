"""Quant campaign orchestration — driven by a fake launcher (no terminal)."""
import ast
import pathlib

from mt5_cli.quant import campaign, store


def _fake_opt(tmp_path):
    def fake_optimize(**kw):
        fake_optimize.calls.append(("optimize", kw["from_date"], kw["to_date"]))
        return {"ok": True, "data": {
            "run_id": "opt_run",
            "run_dir": str(tmp_path / "opt"),
            "optimization": [
                {"FastPeriod": "9", "Profit Factor": 1.2, "Trades": 400, "Sharpe Ratio": 0.9, "Profit": 200},
                {"FastPeriod": "12", "Profit Factor": 1.8, "Trades": 500, "Sharpe Ratio": 1.3, "Profit": 700},
            ],
        }}
    fake_optimize.calls = []
    return fake_optimize


def _fake_single():
    def fake_single(**kw):
        fake_single.calls.append(("single", kw["from_date"], kw["to_date"]))
        fake_single.labels.append(kw.get("run_label"))
        return {"ok": True, "data": {
            "run_id": f"run_{kw['from_date']}_{kw['to_date']}",
            "stats": {"total_trades": 400, "net_profit": 1000.0, "profit_factor": 1.7,
                      "sharpe": 1.1, "max_drawdown_pct": 5.0, "win_rate": 0.5},
            "equity_curve": [{"balance": 10000}, {"balance": 11000}],
        }}
    fake_single.calls = []
    fake_single.labels = []
    return fake_single


def test_three_launches_per_cell_with_correct_windows(monkeypatch, tmp_path):
    opt, single = _fake_opt(tmp_path), _fake_single()
    monkeypatch.setattr(campaign.ea, "optimize", opt)
    monkeypatch.setattr(campaign.ea, "single", single)

    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path)

    assert env["ok"] and env["data"]["schema"] == "quant.v1"
    # optimize IS [from, split-1], then OOS single [split, to], then FULL single [from, to]
    assert opt.calls == [("optimize", "2022-01-01", "2024-02-05")]
    assert single.calls == [("single", "2024-02-06", "2024-12-31"),
                            ("single", "2022-01-01", "2024-12-31")]
    # phase-specific run labels prevent OOS/FULL run-id collisions
    assert single.labels == ["quant-oos-demo", "quant-full-demo"]
    # the manifest lists every child run (optimize + OOS + FULL), in launch order
    assert env["data"]["child_run_ids"] == [
        "opt_run", "run_2024-02-06_2024-12-31", "run_2022-01-01_2024-12-31"]
    winner = env["data"]["ranked"][0]
    assert winner["symbol"] == "EURUSD"
    assert winner["is"]["profit_factor"] == 1.8        # best in-sample PF, not full_net
    assert winner["validated"] is True
    # campaign wrote the winner's .set (distinct from the optimize range set) + manifest + report
    assert (tmp_path / "opt" / "winner.demo.EURUSD.H1.set").exists()
    assert env["data"]["artifacts"]["manifest"].endswith("manifest.json")
    # artifacts are persisted in the manifest (so `quant show` reloads them)
    reloaded = store.get_campaign(env["data"]["campaign_id"], root=tmp_path)
    assert "artifacts" in reloaded["data"] and reloaded["data"]["artifacts"]["manifest"]


def test_winner_set_does_not_clobber_optimize_range_set(monkeypatch, tmp_path):
    # ea.optimize(params=...) writes the RANGE set at <run_dir>/<expert>.<symbol>.<tf>.set
    # and that run's tester.ini references it; the campaign must write the winner's FIXED
    # set to a DISTINCT path so the optimize child artifact stays intact.
    opt_dir = tmp_path / "opt"
    opt_dir.mkdir()
    range_set = opt_dir / "demo.EURUSD.H1.set"
    range_set.write_text("FastPeriod=9||5||1||21||Y\n", encoding="utf-8")  # range-shaped
    original = range_set.read_text(encoding="utf-8")

    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path)
    assert env["ok"] is True
    assert range_set.read_text(encoding="utf-8") == original  # optimize range set untouched
    winner_set = opt_dir / "winner.demo.EURUSD.H1.set"
    assert winner_set.exists()
    assert env["data"]["ranked"][0]["set_file"].endswith("winner.demo.EURUSD.H1.set")


def test_fixed_params_are_carried_into_winner_set(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())

    env = campaign.run(
        expert="demo",
        symbols=["EURUSD"],
        timeframes=["H1"],
        from_date="2022-01-01",
        to_date="2024-12-31",
        split="0.70",
        params=["InpAllowTrading=true", "FastPeriod=9,5,1,21"],
        results_root=tmp_path,
    )

    winner = env["data"]["ranked"][0]
    winner_set = tmp_path / "opt" / "winner.demo.EURUSD.H1.set"
    text = winner_set.read_text(encoding="utf-8")
    assert "InpAllowTrading=true" in text
    assert "FastPeriod=12" in text
    assert winner["params"]["InpAllowTrading"] == "true"
    assert winner["params"]["FastPeriod"] == "12"


def test_fixed_param_campaign_runs_single_is_oos_full_without_optimize(monkeypatch, tmp_path):
    def boom_optimize(**kw):
        raise AssertionError("fixed-param campaigns must not launch optimization")

    calls = []
    fixed_set = tmp_path / "fixed.set"

    def fake_single(**kw):
        calls.append(kw)
        data = {
            "run_id": f"single_{len(calls)}",
            "stats": {"total_trades": 420, "net_profit": 1000.0, "profit_factor": 1.4,
                      "sharpe": 1.1, "max_drawdown_pct": 4.0, "win_rate": 0.52},
            "equity_curve": [{"balance": 10000}, {"balance": 11000}],
        }
        if kw.get("params"):
            data["generated_set_file"] = str(fixed_set)
        return {"ok": True, "data": data}

    monkeypatch.setattr(campaign.ea, "optimize", boom_optimize)
    monkeypatch.setattr(campaign.ea, "single", fake_single)

    env = campaign.run(
        expert="demo",
        symbols=["EURUSD"],
        timeframes=["H1"],
        from_date="2022-01-01",
        to_date="2024-12-31",
        split="0.70",
        params=["InpAllowTrading=true", "FastPeriod=12"],
        results_root=tmp_path,
    )

    assert env["ok"] is True
    assert [c["run_label"] for c in calls] == [
        "quant-is-demo", "quant-oos-demo", "quant-full-demo"]
    assert calls[0]["params"] == {"InpAllowTrading": "true", "FastPeriod": "12"}
    assert calls[1]["set_file"] == str(fixed_set)
    assert calls[2]["set_file"] == str(fixed_set)
    assert env["data"]["child_run_ids"] == ["single_1", "single_2", "single_3"]
    winner = env["data"]["ranked"][0]
    assert winner["is"]["profit_factor"] == 1.4
    assert winner["params"]["FastPeriod"] == "12"


def test_fixed_param_campaign_rejects_is_no_winner_without_oos_full(monkeypatch, tmp_path):
    calls = []

    def fake_single(**kw):
        calls.append(kw)
        return {"ok": True, "data": {
            "run_id": "is_only",
            "generated_set_file": str(tmp_path / "fixed.set"),
            "stats": {"total_trades": 420, "profit_factor": 0.9},
        }}

    monkeypatch.setattr(campaign.ea, "optimize", lambda **kw: (_ for _ in ()).throw(
        AssertionError("fixed-param campaigns must not optimize")))
    monkeypatch.setattr(campaign.ea, "single", fake_single)

    env = campaign.run(
        expert="demo",
        symbols=["EURUSD"],
        timeframes=["H1"],
        from_date="2022-01-01",
        to_date="2024-12-31",
        split="0.70",
        params=["FastPeriod=12"],
        results_root=tmp_path,
    )

    assert env["data"]["ranked"] == []
    assert env["data"]["rejected"][0]["reason"] == "NO_WINNER"
    assert len(calls) == 1


def test_empty_matrix_returns_code_and_no_launch(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", lambda **k: (_ for _ in ()).throw(AssertionError("no launch")))
    env = campaign.run(expert="demo", symbols=[], timeframes=["H1"], from_date="2022-01-01",
                       to_date="2024-12-31", split="0.70", results_root=tmp_path)
    assert env["ok"] is False and env["error"]["code"] == "EMPTY_MATRIX"


def test_invalid_split_and_rank_by(tmp_path):
    bad_split = campaign.run(expert="d", symbols=["EURUSD"], timeframes=["H1"],
                             from_date="2022-01-01", to_date="2024-12-31", split="9", results_root=tmp_path)
    assert bad_split["error"]["code"] == "INVALID_SPLIT"
    bad_rank = campaign.run(expert="d", symbols=["EURUSD"], timeframes=["H1"],
                            from_date="2022-01-01", to_date="2024-12-31", split="0.7",
                            rank_by="sortino", results_root=tmp_path)
    assert bad_rank["error"]["code"] == "INVALID_RANK_BY"


def test_dry_run_plans_without_launching(monkeypatch, tmp_path):
    def boom(**kw):
        raise AssertionError("no launch in dry-run")
    monkeypatch.setattr(campaign.ea, "optimize", boom)
    monkeypatch.setattr(campaign.ea, "single", boom)
    env = campaign.run(expert="demo", symbols=["EURUSD", "XAUUSD"], timeframes=["H1", "H2"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       results_root=tmp_path, dry_run=True)
    assert env["data"]["cells"] == 4 and env["data"]["planned_launches"] == 12


def test_optimize_failure_rejects_cell_not_campaign(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize",
                        lambda **k: {"ok": False, "error": {"code": "TESTER_FAILED", "message": "x"}})
    monkeypatch.setattr(campaign.ea, "single", lambda **k: {"ok": True, "data": {}})
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path)
    assert env["ok"] is True
    assert env["data"]["rejected"][0]["reason"] == "CELL_FAILED"
    assert env["data"]["ranked"] == []


def test_no_winner_when_no_pass_clears_min_pf(monkeypatch, tmp_path):
    def fake_optimize(**kw):
        return {"ok": True, "data": {"run_dir": str(tmp_path / "opt"),
                "optimization": [{"FastPeriod": "9", "Profit Factor": 0.6, "Trades": 100}]}}
    monkeypatch.setattr(campaign.ea, "optimize", fake_optimize)
    monkeypatch.setattr(campaign.ea, "single", lambda **k: {"ok": True, "data": {}})
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], min_pf=1.0, results_root=tmp_path)
    assert env["data"]["rejected"][0]["reason"] == "NO_WINNER"
    # all-NO_WINNER campaigns carry a diagnostic hint (loud, not silent), persisted;
    # it names both in-sample gates the winner must clear.
    assert "hint" in env["data"] and "--min-is-trades" in env["data"]["hint"]
    reloaded = store.get_campaign(env["data"]["campaign_id"], root=tmp_path)
    assert "--min-is-trades" in reloaded["data"]["hint"]


def test_all_zero_trade_optimization_is_no_trades_not_no_winner(monkeypatch, tmp_path):
    def fake_optimize(**kw):
        return {"ok": True, "data": {"run_dir": str(tmp_path / "opt"),
                "optimization": [{"FastPeriod": "9", "Profit Factor": None, "Trades": 0}]}}

    monkeypatch.setattr(campaign.ea, "optimize", fake_optimize)
    monkeypatch.setattr(campaign.ea, "single", lambda **k: {"ok": True, "data": {}})

    env = campaign.run(
        expert="demo",
        symbols=["EURUSD"],
        timeframes=["H1"],
        from_date="2022-01-01",
        to_date="2024-12-31",
        split="0.70",
        params=["FastPeriod=9,5,1,21"],
        results_root=tmp_path,
    )

    assert env["data"]["rejected"][0]["reason"] == "NO_TRADES"
    assert "hint" not in env["data"]


def test_hint_absent_when_rejects_are_not_all_no_winner(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    # a winner is found but FULL trades (400) < min_trades -> MIN_TRADES, ranked empty;
    # the reject is not NO_WINNER, so no hint
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], min_trades=500, results_root=tmp_path)
    assert env["data"]["ranked"] == []
    assert env["data"]["rejected"][0]["reason"] == "MIN_TRADES"
    assert "hint" not in env["data"]


def test_min_is_trades_floor_skips_sparse_overfit_winner(monkeypatch, tmp_path):
    # optimization yields a sparse high-PF pass and a dense moderate pass; with an
    # in-sample trade floor the dense pass is crowned, so the sparse overfit pass
    # never wastes an OOS/FULL launch only to be MIN_TRADES-rejected downstream.
    def fake_optimize(**kw):
        return {"ok": True, "data": {"run_id": "opt", "run_dir": str(tmp_path / "opt"),
                "optimization": [
                    {"FastPeriod": "3", "Profit Factor": 9.0, "Trades": 4, "Sharpe Ratio": 2.0, "Profit": 50},
                    {"FastPeriod": "21", "Profit Factor": 1.6, "Trades": 450, "Sharpe Ratio": 1.1, "Profit": 900},
                ]}}
    monkeypatch.setattr(campaign.ea, "optimize", fake_optimize)
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=3,3,1,21"], min_is_trades=300, results_root=tmp_path)
    assert env["ok"] is True
    assert env["data"]["ranked"][0]["is"]["profit_factor"] == 1.6  # dense pass, not PF 9.0
    assert env["data"]["selection"]["min_is_trades"] == 300


def test_min_is_trades_defaults_to_min_trades(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], min_trades=250, results_root=tmp_path)
    assert env["data"]["selection"]["min_is_trades"] == 250  # defaulted from --min-trades


def test_min_is_trades_negative_clamps_to_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    # a nonsensical negative floor clamps to 0 (recorded as 0, the trades check disabled),
    # mirroring per_asset's clamp; the cell still produces a winner.
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], min_is_trades=-5, results_root=tmp_path)
    assert env["ok"] is True and len(env["data"]["ranked"]) == 1
    assert env["data"]["selection"]["min_is_trades"] == 0


def test_oos_single_failure_rejects_cell(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single",
                        lambda **k: {"ok": False, "error": {"code": "TESTER_FAILED", "message": "oos boom"}})
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path)
    assert env["ok"] is True
    assert env["data"]["rejected"][0]["reason"] == "CELL_FAILED"
    assert env["data"]["ranked"] == []


def test_per_asset_zero_clamps_to_one(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], per_asset=0, results_root=tmp_path)
    assert env["ok"] is True and len(env["data"]["ranked"]) == 1  # clamped to keep the top 1


def test_capped_survivors_are_surfaced(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    # two H1+H2 cells for one symbol, per_asset=1 -> one ranked, one surfaced as capped
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1", "H2"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], per_asset=1, results_root=tmp_path)
    assert len(env["data"]["ranked"]) == 1
    assert env["data"]["capped"] == [{"symbol": "EURUSD", "timeframe": "H2"}]


def test_no_results_guard_when_no_records(monkeypatch, tmp_path):
    monkeypatch.setattr(campaign.ea, "optimize", _fake_opt(tmp_path))
    monkeypatch.setattr(campaign.ea, "single", _fake_single())
    monkeypatch.setattr(campaign.selection, "gate_and_rank",
                        lambda *a, **k: {"ranked": [], "rejected": [], "capped": [], "rank_caveat": None})
    env = campaign.run(expert="demo", symbols=["EURUSD"], timeframes=["H1"],
                       from_date="2022-01-01", to_date="2024-12-31", split="0.70",
                       params=["FastPeriod=9,5,1,21"], results_root=tmp_path)
    assert env["ok"] is False and env["error"]["code"] == "NO_RESULTS"


def test_quant_package_never_imports_metatrader5():
    for path in pathlib.Path("mt5_cli/quant").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("MetaTrader5" not in a.name for a in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert "MetaTrader5" not in (node.module or ""), path
