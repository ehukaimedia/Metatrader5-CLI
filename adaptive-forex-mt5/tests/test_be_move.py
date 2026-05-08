"""BE-move math: trigger when favorable distance >= BE_R * initial_risk."""
from __future__ import annotations

import trade_manager


def _row(direction="buy", entry=156.50, initial_risk_price=0.20, point=0.001):
    return {
        "direction": direction, "entry_price": entry,
        "initial_risk_price": initial_risk_price,
        "initial_risk_points": initial_risk_price / point if point else 0.0,
        "point": point,
        "digits": 3,
    }


def test_be_target_buy_below_threshold():
    row = _row()
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 + 0.10  # 0.5R, below 0.8 trigger
    assert trade_manager.compute_be_target(row, cfg, favorable_price) is None


def test_be_target_buy_at_threshold():
    row = _row()
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 + 0.16  # 0.80R
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.505  # entry + 5 points


def test_be_target_sell_at_threshold():
    row = _row(direction="sell", entry=156.50, initial_risk_price=0.20)
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.50 - 0.16
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.495  # entry - 5 points


def test_be_target_uses_fallback_when_risk_zero():
    row = _row()
    row["initial_risk_price"] = 0.0
    row["initial_risk_points"] = 0.0
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5,
                       "be_trigger_points_fallback": 80}}
    favorable_price = 156.50 + 0.080  # 80 points = 0.080 in JPY pairs
    target = trade_manager.compute_be_target(row, cfg, favorable_price)
    assert target == 156.505


def test_be_target_no_favorable_distance_returns_none():
    row = _row()
    cfg = {"manager": {"be_trigger_r": 0.80, "be_buffer_points": 5}}
    favorable_price = 156.40  # below entry for a buy
    assert trade_manager.compute_be_target(row, cfg, favorable_price) is None
