"""
ehukai.py - Structured mirrors for the vendored Ehukai MT5 indicators.

These helpers intentionally follow the visual indicator contracts used by:
- EhukaiFVG.mq5
- EhukaiMarketStructure.mq5

They are used by visual TDA so agents see one coherent Ehukai interpretation
instead of competing generic analysis labels.
"""
from __future__ import annotations

from datetime import datetime, timezone

from metatrader5_cli.mt5.core import indicator, rates as rates_module


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _tf_label(timeframe: str) -> str:
    value = timeframe.upper()
    return "MN1" if value == "MN" else value


def _effective_pivot_bars(timeframe: str, pivot_bars: int = 4) -> int:
    tf = _tf_label(timeframe)
    pivot = max(1, int(pivot_bars))
    if tf in {"M1", "M5"}:
        return min(pivot, 2)
    if tf in {"M15", "M30"}:
        return min(pivot, 3)
    return pivot


def _classify_swings(swings: list[dict]) -> list[dict]:
    last_high = None
    last_low = None
    classified: list[dict] = []
    for swing in swings:
        item = dict(swing)
        if item["is_high"]:
            if last_high is None:
                kind = "SH"
            else:
                kind = "HH" if item["price"] > last_high else "LH"
            last_high = item["price"]
        else:
            if last_low is None:
                kind = "SL"
            else:
                kind = "HL" if item["price"] > last_low else "LL"
            last_low = item["price"]
        item["kind"] = kind
        item["visual_label"] = kind
        item["visual_contract"] = "EhukaiMarketStructure"
        item["object_prefix"] = "EMS_"
        classified.append(item)
    return classified


def market_structure(
    symbol: str,
    timeframe: str,
    *,
    bars: int = 300,
    pivot_bars: int = 4,
    max_swings: int = 10,
) -> dict:
    """Return structure context matching EhukaiMarketStructure.mq5 defaults."""
    result = rates_module.fetch(symbol, _tf_label(timeframe), bars)
    if not result.get("ok"):
        return result

    rows = result["data"]
    pivot = _effective_pivot_bars(timeframe, pivot_bars)
    if len(rows) < (pivot * 2 + 5):
        return _fail("MT5_NO_DATA", f"Not enough bars for Ehukai market structure on {symbol} {timeframe}.")

    lookback = min(bars, len(rows) - (pivot * 2) - 1)
    start = max(pivot, len(rows) - lookback)
    stop = len(rows) - pivot
    swings: list[dict] = []

    for i in range(start, stop):
        high = float(rows[i]["high"])
        low = float(rows[i]["low"])
        is_high = True
        is_low = True
        for j in range(i - pivot, i + pivot + 1):
            if j == i:
                continue
            if high <= float(rows[j]["high"]):
                is_high = False
            if low >= float(rows[j]["low"]):
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            swings.append({"time": rows[i]["time"], "price": high, "is_high": True, "side": "high", "index": i})
        if is_low:
            swings.append({"time": rows[i]["time"], "price": low, "is_high": False, "side": "low", "index": i})

    swings = _classify_swings(swings)
    last_high = next((s for s in reversed(swings) if s["is_high"]), None)
    last_low = next((s for s in reversed(swings) if not s["is_high"]), None)
    current_price = float(rows[-1]["close"])

    if last_high and current_price > last_high["price"]:
        bias = "BULLISH BOS"
    elif last_low and current_price < last_low["price"]:
        bias = "BEARISH BOS"
    elif last_high and last_low and last_high["kind"] == "HH" and last_low["kind"] == "HL":
        bias = "BULLISH HH/HL"
    elif last_high and last_low and last_high["kind"] == "LH" and last_low["kind"] == "LL":
        bias = "BEARISH LH/LL"
    else:
        bias = "NEUTRAL / RANGE"

    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "timeframe": _tf_label(timeframe),
            "source": "EhukaiMarketStructure",
            "object_prefix": "EMS_",
            "pivot_bars": pivot,
            "max_swings": max_swings,
            "current_price": current_price,
            "bias": bias,
            "support": last_low["price"] if last_low else None,
            "resistance": last_high["price"] if last_high else None,
            "latest_swing_high": last_high,
            "latest_swing_low": last_low,
            "visible_swings": list(reversed(swings[-max_swings:])),
            "panel_label": _panel_label(_tf_label(timeframe), bias, last_high, last_low),
            "visual_contract": {
                "indicator": "EhukaiMarketStructure",
                "object_prefix": "EMS_",
                "swing_labels": ["SH", "SL", "HH", "HL", "LH", "LL"],
                "panel_pattern": "MS <TF>: <BIAS> | H <kind> <price> | L <kind> <price>",
                "bos_labels": ["BULLISH BOS", "BEARISH BOS"],
                "level_suffixes": ["SUPPORT", "RESISTANCE"],
            },
        },
    }


