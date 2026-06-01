from mt5_cli.tester import indicator


def test_visual_returns_envelope_with_run_id(monkeypatch, tmp_path):
    def fake_launch(*, ini_path, run_dir, timeout):
        return {
            "ok": True,
            "data": {"exit_code": 0, "stdout": "", "stderr": "", "run_dir": str(run_dir)},
        }

    monkeypatch.setattr(indicator.launcher, "run", fake_launch)
    monkeypatch.setattr(
        indicator.discovery,
        "get_indicator",
        lambda name: {"name": name, "source": "x.mq5", "compiled": True},
    )

    out = indicator.visual(
        indicator_name="donchian",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="ohlc-1m",
        results_root=tmp_path,
    )

    assert out["ok"] is True
    assert "run_id" in out["data"]
    assert out["data"]["indicator"] == "donchian"


def test_visual_returns_fail_when_indicator_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(indicator.discovery, "get_indicator", lambda name: None)
    out = indicator.visual(
        indicator_name="missing",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INDICATOR_NOT_FOUND"


def test_visual_bad_modelling_returns_envelope_before_side_effects(monkeypatch, tmp_path):
    calls = {"launcher": 0, "discovery": 0}
    monkeypatch.setattr(
        indicator.discovery,
        "get_indicator",
        lambda name: calls.__setitem__("discovery", 1),
    )
    monkeypatch.setattr(
        indicator.launcher,
        "run",
        lambda **kwargs: calls.__setitem__("launcher", 1),
    )
    out = indicator.visual(
        indicator_name="donchian",
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


def test_visual_requires_compiled_indicator(monkeypatch, tmp_path):
    monkeypatch.setattr(
        indicator.discovery,
        "get_indicator",
        lambda name: {"name": name, "source": "x.mq5", "compiled": False},
    )
    out = indicator.visual(
        indicator_name="donchian",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        results_root=tmp_path,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INDICATOR_NOT_COMPILED"
