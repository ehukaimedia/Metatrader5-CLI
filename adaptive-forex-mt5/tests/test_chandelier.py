"""Chandelier trail: highest_high - ATR*multiplier (buy), mirror for sell."""
from __future__ import annotations

import math

import trade_manager


def _bars(highs, lows, closes):
    return [{"high": h, "low": l, "close": c} for h, l, c in zip(highs, lows, closes)]


def test_chandelier_buy_simple():
    bars = _bars(
        highs=[1.10, 1.11, 1.12],
        lows=[1.08, 1.09, 1.105],
        closes=[1.09, 1.10, 1.115],
    )
    cfg = {"manager": {"chandelier_atr_period": 2, "chandelier_atr_multiplier": 1.0,
                       "chandelier_extreme_lookback": 3}}
    stop = trade_manager.compute_chandelier(bars, direction="buy", cfg=cfg)
    # highest_high = 1.12. TR2 = max(0.02, |1.11-1.09|, |1.09-1.09|) = 0.02.
    # TR3 = max(0.015, |1.12-1.10|, |1.105-1.10|) = 0.02. ATR = 0.02. Stop = 1.10.
    assert math.isclose(stop, 1.10, abs_tol=1e-9)


def test_chandelier_sell_simple():
    bars = _bars(
        highs=[1.12, 1.11, 1.10],
        lows=[1.10, 1.09, 1.08],
        closes=[1.11, 1.10, 1.085],
    )
    cfg = {"manager": {"chandelier_atr_period": 2, "chandelier_atr_multiplier": 1.0,
                       "chandelier_extreme_lookback": 3}}
    stop = trade_manager.compute_chandelier(bars, direction="sell", cfg=cfg)
    assert math.isclose(stop, 1.10, abs_tol=1e-9)


def test_chandelier_too_few_bars_returns_none():
    bars = _bars(highs=[1.10], lows=[1.08], closes=[1.09])
    cfg = {"manager": {"chandelier_atr_period": 22, "chandelier_atr_multiplier": 3.0,
                       "chandelier_extreme_lookback": 22}}
    assert trade_manager.compute_chandelier(bars, direction="buy", cfg=cfg) is None
