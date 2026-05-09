"""
ehukai.py - Structured mirrors for the vendored Ehukai MT5 indicators.

These helpers intentionally follow the visual indicator contracts used by:
- EhukaiFVG.mq5
- EhukaiMarketStructure.mq5
- EhukaiLiquiditySwings.mq5
- EhukaiVolumeProfilePOC.mq5

They are used by visual TDA so agents see one coherent Ehukai interpretation
instead of competing generic analysis labels.
"""
from __future__ import annotations

from datetime import datetime, timezone

from metatrader5_cli.mt5.core import indicator, rates as rates_module

STRUCTURE_ENGINE_VERSION = "elite-v1"


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _tf_label(timeframe: str) -> str:
    value = timeframe.upper()
    return "MN1" if value == "MN" else value


def _effective_pivot_bars(timeframe: str, pivot_bars: int = 8) -> int:
    return max(1, int(pivot_bars))


def _pip_size(symbol: str, rows: list[dict]) -> float:
    point = indicator._point_for_symbol(symbol, rows)  # noqa: SLF001 - shared CLI/MQ5 visual contract helper
    return indicator._pip_size_for_symbol(symbol, rows, point)  # noqa: SLF001


def _liquidity_id(symbol: str, timeframe: str, side: str, pivot_time: str, price: float) -> str:
    return f"{symbol.upper()}-{_tf_label(timeframe)}-{side}-{pivot_time}-{price:.10g}"


def _pool_status(
    side: str,
    top: float,
    bottom: float,
    rows: list[dict],
    start_idx: int,
    *,
    min_penetration: float = 0.0,
) -> tuple[str, str | None, int | None]:
    """Classify pool state with a wick-through/reclaim sweep contract.

    A close beyond a pool is a break, not a liquidity grab. A valid sweep
    probes beyond the pool boundary and closes back through the midpoint.
    """
    mid = (top + bottom) / 2.0
    for idx, row in enumerate(rows[start_idx + 1:], start=start_idx + 1):
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        if side == "buy_side":
            if high > top + min_penetration and close < mid:
                return "swept", row["time"], idx
            if close > top:
                return "broken", row["time"], idx
        else:
            if low < bottom - min_penetration and close > mid:
                return "swept", row["time"], idx
            if close < bottom:
                return "broken", row["time"], idx
    return "open", None, None


def _pool_counts(top: float, bottom: float, rows: list[dict], start_idx: int) -> tuple[int, float]:
    count = 0
    volume = 0.0
    for row in rows[start_idx + 1:]:
        overlaps = float(row["low"]) < top and float(row["high"]) > bottom
        if overlaps:
            count += 1
            volume += float(row.get("tick_volume", row.get("volume", 0)) or 0)
    return count, volume


def _true_range(row: dict, prev_close: float | None) -> float:
    high = float(row["high"])
    low = float(row["low"])
    if prev_close is None:
        return high - low
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr_at(rows: list[dict], index: int, period: int = 14) -> float:
    start = max(0, index - max(1, period) + 1)
    values = []
    for i in range(start, index + 1):
        prev = float(rows[i - 1]["close"]) if i > 0 else None
        values.append(_true_range(rows[i], prev))
    return sum(values) / len(values) if values else 0.0


def _pool_zone_from_level(rows: list[dict], index: int, level: float, point: float, *, half_atr: float) -> tuple[float, float, float]:
    atr = _atr_at(rows, index)
    half = max(atr * half_atr, point * 5.0)
    return level + half, level - half, half


def _clamp_index(value: int, upper: int) -> int:
    return max(0, min(upper, value))


def _profile_value_area(volumes: list[float], poc_index: int, value_area_pct: float) -> tuple[int, int, float]:
    total = sum(volumes)
    if not volumes or total <= 0:
        return poc_index, poc_index, 0.0
    target = total * max(0.0, min(100.0, value_area_pct)) / 100.0
    low_idx = high_idx = poc_index
    covered = volumes[poc_index]
    while covered < target and (low_idx > 0 or high_idx < len(volumes) - 1):
        above = volumes[high_idx + 1] if high_idx < len(volumes) - 1 else -1.0
        below = volumes[low_idx - 1] if low_idx > 0 else -1.0
        if above >= below:
            high_idx += 1
            covered += max(0.0, above)
        else:
            low_idx -= 1
            covered += max(0.0, below)
    return low_idx, high_idx, covered


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


