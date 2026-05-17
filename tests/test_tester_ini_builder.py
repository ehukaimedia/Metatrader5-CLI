"""Tests for mt5_cli/tester/ini_builder.py - .ini text + UTF-16-LE BOM write."""
import pytest

from mt5_cli.tester import ini_builder


def test_build_single_ea_ini_includes_required_fields(tmp_path):
    text = ini_builder.build_ea_ini(
        expert="alpha",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="real-ticks",
        deposit=10000,
        currency="USD",
        leverage=50,
        report_path=tmp_path / "report.html",
    )
    assert "[Tester]" in text
    assert "Expert=alpha" in text
    assert "Symbol=AUDUSD" in text
    assert "Period=M5" in text
    assert "FromDate=2024.01.01" in text
    assert "ToDate=2024.06.30" in text
    assert "Model=0" in text  # real-ticks
    assert "Deposit=10000" in text
    assert "Leverage=50" in text
    assert "Optimization=0" in text  # default single run
    assert "Visual=0" in text


def test_build_ea_ini_with_visual_flag():
    text = ini_builder.build_ea_ini(
        expert="alpha", symbol="EURUSD", timeframe="H1",
        from_date="2024-01-01", to_date="2024-06-30",
        visual=True,
    )
    assert "Visual=1" in text


def test_build_ea_ini_with_optimization_and_forward():
    text = ini_builder.build_ea_ini(
        expert="alpha", symbol="EURUSD", timeframe="H1",
        from_date="2024-01-01", to_date="2024-06-30",
        optimization=2,  # genetic
        forward="2024-04-01",
    )
    assert "Optimization=2" in text
    assert "ForwardMode=1" in text
    assert "ForwardDate=2024.04.01" in text


def test_build_ea_ini_with_set_file_includes_just_basename(tmp_path):
    """ExpertParameters takes the .set basename, not the full path."""
    set_file = tmp_path / "presets" / "alpha.AUDUSD.M5.set"
    text = ini_builder.build_ea_ini(
        expert="alpha", symbol="AUDUSD", timeframe="M5",
        from_date="2024-01-01", to_date="2024-06-30",
        set_file=set_file,
    )
    assert "ExpertParameters=alpha.AUDUSD.M5.set" in text


def test_build_indicator_visual_ini():
    text = ini_builder.build_indicator_ini(
        indicator="donchian",
        symbol="AUDUSD",
        timeframe="M5",
        from_date="2024-01-01",
        to_date="2024-06-30",
        modelling="ohlc-1m",
    )
    assert "Indicator=donchian" in text
    assert "Visual=1" in text  # indicators always visual


def test_modelling_maps_to_mt5_codes():
    assert ini_builder._modelling_code("real-ticks") == 0
    assert ini_builder._modelling_code("every-tick") == 1
    assert ini_builder._modelling_code("ohlc-1m") == 2
    assert ini_builder._modelling_code("open-only") == 2
    assert ini_builder._modelling_code("math") == 4


def test_unknown_modelling_raises():
    with pytest.raises(ValueError):
        ini_builder._modelling_code("invalid")


def test_write_ini_uses_utf16_le_with_bom(tmp_path):
    """MT5 silently ignores the [Tester] block if the .ini is UTF-8.
    Must be UTF-16-LE with a BOM (\\xff\\xfe). Lock the binary shape."""
    ini = tmp_path / "tester.ini"
    text = "[Tester]\nExpert=alpha\n"
    ini_builder.write_ini(ini, text)
    raw = ini.read_bytes()
    assert raw[:2] == b"\xff\xfe", "UTF-16-LE BOM missing"
    decoded = raw[2:].decode("utf-16-le")
    assert "[Tester]" in decoded
    assert "Expert=alpha" in decoded


def test_write_ini_creates_parent_dir(tmp_path):
    """`tester.ini` lives under <run-dir>/, which may not exist yet."""
    nested = tmp_path / "fresh" / "run" / "tester.ini"
    ini_builder.write_ini(nested, "[Tester]\n")
    assert nested.exists()


def test_render_set_supports_fixed_and_optimization_params():
    text = ini_builder.render_set([
        "Risk=1.0",
        "FastPeriod=9,5,1,21",
    ])
    assert "Risk=1.0" in text
    assert "FastPeriod=9||5||1||21||Y" in text


def test_write_set_creates_parent_dir(tmp_path):
    target = tmp_path / "run" / "alpha.set"
    ini_builder.write_set(target, {"Risk": "1.0"})
    assert target.read_text(encoding="utf-8") == "Risk=1.0\n"


def test_render_set_rejects_malformed_param():
    with pytest.raises(ValueError):
        ini_builder.render_set(["Risk"])
