"""
indicator.py — Technical indicators via pandas-ta for the MT5 CLI.

All indicator functions delegate rate fetching to ``rates.fetch()`` (spec §6.4).
This module never imports MetaTrader5 directly.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import pandas as pd
import pandas_ta as ta  # noqa: F401  (imported for its DataFrame accessor)

from metatrader5_cli.mt5.core import rates as rates_module
from metatrader5_cli.mt5.utils import mt5_backend as bridge


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _values_with_time(df: pd.DataFrame, col: str, field: str) -> list[dict]:
    """Return [{time, <field>}] for *col*, dropping NaN rows."""
    return [
        {"time": row["time"], field: float(row[col])}
        for _, row in df.iterrows()
        if not pd.isna(row[col])
    ]


def _point_for_symbol(symbol: str, rows: list[dict]) -> float:
    """Return symbol point from MT5 when available, otherwise infer from prices."""
    try:
        info = bridge.mt5_call("symbol_info", symbol)
        point = getattr(info, "point", None)
        if point and point > 0:
            return float(point)
    except Exception:  # noqa: BLE001
        pass

    max_digits = 0
    for row in rows:
        for key in ("open", "high", "low", "close"):
            try:
                dec = Decimal(str(row[key])).normalize()
            except (InvalidOperation, KeyError):
                continue
            max_digits = max(max_digits, max(0, -dec.as_tuple().exponent))
    return 10 ** (-max_digits) if max_digits else 0.0001


def _inferred_digits(rows: list[dict]) -> int:
    max_digits = 0
    for row in rows:
        for key in ("open", "high", "low", "close"):
            try:
                dec = Decimal(str(row[key])).normalize()
            except (InvalidOperation, KeyError):
                continue
            max_digits = max(max_digits, max(0, -dec.as_tuple().exponent))
    return max_digits


def _pip_size_for_symbol(symbol: str, rows: list[dict], point: float) -> float:
    """Return pip size for visual FVG labels, matching the MQ5 indicator."""
    digits = None
    try:
        info = bridge.mt5_call("symbol_info", symbol)
        raw_digits = getattr(info, "digits", None)
        if isinstance(raw_digits, int):
            digits = raw_digits
    except Exception:  # noqa: BLE001
        pass
    if digits is None:
        digits = _inferred_digits(rows)
    if digits in {3, 5}:
        return point * 10.0
    return point


def _fvg_id(symbol: str, timeframe: str, formed_at: str, direction: str, lower: float, upper: float) -> str:
    return f"{symbol.upper()}-{timeframe.upper()}-{formed_at}-{direction}-{lower:.10g}-{upper:.10g}"


def _mitigation_state(rows: list[dict], start_idx: int, direction: str, lower: float, upper: float, mode: str) -> tuple[str, float]:
    if upper <= lower:
        return "filled", 1.0
    future = rows[start_idx + 1:]
    if not future:
        return "open", 0.0

    if direction == "bullish":
        field = "close" if mode == "body" else "low"
        deepest = min(float(row[field]) for row in future)
        if deepest <= lower:
            return "filled", 1.0
        if deepest < upper:
            return "partial", round((upper - deepest) / (upper - lower), 4)
        return "open", 0.0

    field = "close" if mode == "body" else "high"
    highest = max(float(row[field]) for row in future)
    if highest >= upper:
        return "filled", 1.0
    if highest > lower:
        return "partial", round((highest - lower) / (upper - lower), 4)
    return "open", 0.0


def _true_range(prev_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr_at(rows: list[dict], idx: int, period: int = 14) -> float | None:
    if idx <= 0:
        return None
    ranges = []
    start = max(1, idx - period + 1)
    for j in range(start, idx + 1):
        ranges.append(
            _true_range(
                float(rows[j - 1]["close"]),
                float(rows[j]["high"]),
                float(rows[j]["low"]),
            )
        )
    if not ranges:
        return None
    return sum(ranges) / len(ranges)


def _distance_from_price(price: float, lower: float, upper: float, point: float) -> float:
    if not point:
        return 0.0
    if lower <= price <= upper:
        return 0.0
    if price > upper:
        return round((price - upper) / point, 2)
    return round((lower - price) / point, 2)


def _zone_render(direction: str, timeframe: str, size_points: float, visual_label: str) -> dict:
    color = "rgba(16,185,129,0.18)" if direction == "bullish" else "rgba(239,68,68,0.18)"
    border = "#10b981" if direction == "bullish" else "#ef4444"
    return {
        "kind": "zone",
        "fill": color,
        "border": border,
        "boundary_style": "solid",
        "midline_style": "dashed",
        "label": visual_label,
        "cli_pair": f"mt5 --json indicator fvg SYMBOL {timeframe.upper()}",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ema(symbol: str, timeframe: str, period: int, bars: int = 100) -> dict:
    """Exponential Moving Average (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    df.ta.ema(length=period, append=True)
    col = f"EMA_{period}"
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe, "period": period,
            "values": _values_with_time(df, col, "ema"),
        },
    }


