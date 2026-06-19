"""Quant matrix: cell expansion, split-date resolution, param validation."""
import pytest

from mt5_cli.quant import matrix


def test_expand_orders_and_dedupes():
    assert matrix.expand(["EURUSD", "XAUUSD"], ["H1", "H2"]) == [
        ("EURUSD", "H1"), ("EURUSD", "H2"), ("XAUUSD", "H1"), ("XAUUSD", "H2"),
    ]
    assert matrix.expand(["EURUSD", "EURUSD"], ["H1", "H1"]) == [("EURUSD", "H1")]


def test_expand_empty_raises_emptymatrix():
    with pytest.raises(matrix.EmptyMatrix):
        matrix.expand([], ["H1"])
    with pytest.raises(matrix.EmptyMatrix):
        matrix.expand(["EURUSD"], [])
    # EmptyMatrix is a ValueError subclass
    with pytest.raises(ValueError):
        matrix.expand([], [])


def test_resolve_split_fraction_uses_floor():
    # 1095-day span, floor(0.70*1095)=766 days -> 2024-02-06 (first OOS day)
    assert matrix.resolve_split("2022-01-01", "2024-12-31", "0.70") == "2024-02-06"


def test_resolve_split_explicit_date_passthrough():
    assert matrix.resolve_split("2022-01-01", "2024-12-31", "2024-06-01") == "2024-06-01"


def test_resolve_split_invalid_raises():
    for bad in ("1.5", "0", "abc", "", "2030-01-01"):
        with pytest.raises(matrix.InvalidSplit):
            matrix.resolve_split("2022-01-01", "2024-12-31", bad)


def test_is_end_is_day_before_split():
    assert matrix.is_end("2024-02-06") == "2024-02-05"


def test_param_names_extracted():
    assert matrix.param_names(["FastPeriod=9,5,1,21", "Risk=1.0"]) == ["FastPeriod", "Risk"]


def test_optimized_param_names_and_fixed_params_are_split():
    specs = ["InpAllowTrading=true", "FastPeriod=9,5,1,21", "RunTag=stage1"]

    assert matrix.optimized_param_names(specs) == ["FastPeriod"]
    assert matrix.fixed_params(specs) == {
        "InpAllowTrading": "true",
        "RunTag": "stage1",
    }


def test_parse_params_ok_and_bad():
    assert matrix.parse_params(["Risk=1.0,0.5,0.5,3.0"]) == ["Risk=1.0,0.5,0.5,3.0"]
    with pytest.raises(matrix.InvalidParam):
        matrix.parse_params(["Risk="])