def _detect_pivots(
    rows: list[dict],
    *,
    pivot: int,
    start: int,
    stop: int,
) -> list[dict]:
    swings: list[dict] = []
    for i in range(max(pivot, start), min(stop, len(rows) - pivot)):
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
    return _classify_swings(swings)


def _signal_index(rows: list[dict], pivot: int) -> int:
    """Use the last closed bar for structure decisions.

    MT5 and TradingView both draw a forming candle that can reverse before close.
    TDA should not call a BOS/CHOCH from that candle, so the canonical engine
    uses rows[-2] whenever possible and reserves rows[-1] for current price.
    """
    return max(pivot, len(rows) - 2)


def _stage_from_bias(bias: str) -> str:
    text = bias.upper()
    if "CHOCH" in text:
        return "CHOCH"
    if "BOS" in text:
        return "BOS"
    if "HH/HL" in text:
        return "HH_HL"
    if "LH/LL" in text:
        return "LH_LL"
    return "RANGE"


def _direction_from_bias(bias: str) -> str:
    text = bias.upper()
    if "BULLISH" in text:
        return "bullish"
    if "BEARISH" in text:
        return "bearish"
    return "neutral"


def _structure_bias(
    *,
    signal_close: float,
    last_high: dict | None,
    last_low: dict | None,
    buffer: float,
) -> tuple[str, dict | None]:
    """Return the close-confirmed swing state and latest event.

    CHOCH is only emitted when a closed break violates the opposite established
    swing sequence. BOS is continuation. HH/HL and LH/LL are directional
    structure reads while price remains inside the dealing range.
    """
    have_high = last_high is not None
    have_low = last_low is not None

    if have_high and signal_close > float(last_high["price"]) + buffer:
        prior_bearish = have_low and last_high.get("kind") == "LH" and last_low.get("kind") == "LL"
        label = "BULLISH CHOCH" if prior_bearish else "BULLISH BOS"
        return label, {"type": "CHOCH" if prior_bearish else "BOS", "direction": "bullish", "level": last_high}

    if have_low and signal_close < float(last_low["price"]) - buffer:
        prior_bullish = have_high and last_high.get("kind") == "HH" and last_low.get("kind") == "HL"
        label = "BEARISH CHOCH" if prior_bullish else "BEARISH BOS"
        return label, {"type": "CHOCH" if prior_bullish else "BOS", "direction": "bearish", "level": last_low}

    if have_high and have_low and last_high.get("kind") == "HH" and last_low.get("kind") == "HL":
        return "BULLISH HH/HL", None

    if have_high and have_low and last_high.get("kind") == "LH" and last_low.get("kind") == "LL":
        return "BEARISH LH/LL", None

    return "NEUTRAL / RANGE", None


def _internal_structure(
    rows: list[dict],
    *,
    signal_index: int,
    internal_pivot_bars: int,
    lookback: int,
    signal_close: float,
    buffer: float,
) -> dict:
    """Compact internal read inspired by the elite market-structure video.

    Internal structure is its own pivot sequence. It is not a slice of the
    slower swing pivots; MQL5 uses a separate internal pivot length, and the
    Python mirror does the same so chart and JSON can agree on iBOS/CHOCH.
    """
    pivot = max(1, int(internal_pivot_bars))
    start = max(pivot, signal_index - max(20, int(lookback)))
    stop = signal_index - pivot + 1
    internal_swings = _detect_pivots(rows, pivot=pivot, start=start, stop=stop)
    highs = [s for s in internal_swings if s["is_high"]]
    lows = [s for s in internal_swings if not s["is_high"]]
    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    bias, event = _structure_bias(
        signal_close=signal_close,
        last_high=last_high,
        last_low=last_low,
        buffer=buffer,
    )
    direction = _direction_from_bias(bias)
    stage = _stage_from_bias(bias)

    weak_side = None
    strong_side = None
    weak_level = None
    strong_level = None
    if direction == "bullish":
        weak_side = "high"
        strong_side = "low"
        weak_level = last_high
        strong_level = last_low
    elif direction == "bearish":
        weak_side = "low"
        strong_side = "high"
        weak_level = last_low
        strong_level = last_high

    return {
        "bias": bias.replace("BULLISH", "Bullish").replace("BEARISH", "Bearish").replace("NEUTRAL", "Neutral"),
        "direction": direction,
        "stage": "i" + stage if stage in {"BOS", "CHOCH"} else stage,
        "last_event": {**event, "type": "i" + event["type"]} if event else None,
        "pivot_bars": pivot,
        "swings": internal_swings[-8:],
        "dealing_high": last_high,
        "dealing_low": last_low,
        "weak_side": weak_side,
        "weak_level": weak_level,
        "strong_side": strong_side,
        "strong_level": strong_level,
        "early_signal": stage == "CHOCH" and event is not None,
    }