def atr(symbol: str, timeframe: str, period: int = 14, bars: int = 100) -> dict:
    """Average True Range (spec §6.4)."""
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result
    df = pd.DataFrame(result["data"])
    if len(df) < period:
        return _fail(
            "INDICATOR_INVALID_INPUT",
            f"--bars ({len(df)}) must be >= --period ({period}) to compute ATR.",
        )
    atr_series = df.ta.atr(
        high=df["high"], low=df["low"], close=df["close"], length=period
    )
    rows = [
        {"time": df.iloc[i]["time"], "atr": float(v)}
        for i, v in enumerate(atr_series)
        if not pd.isna(v)
    ]
    return {
        "ok": True,
        "data": {
            "symbol": symbol, "timeframe": timeframe,
            "period": period, "values": rows,
        },
    }


def fvg(
    symbol: str,
    timeframe: str,
    bars: int = 300,
    min_points: float = 0.0,
    min_atr_multiple: float = 0.0,
    direction: str = "both",
    state: str = "all",
    mitigation: str = "body",
    limit: int | None = None,
) -> dict:
    """Fair Value Gap zones.

    Each FVG is returned as one zone object with nested upper/lower boundaries,
    not as two independent lines. The final fetched bar is excluded because MT5
    ``copy_rates_from_pos(..., 0, n)`` can include the live forming candle.
    """
    direction = direction.lower()
    state = state.lower()
    mitigation = mitigation.lower()
    if direction not in {"both", "bullish", "bearish"}:
        return _fail("INDICATOR_INVALID_INPUT", "direction must be one of: both, bullish, bearish.")
    if state not in {"all", "open", "partial", "filled"}:
        return _fail("INDICATOR_INVALID_INPUT", "state must be one of: all, open, partial, filled.")
    if mitigation not in {"wick", "body"}:
        return _fail("INDICATOR_INVALID_INPUT", "mitigation must be one of: wick, body.")

    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result

    rows = result["data"][:-1]
    if len(rows) < 3:
        return _fail("INDICATOR_ERROR", "FVG requires at least three closed bars.")

    point = _point_for_symbol(symbol, rows)
    pip_size = _pip_size_for_symbol(symbol, rows, point)
    current_price = float(rows[-1]["close"])
    zones: list[dict] = []
    for i in range(2, len(rows)):
        left = rows[i - 2]
        right = rows[i]
        candidates = []
        if float(left["high"]) < float(right["low"]):
            candidates.append(("bullish", float(left["high"]), float(right["low"])))
        if float(left["low"]) > float(right["high"]):
            candidates.append(("bearish", float(right["high"]), float(left["low"])))

        for gap_direction, lower, upper in candidates:
            if direction != "both" and gap_direction != direction:
                continue
            size_points = round((upper - lower) / point, 2) if point else 0.0
            size_pips = round((upper - lower) / pip_size, 2) if pip_size else 0.0
            if size_points < float(min_points):
                continue
            atr = _atr_at(rows, i)
            if min_atr_multiple and atr is not None and (upper - lower) < (atr * float(min_atr_multiple)):
                continue
            zone_state, fill_pct = _mitigation_state(rows, i, gap_direction, lower, upper, mitigation)
            if state != "all" and zone_state != state:
                continue
            mid = (lower + upper) / 2.0
            formed_at = right["time"]
            side_label = "BULL" if gap_direction == "bullish" else "BEAR"
            visual_label = f"{side_label} FVG {zone_state.upper()} {size_pips:g}p"
            zone = {
                "id": _fvg_id(symbol, timeframe, formed_at, gap_direction, lower, upper),
                "type": "fvg",
                "object_prefix": "EFVG_",
                "visual_label": visual_label,
                "visual_contract": "EhukaiFVG",
                "direction": gap_direction,
                "formed_at": formed_at,
                "anchor_times": [left["time"], rows[i - 1]["time"], right["time"]],
                "lower": lower,
                "upper": upper,
                "mid": mid,
                "size_points": size_points,
                "size_pips": size_pips,
                "atr": round(atr, 10) if atr is not None else None,
                "atr_multiple": round((upper - lower) / atr, 4) if atr else None,
                "distance_points": _distance_from_price(current_price, lower, upper, point),
                "distance_pips": _distance_from_price(current_price, lower, upper, pip_size),
                "state": zone_state,
                "fill_pct": fill_pct,
                "age_bars": len(rows) - 1 - i,
                "boundaries": {
                    "lower": {"price": lower, "role": "lower"},
                    "upper": {"price": upper, "role": "upper"},
                    "mid": {"price": mid, "role": "mid"},
                },
                "render": _zone_render(gap_direction, timeframe, size_points, visual_label),
            }
            zones.append(zone)

    zones.sort(key=lambda z: z["formed_at"], reverse=True)
    if limit is not None and limit > 0:
        zones = zones[:limit]

    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "min_points": min_points,
            "min_atr_multiple": min_atr_multiple,
            "mitigation": mitigation,
            "current_price": current_price,
            "values": zones,
            "zones": zones,
        },
    }


def list_available() -> dict:
    """Return the static catalogue of supported indicators (spec §6.4)."""
    return {
        "ok": True,
        "data": [
            {"name": "ema",  "description": "Exponential Moving Average",             "params": ["period", "bars"]},
            {"name": "atr",  "description": "Average True Range",                     "params": ["period", "bars"]},
            {"name": "fvg",  "description": "Fair Value Gap zones",                   "params": ["bars", "min_points", "min_atr_multiple", "direction", "state", "mitigation", "limit"]},
        ],
    }