def _panel_label(timeframe: str, bias: str, last_high: dict | None, last_low: dict | None) -> str:
    hi = f"H {last_high['kind']} {last_high['price']:.3f}" if last_high else "H n/a"
    lo = f"L {last_low['kind']} {last_low['price']:.3f}" if last_low else "L n/a"
    return f"MS {timeframe}: {bias} | {hi} | {lo}"


def fvg(
    symbol: str,
    timeframe: str,
    *,
    bars: int = 100,
    min_gap_pips: float = 1.0,
    max_zones: int = 4,
    max_distance_pips: float = 120.0,
) -> dict:
    """Return FVG context matching EhukaiFVG.mq5 default visible-zone rules."""
    result = indicator.fvg(
        symbol,
        _tf_label(timeframe),
        bars=bars,
        min_points=0.0,
        direction="both",
        state="all",
        mitigation="wick",
        limit=None,
    )
    if not result.get("ok"):
        return result

    zones = []
    for zone in result["data"].get("zones", []):
        if zone.get("state") not in {"open", "partial"}:
            continue
        if float(zone.get("size_pips") or 0) < float(min_gap_pips):
            continue
        if max_distance_pips > 0 and float(zone.get("distance_pips") or 0) > float(max_distance_pips):
            continue
        item = dict(zone)
        item["source"] = "EhukaiFVG"
        item["object_prefix"] = "EFVG_"
        item["visual_contract"] = "EhukaiFVG"
        zones.append(item)
        if len(zones) >= max(1, min(max_zones, 4)):
            break

    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "timeframe": _tf_label(timeframe),
            "source": "EhukaiFVG",
            "object_prefix": "EFVG_",
            "lookback": bars,
            "min_gap_pips": min_gap_pips,
            "max_zones": max(1, min(max_zones, 4)),
            "max_distance_pips": max_distance_pips,
            "current_price": result["data"].get("current_price"),
            "zones": zones,
            "visual_contract": {
                "indicator": "EhukaiFVG",
                "object_prefix": "EFVG_",
                "label_pattern": "BULL/BEAR FVG OPEN/PARTIAL/FILLED <pips>p",
                "geometry": ["rectangle", "upper", "lower", "midline"],
            },
        },
    }


def summarize_contexts(frames: list[dict]) -> dict:
    biases: dict[str, int] = {}
    zone_count = 0
    for frame in frames:
        context = frame.get("structured_context") or {}
        structure = context.get("market_structure") or {}
        bias = structure.get("bias")
        if bias:
            biases[bias] = biases.get(bias, 0) + 1
        fvg_context = context.get("fvg") or {}
        zone_count += len(fvg_context.get("zones") or [])

    dominant_bias = max(biases, key=biases.get) if biases else None
    return {
        "source": "Ehukai visual indicators",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "dominant_bias": dominant_bias,
        "bias_counts": biases,
        "visible_fvg_zone_count": zone_count,
    }