def market_structure(
    symbol: str,
    timeframe: str,
    *,
    bars: int = 300,
    pivot_bars: int = 8,
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

    lookback = min(bars, len(rows))
    start = max(pivot, len(rows) - lookback)
    stop = len(rows) - pivot
    swings = _detect_pivots(rows, pivot=pivot, start=start, stop=stop)
    signal = _signal_index(rows, pivot)
    signal_time = rows[signal]["time"]
    signal_close = float(rows[signal]["close"])
    decision_swings = [s for s in swings if int(s["index"]) <= signal - pivot]
    last_high = next((s for s in reversed(decision_swings) if s["is_high"]), None)
    last_low = next((s for s in reversed(decision_swings) if not s["is_high"]), None)
    current_price = float(rows[-1]["close"])
    buffer = _pip_size(symbol, rows) * 0.2
    bias, event = _structure_bias(
        signal_close=signal_close,
        last_high=last_high,
        last_low=last_low,
        buffer=buffer,
    )
    direction = _direction_from_bias(bias)
    stage = _stage_from_bias(bias)
    swing_highs = [s for s in swings if s["is_high"]]
    swing_lows = [s for s in swings if not s["is_high"]]
    internal = _internal_structure(
        rows,
        signal_index=signal,
        internal_pivot_bars=3,
        lookback=lookback,
        signal_close=signal_close,
        buffer=buffer,
    )

    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "timeframe": _tf_label(timeframe),
            "source": "EhukaiMarketStructure",
            "structure_engine_version": STRUCTURE_ENGINE_VERSION,
            "object_prefix": "EMS_",
            "pivot_bars": pivot,
            "max_swings": max_swings,
            "current_price": current_price,
            "signal_bar": {"index": signal, "time": signal_time, "close": signal_close},
            "bias": bias,
            "direction": direction,
            "stage": stage,
            "last_event": event,
            "support": last_low["price"] if last_low else None,
            "resistance": last_high["price"] if last_high else None,
            "latest_swing_high": last_high,
            "latest_swing_low": last_low,
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "visible_swings": list(reversed(swings[-max_swings:])),
            "swing": {
                "bias": bias,
                "direction": direction,
                "stage": stage,
                "last_event": event,
                "support": last_low["price"] if last_low else None,
                "resistance": last_high["price"] if last_high else None,
                "dealing_high": last_high,
                "dealing_low": last_low,
            },
            "internal": internal,
            "trade_read": _trade_read(direction, stage, internal),
            "panel_label": _panel_label(_tf_label(timeframe), bias, last_high, last_low),
            "visual_contract": {
                "indicator": "EhukaiMarketStructure",
                "object_prefix": "EMS_",
                "swing_labels": ["SH", "SL", "HH", "HL", "LH", "LL"],
                "panel_pattern": "MS <TF>: <BIAS> | H <kind> <price> | L <kind> <price>",
                "event_labels": ["BULLISH BOS", "BEARISH BOS", "BULLISH CHOCH", "BEARISH CHOCH", "iBOS"],
                "level_suffixes": ["SUPPORT", "RESISTANCE"],
                "decision_bar": "last_closed_bar",
                "default_lengths": {"swing": 8, "internal": 3, "fractal": 1},
            },
        },
    }


