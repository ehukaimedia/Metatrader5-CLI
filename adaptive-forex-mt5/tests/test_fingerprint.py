"""Unit tests for setup_fingerprint computation."""
from __future__ import annotations

import pytest

import fingerprint


def _scan(**overrides):
    base = {
        "pair": "USDJPY",
        "direction": "buy",
        "setup": {"entry": 156.500, "sl": 156.300, "tp": 157.000},
        "poi": {"id": "FVG-1", "top": 156.520, "bottom": 156.480},
        "reasoning": {
            "structure": {"last_confirmed_event": {
                "type": "BOS",
                "level": {"time": "2026-05-08T12:00:00+00:00"},
            }},
        },
        "bar_time": "2026-05-08T12:05:00+00:00",
        "digits": 3,
    }
    base.update(overrides)
    return base


def test_fingerprint_is_deterministic():
    a = fingerprint.compute(_scan())
    b = fingerprint.compute(_scan())
    assert a == b
    assert isinstance(a, str)
    assert len(a) == 16  # 64-bit hex


def test_fingerprint_changes_when_levels_change():
    base = fingerprint.compute(_scan())
    moved_entry = fingerprint.compute(_scan(setup={"entry": 156.501, "sl": 156.300, "tp": 157.000}))
    assert base != moved_entry


def test_fingerprint_stable_under_irrelevant_field():
    base = fingerprint.compute(_scan())
    base_with_extra = _scan()
    base_with_extra["unrelated_field"] = "noise"
    assert base == fingerprint.compute(base_with_extra)


def test_fingerprint_changes_on_direction_flip():
    base = fingerprint.compute(_scan())
    flipped = fingerprint.compute(_scan(direction="sell"))
    assert base != flipped


def test_fingerprint_changes_on_poi_id():
    base = fingerprint.compute(_scan())
    other_poi = fingerprint.compute(_scan(poi={"id": "FVG-2", "top": 156.520, "bottom": 156.480}))
    assert base != other_poi


def test_fingerprint_rounds_to_digits():
    """Sub-point noise must not change the fingerprint."""
    base = fingerprint.compute(_scan(setup={"entry": 156.5000001, "sl": 156.300, "tp": 157.000}))
    same = fingerprint.compute(_scan(setup={"entry": 156.500, "sl": 156.300, "tp": 157.000}))
    assert base == same
