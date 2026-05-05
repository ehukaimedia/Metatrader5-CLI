"""
ehukai.py - Structured mirrors for the vendored Ehukai MT5 indicators.

These helpers intentionally follow the visual indicator contracts used by:
- EhukaiFVG.mq5
- EhukaiMarketStructure.mq5
- EhukaiLiquiditySwings.mq5

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


def _pip_size(symbol: str, rows: list[dict]) -> float:
    point = indicator._point_for_symbol(symbol, rows)  # noqa: SLF001 - shared CLI/MQ5 visual contract helper
    return indicator._pip_size_for_symbol(symbol, rows, point)  # noqa: SLF001


def _liquidity_id(symbol: str, timeframe: str, side: str, pivot_time: str, price: float) -> str:
    return f"{symbol.upper()}-{_tf_label(timeframe)}-{side}-{pivot_time}-{price:.10g}"


def _pool_status(side: str, top: float, bottom: float, rows: list[dict], start_idx: int) -> tuple[bool, str | None, int | None]:
    for idx, row in enumerate(rows[start_idx + 1:], start=start_idx + 1):
        if side == "buy_side" and float(row["close"]) > top:
            return True, row["time"], idx
        if side == "sell_side" and float(row["close"]) < bottom:
            return True, row["time"], idx
    return False, None, None


def _pool_counts(top: float, bottom: float, rows: list[dict], start_idx: int) -> tuple[int, float]:
    count = 0
    volume = 0.0
    for row in rows[start_idx + 1:]:
        overlaps = float(row["low"]) < top and float(row["high"]) > bottom
        if overlaps:
            count += 1
            volume += float(row.get("tick_volume", row.get("volume", 0)) or 0)
    return count, volume


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


def liquidity(
    symbol: str,
    timeframe: str,
    *,
    bars: int = 300,
    length: int = 14,
    area: str = "wick",
    filter_by: str = "count",
    filter_value: float = 0.0,
    max_pools: int = 10,
) -> dict:
    """Return liquidity swing pools matching EhukaiLiquiditySwings.mq5.

    Swing highs are buy-side liquidity; swing lows are sell-side liquidity.
    Pools are counted when later candles trade back through the pivot zone.
    A pool becomes swept when a later close crosses beyond the pivot extreme.
    """
    area = area.lower().replace("_", "-")
    filter_by = filter_by.lower()
    if area not in {"wick", "full-range"}:
        return _fail("EHUKAI_INVALID_ARGUMENT", "area must be one of: wick, full-range.")
    if filter_by not in {"count", "volume"}:
        return _fail("EHUKAI_INVALID_ARGUMENT", "filter_by must be one of: count, volume.")
    if length < 1:
        return _fail("EHUKAI_INVALID_ARGUMENT", "length must be >= 1.")

    result = rates_module.fetch(symbol, _tf_label(timeframe), bars)
    if not result.get("ok"):
        return result

    rows = result["data"]
    if len(rows) < (length * 2 + 3):
        return _fail("MT5_NO_DATA", f"Not enough bars for Ehukai liquidity swings on {symbol} {timeframe}.")

    pip_size = _pip_size(symbol, rows)
    current_price = float(rows[-1]["close"])
    pools: list[dict] = []
    start = length
    stop = len(rows) - length

    for i in range(start, stop):
        high = float(rows[i]["high"])
        low = float(rows[i]["low"])
        is_high = True
        is_low = True
        for j in range(i - length, i + length + 1):
            if j == i:
                continue
            if high <= float(rows[j]["high"]):
                is_high = False
            if low >= float(rows[j]["low"]):
                is_low = False
            if not is_high and not is_low:
                break

        candidates: list[tuple[str, str, float, float, float]] = []
        if is_high:
            top = high
            bottom = max(float(rows[i]["open"]), float(rows[i]["close"])) if area == "wick" else low
            candidates.append(("buy_side", "BSL", top, bottom, top))
        if is_low:
            top = min(float(rows[i]["open"]), float(rows[i]["close"])) if area == "wick" else high
            bottom = low
            candidates.append(("sell_side", "SSL", top, bottom, bottom))

        for side, short_label, top, bottom, level in candidates:
            count, volume = _pool_counts(top, bottom, rows, i)
            target = count if filter_by == "count" else volume
            if target <= filter_value:
                continue
            swept, swept_at, sweep_idx = _pool_status(side, top, bottom, rows, i)
            status = "swept" if swept else "open"
            distance_pips = 0.0
            if current_price > top:
                distance_pips = (current_price - top) / pip_size
            elif current_price < bottom:
                distance_pips = (bottom - current_price) / pip_size
            visual_label = f"{short_label} LIQ {status.upper()} C{count} V{volume:g}"
            pool = {
                "id": _liquidity_id(symbol, timeframe, side, rows[i]["time"], level),
                "source": "EhukaiLiquiditySwings",
                "type": "liquidity_swing",
                "object_prefix": "ELS_",
                "visual_contract": "EhukaiLiquiditySwings",
                "side": side,
                "short_label": short_label,
                "status": status,
                "pivot_time": rows[i]["time"],
                "swept_at": swept_at,
                "sweep_age_bars": len(rows) - 1 - sweep_idx if sweep_idx is not None else None,
                "level": level,
                "top": top,
                "bottom": bottom,
                "mid": (top + bottom) / 2.0,
                "count": count,
                "volume": volume,
                "filter_target": target,
                "distance_pips": round(distance_pips, 2),
                "age_bars": len(rows) - 1 - i,
                "visual_label": visual_label,
                "boundaries": {
                    "top": {"price": top, "role": "top"},
                    "bottom": {"price": bottom, "role": "bottom"},
                    "level": {"price": level, "role": "liquidity_level"},
                },
                "render": {
                    "kind": "liquidity_zone",
                    "fill": "rgba(239,68,68,0.16)" if side == "buy_side" else "rgba(20,184,166,0.16)",
                    "border": "#ef4444" if side == "buy_side" else "#14b8a6",
                    "level_style": "dashed" if swept else "solid",
                    "label": visual_label,
                    "cli_pair": f"mt5 --json ehukai liquidity SYMBOL {_tf_label(timeframe)}",
                },
            }
            pools.append(pool)

    pools.sort(key=lambda item: item["pivot_time"], reverse=True)
    visible = pools[:max(1, int(max_pools))]
    open_pools = [pool for pool in visible if pool["status"] == "open"]
    swept_pools = [pool for pool in visible if pool["status"] == "swept"]
    open_by_distance = sorted(open_pools, key=lambda pool: pool["distance_pips"])
    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "timeframe": _tf_label(timeframe),
            "source": "EhukaiLiquiditySwings",
            "object_prefix": "ELS_",
            "length": length,
            "area": area,
            "filter_by": filter_by,
            "filter_value": filter_value,
            "current_price": current_price,
            "pools": visible,
            "open_pools": open_pools,
            "swept_pools": swept_pools,
            "nearest_buy_side": next((p for p in open_by_distance if p["side"] == "buy_side"), None),
            "nearest_sell_side": next((p for p in open_by_distance if p["side"] == "sell_side"), None),
            "visual_contract": {
                "indicator": "EhukaiLiquiditySwings",
                "object_prefix": "ELS_",
                "label_pattern": "BSL/SSL LIQ OPEN/SWEPT C<count> V<volume>",
                "sides": {"buy_side": "liquidity above swing highs", "sell_side": "liquidity below swing lows"},
                "geometry": ["rectangle", "liquidity level", "count/volume label"],
            },
        },
    }


def summarize_contexts(frames: list[dict]) -> dict:
    biases: dict[str, int] = {}
    zone_count = 0
    open_liquidity_count = 0
    swept_liquidity_count = 0
    for frame in frames:
        context = frame.get("structured_context") or {}
        structure = context.get("market_structure") or {}
        bias = structure.get("bias")
        if bias:
            biases[bias] = biases.get(bias, 0) + 1
        fvg_context = context.get("fvg") or {}
        zone_count += len(fvg_context.get("zones") or [])
        liquidity_context = context.get("liquidity") or {}
        open_liquidity_count += len(liquidity_context.get("open_pools") or [])
        swept_liquidity_count += len(liquidity_context.get("swept_pools") or [])

    dominant_bias = max(biases, key=biases.get) if biases else None
    return {
        "source": "Ehukai visual indicators",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "dominant_bias": dominant_bias,
        "bias_counts": biases,
        "visible_fvg_zone_count": zone_count,
        "open_liquidity_pool_count": open_liquidity_count,
        "swept_liquidity_pool_count": swept_liquidity_count,
    }