def _trade_read(direction: str, stage: str, internal: dict) -> dict:
    internal_direction = internal.get("direction")
    if direction == "neutral":
        return {
            "direction_permission": "none",
            "quality": "no_trade",
            "summary": "No swing permission yet; wait for a close-confirmed BOS or CHOCH.",
        }

    if internal_direction == direction and internal.get("stage") in {"iBOS", "HH_HL", "LH_LL"}:
        return {
            "direction_permission": "buy" if direction == "bullish" else "sell",
            "quality": "aligned",
            "summary": "Swing and internal structure are aligned; use FVG/POI retest for entry timing.",
        }

    if stage == "CHOCH" or internal.get("early_signal"):
        return {
            "direction_permission": "watch",
            "quality": "pullback_or_transition",
            "summary": "Structure is transitioning; wait for internal BOS confirmation before treating it as a trade.",
        }

    return {
        "direction_permission": "watch",
        "quality": "pullback",
        "summary": "Swing bias exists, but internal structure is not aligned yet.",
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
    pool_half_atr: float = 0.40,
    min_pen_atr: float = 0.0,
) -> dict:
    """Return liquidity swing pools matching EhukaiLiquiditySwings.mq5.

    Swing highs are buy-side liquidity; swing lows are sell-side liquidity.
    Pools are counted when later candles trade back through the pivot zone.
    A pool is swept only when price wicks through and closes back through the
    pool midpoint. Close-throughs are marked broken instead of swept.
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
    point = indicator._point_for_symbol(symbol, rows)  # noqa: SLF001 - shared visual contract helper
    current_price = float(rows[-1]["close"])
    pools: list[dict] = []
    broken_pools: list[dict] = []
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

        candidates: list[tuple[str, str, float, float, float, float]] = []
        if is_high:
            level = high
            if area == "wick":
                top, bottom, half_width = _pool_zone_from_level(rows, i, level, point, half_atr=pool_half_atr)
            else:
                top = high
                bottom = low
                half_width = (top - bottom) / 2.0
            candidates.append(("buy_side", "BSL", top, bottom, level, half_width))
        if is_low:
            level = low
            if area == "wick":
                top, bottom, half_width = _pool_zone_from_level(rows, i, level, point, half_atr=pool_half_atr)
            else:
                top = high
                bottom = low
                half_width = (top - bottom) / 2.0
            candidates.append(("sell_side", "SSL", top, bottom, level, half_width))

        for side, short_label, top, bottom, level, half_width in candidates:
            count, volume = _pool_counts(top, bottom, rows, i)
            target = count if filter_by == "count" else volume
            if target <= filter_value:
                continue
            min_penetration = _atr_at(rows, i) * max(0.0, float(min_pen_atr))
            status, swept_at, sweep_idx = _pool_status(
                side,
                top,
                bottom,
                rows,
                i,
                min_penetration=min_penetration,
            )
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
                "zone_width_pips": round((top - bottom) / pip_size, 2),
                "sweep_model": "wick_reclaim",
                "pool_half_atr": pool_half_atr,
                "min_pen_atr": min_pen_atr,
                "source_kind": "swing_pivot",
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
                    "level_style": "dashed" if status == "swept" else "solid",
                    "label": visual_label,
                    "cli_pair": f"mt5 --json ehukai liquidity SYMBOL {_tf_label(timeframe)}",
                },
            }
            if status == "broken":
                broken_pools.append(pool)
            else:
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
            "pool_half_atr": pool_half_atr,
            "min_pen_atr": min_pen_atr,
            "sweep_model": "wick_reclaim",
            "current_price": current_price,
            "pools": visible,
            "open_pools": open_pools,
            "swept_pools": swept_pools,
            "broken_pools": broken_pools[:max(1, int(max_pools))],
            "nearest_buy_side": next((p for p in open_by_distance if p["side"] == "buy_side"), None),
            "nearest_sell_side": next((p for p in open_by_distance if p["side"] == "sell_side"), None),
            "visual_contract": {
                "indicator": "EhukaiLiquiditySwings",
                "object_prefix": "ELS_",
                "label_pattern": "BSL/SSL LIQ OPEN/SWEPT C<count> V<volume>",
                "sides": {"buy_side": "liquidity above swing highs", "sell_side": "liquidity below swing lows"},
                "geometry": ["ATR-width rectangle", "liquidity level", "count/volume label"],
                "sweep_rule": "wick beyond pool boundary, close back through midpoint",
            },
        },
    }


def volume_profile(
    symbol: str,
    timeframe: str,
    *,
    bars: int = 120,
    rows: int = 48,
    value_area_pct: float = 70.0,
) -> dict:
    """Return an EhukaiVolumeProfilePOC-compatible fixed lookback profile.

    The profile uses tick volume for forex/CFD symbols and distributes each
    bar's volume across the price rows touched by that bar. This mirrors the
    TradingView concept at a lightweight MT5-compatible resolution: POC,
    VAH/VAL, profile high/low, and high-volume rows for reactive S/R context.
    """
    if bars < 10:
        return _fail("EHUKAI_INVALID_ARGUMENT", "bars must be >= 10.")
    if rows < 8:
        return _fail("EHUKAI_INVALID_ARGUMENT", "rows must be >= 8.")
    if not 1.0 <= value_area_pct <= 100.0:
        return _fail("EHUKAI_INVALID_ARGUMENT", "value_area_pct must be between 1 and 100.")

    result = rates_module.fetch(symbol, _tf_label(timeframe), bars)
    if not result.get("ok"):
        return result

    fetched_rows = result["data"]
    if len(fetched_rows) < 11:
        return _fail("MT5_NO_DATA", f"Not enough bars for Ehukai volume profile on {symbol} {timeframe}.")
    raw_rows = fetched_rows[:-1]
    if len(raw_rows) < 10:
        return _fail("MT5_NO_DATA", f"Not enough closed bars for Ehukai volume profile on {symbol} {timeframe}.")

    profile_high = max(float(row["high"]) for row in raw_rows)
    profile_low = min(float(row["low"]) for row in raw_rows)
    if profile_high <= profile_low:
        return _fail("MT5_NO_DATA", "Volume profile range is flat.")

    row_count = max(8, int(rows))
    step = (profile_high - profile_low) / row_count
    total_volume = [0.0 for _ in range(row_count)]
    up_volume = [0.0 for _ in range(row_count)]
    down_volume = [0.0 for _ in range(row_count)]

    for bar in raw_rows:
        high = float(bar["high"])
        low = float(bar["low"])
        open_price = float(bar["open"])
        close = float(bar["close"])
        volume = float(bar.get("tick_volume", bar.get("volume", 0)) or 0.0)
        if volume <= 0:
            continue
        first = _clamp_index(int((low - profile_low) / step), row_count - 1)
        last = _clamp_index(int((high - profile_low) / step), row_count - 1)
        if last < first:
            first, last = last, first
        touched = max(1, last - first + 1)
        share = volume / touched
        for idx in range(first, last + 1):
            total_volume[idx] += share
            if close >= open_price:
                up_volume[idx] += share
            else:
                down_volume[idx] += share

    total = sum(total_volume)
    if total <= 0:
        return _fail("MT5_NO_DATA", "No tick volume available for volume profile.")

    poc_index = max(range(row_count), key=lambda idx: total_volume[idx])
    va_low_idx, va_high_idx, va_volume = _profile_value_area(total_volume, poc_index, value_area_pct)
    poc = profile_low + (poc_index + 0.5) * step
    vah = profile_low + (va_high_idx + 1) * step
    val = profile_low + va_low_idx * step
    current_price = float(raw_rows[-1]["close"])
    pip_size = _pip_size(symbol, raw_rows)
    max_volume = max(total_volume)

    profile_rows = []
    for idx, volume in enumerate(total_volume):
        lower = profile_low + idx * step
        upper = lower + step
        profile_rows.append({
            "index": idx,
            "lower": lower,
            "upper": upper,
            "mid": (lower + upper) / 2.0,
            "volume": round(volume, 4),
            "up_volume": round(up_volume[idx], 4),
            "down_volume": round(down_volume[idx], 4),
            "volume_pct_of_poc": round((volume / max_volume) * 100.0, 2) if max_volume else 0.0,
            "in_value_area": va_low_idx <= idx <= va_high_idx,
            "is_poc": idx == poc_index,
        })

    if current_price > vah:
        price_context = "above_value_area"
    elif current_price < val:
        price_context = "below_value_area"
    else:
        price_context = "inside_value_area"

    poc_distance_pips = abs(current_price - poc) / pip_size if pip_size else 0.0
    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "timeframe": _tf_label(timeframe),
            "source": "EhukaiVolumeProfilePOC",
            "object_prefix": "EVP_",
            "bars": len(raw_rows),
            "rows": row_count,
            "value_area_pct": value_area_pct,
            "profile_high": profile_high,
            "profile_low": profile_low,
            "poc": poc,
            "point_of_control": poc,
            "value_area_high": vah,
            "value_area_low": val,
            "value_area_volume": round(va_volume, 4),
            "total_volume": round(total, 4),
            "current_price": current_price,
            "price_context": price_context,
            "poc_distance_pips": round(poc_distance_pips, 2),
            "rows_detail": profile_rows,
            "high_volume_nodes": sorted(profile_rows, key=lambda row: row["volume"], reverse=True)[:5],
            "visual_label": f"VP POC {poc:.5f} | VA {val:.5f}-{vah:.5f}",
            "visual_contract": {
                "indicator": "EhukaiVolumeProfilePOC",
                "object_prefix": "EVP_",
                "label_pattern": "VP POC <price> | VA <val>-<vah>",
                "levels": ["POC", "VAH", "VAL", "Profile High", "Profile Low"],
                "geometry": ["right-side histogram", "POC line", "VAH/VAL lines"],
                "volume_source": "tick volume for forex/CFD symbols",
                "calculation_note": "bar volume distributed equally across touched price rows",
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
