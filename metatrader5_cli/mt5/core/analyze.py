"""
analyze.py — Top-down multi-timeframe analysis and price structure for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  MT5 access stays behind core
modules such as rates, market, and the structured Ehukai mirrors.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from metatrader5_cli.mt5.core import ehukai, market, order as order_module, rates as rates_module


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


# ---------------------------------------------------------------------------
# structure — N-bar pivot detection (spec §6.5)
# ---------------------------------------------------------------------------

def structure(symbol: str, timeframe: str, bars: int = 200, pivot_n: int = 5) -> dict:
    """Return swing highs/lows, support, and resistance via N-bar pivot detection.

    A bar at index i is a swing high if its high is the highest of the pivot_n
    bars before AND after it; swing low symmetrically.  support = highest
    swing low below current price; resistance = lowest swing high above it.
    """
    result = rates_module.fetch(symbol, timeframe, bars)
    if not result["ok"]:
        return result

    df = pd.DataFrame(result["data"])
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    times = df["time"].tolist()
    n = len(df)

    swing_highs = []
    swing_lows = []
    swing_points = []

    for i in range(pivot_n, n - pivot_n):
        window_h = highs[i - pivot_n:i] + highs[i + 1:i + pivot_n + 1]
        if highs[i] > max(window_h):
            point = {"time": times[i], "price": highs[i]}
            swing_highs.append(point)
            swing_points.append({**point, "side": "high"})

        window_l = lows[i - pivot_n:i] + lows[i + 1:i + pivot_n + 1]
        if lows[i] < min(window_l):
            point = {"time": times[i], "price": lows[i]}
            swing_lows.append(point)
            swing_points.append({**point, "side": "low"})

    current_price = float(df["close"].iloc[-1])
    last_high = None
    last_low = None
    for point in swing_points:
        if point["side"] == "high":
            if last_high is None:
                kind = "SH"
            else:
                kind = "HH" if point["price"] > last_high else "LH"
            last_high = point["price"]
        else:
            if last_low is None:
                kind = "SL"
            else:
                kind = "HL" if point["price"] > last_low else "LL"
            last_low = point["price"]
        point["kind"] = kind
        point["visual_label"] = kind
        point["visual_contract"] = "EhukaiMarketStructure"
        point["object_prefix"] = "EMS_"

    resistance_candidates = [s["price"] for s in swing_highs if s["price"] > current_price]
    support_candidates = [s["price"] for s in swing_lows if s["price"] < current_price]

    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "timeframe": timeframe,
            "pivot_n": pivot_n,
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "swing_points": swing_points,
            "latest_swing_high": next((p for p in reversed(swing_points) if p["side"] == "high"), None),
            "latest_swing_low": next((p for p in reversed(swing_points) if p["side"] == "low"), None),
            "support": max(support_candidates) if support_candidates else None,
            "resistance": min(resistance_candidates) if resistance_candidates else None,
            "current_price": current_price,
            "visual_contract": {
                "indicator": "EhukaiMarketStructure",
                "object_prefix": "EMS_",
                "swing_labels": ["SH", "SL", "HH", "HL", "LH", "LL"],
                "level_suffixes": ["SUPPORT", "RESISTANCE"],
            },
        },
    }


# ---------------------------------------------------------------------------
# _classify_tf — single-timeframe market-structure classification
# ---------------------------------------------------------------------------

def _classify_tf(symbol: str, timeframe: str, bars: int) -> dict | None:
    """Return canonical Ehukai/elite TF structure or None on any data error."""
    result = ehukai.market_structure(symbol, timeframe, bars=bars)
    if not result["ok"]:
        return None
    data = result["data"]
    trend = data.get("direction") or "neutral"
    structure_state = data.get("stage") or "RANGE"
    if structure_state == "RANGE":
        structure_state = "range"

    return {
        "timeframe": timeframe,
        "trend": trend,
        "structure": structure_state,
        "current_price": data["current_price"],
        "support": data["support"],
        "resistance": data["resistance"],
        "swing_highs": data.get("swing_highs", []),
        "swing_lows": data.get("swing_lows", []),
        "bias": data.get("bias"),
        "signal_bar": data.get("signal_bar"),
        "last_event": data.get("last_event"),
        "internal": data.get("internal"),
        "trade_read": data.get("trade_read"),
        "structure_engine_version": data.get("structure_engine_version"),
    }


# ---------------------------------------------------------------------------
# topdown
# ---------------------------------------------------------------------------

def topdown(symbol: str, timeframes: list[str], bars: int = 200) -> dict:
    """Multi-timeframe market-structure summary (spec §6.5).

    For each TF: detect swing highs/lows and classify HH/HL or LH/LL structure.
    Aggregates bias from majority across TFs. confluence_score = fraction
    of TFs agreeing with the majority bias.
    """
    tf_dict: dict[str, dict] = {}
    for tf in timeframes:
        classified = _classify_tf(symbol, tf, bars)
        if classified is not None:
            tf_dict[tf] = {k: v for k, v in classified.items() if k != "timeframe"}

    if not tf_dict:
        return _fail("MT5_NO_DATA", f"Could not compute market structure for any timeframe for {symbol!r}.")

    counts: dict[str, int] = {"bullish": 0, "bearish": 0, "neutral": 0}
    for r in tf_dict.values():
        counts[r["trend"]] += 1

    bias = max(counts, key=lambda k: counts[k])
    confluence_score = counts[bias] / len(tf_dict)

    notes = []
    for tf, r in tf_dict.items():
        notes.append(
            f"{tf}: {r['trend']} structure ({r['structure']}); "
            f"support={r['support']}, resistance={r['resistance']}; "
            f"{((r.get('trade_read') or {}).get('summary') or 'No trade read.')}"
        )

    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "bias": bias,
            "confluence_score": confluence_score,
            "timeframes": tf_dict,
            "notes": notes,
        },
    }


# ---------------------------------------------------------------------------
# bias
# ---------------------------------------------------------------------------

_DEFAULT_TIMEFRAMES = ["D1", "H4", "H1"]
_SNIPER_TIMEFRAMES = ["D1", "H4", "M15", "M5", "M1"]
_FX_ROLLOVER_HOURS_UTC = {21, 22}


def bias(symbol: str) -> dict:
    """Quick directional bias using default TFs D1, H4, H1 (spec §6.5)."""
    result = topdown(symbol, _DEFAULT_TIMEFRAMES)
    if not result["ok"]:
        return result
    data = result["data"]
    return {
        "ok": True,
        "data": {
            "symbol": symbol,
            "bias": data["bias"],
            "confidence": data["confluence_score"],
            "reasoning": "\n".join(data["notes"]),
        },
    }


# ---------------------------------------------------------------------------
# sniper_poc
# ---------------------------------------------------------------------------

def _side_from_bias(bias_value: str | None) -> str | None:
    text = (bias_value or "").upper()
    if "BULLISH" in text:
        return "buy"
    if "BEARISH" in text:
        return "sell"
    return None


def _pip_size_from_info(info_data: dict) -> float:
    pip_size = info_data.get("pip_size")
    if isinstance(pip_size, (int, float)) and pip_size:
        return float(pip_size)
    digits = int(info_data.get("digits", 5) or 5)
    return 10 ** (1 - digits)


def _round_price(price: float, digits: int) -> float:
    return round(float(price), max(0, int(digits)))


def _gate(name: str, ok: bool, detail: str, severity: str = "blocker") -> dict:
    return {"name": name, "ok": bool(ok), "severity": severity, "detail": detail}


def _sniper_liquidity_length(timeframe: str) -> int:
    return 5 if timeframe.upper() in {"M1", "M5"} else 14


def _frame(symbol: str, timeframe: str, bars: int) -> dict:
    frame = {"timeframe": timeframe}
    structure = ehukai.market_structure(symbol, timeframe, bars=bars)
    fvg = ehukai.fvg(symbol, timeframe, bars=min(bars, 100), max_zones=4)
    liquidity = ehukai.liquidity(
        symbol,
        timeframe,
        bars=bars,
        length=_sniper_liquidity_length(timeframe),
        max_pools=10,
    )
    frame["market_structure"] = structure["data"] if structure.get("ok") else None
    frame["fvg"] = fvg["data"] if fvg.get("ok") else None
    frame["liquidity"] = liquidity["data"] if liquidity.get("ok") else None
    frame["errors"] = {
        "market_structure": structure.get("error") if not structure.get("ok") else None,
        "fvg": fvg.get("error") if not fvg.get("ok") else None,
        "liquidity": liquidity.get("error") if not liquidity.get("ok") else None,
    }
    return frame


def _is_fx_symbol(symbol: str) -> bool:
    text = "".join(ch for ch in symbol.upper() if ch.isalpha())
    return len(text) >= 6 and text[:3].isalpha() and text[3:6].isalpha()


def _matching_zones(
    frames: dict[str, dict],
    direction: str,
    quote_price: float,
    *,
    pip_size: float,
    max_age_bars: int,
    max_entry_distance_pips: float,
    include_partial: bool,
) -> list[dict]:
    wanted = "bullish" if direction == "buy" else "bearish"
    zones: list[dict] = []
    for tf in ("M1", "M5", "M15"):
        fvg_data = (frames.get(tf) or {}).get("fvg") or {}
        for zone in fvg_data.get("zones") or []:
            if zone.get("direction") != wanted:
                continue
            mid = zone.get("mid")
            if not isinstance(mid, (int, float)):
                continue
            state = str(zone.get("state") or "").lower()
            if state != "open" and not (include_partial and state == "partial"):
                continue
            age_bars = zone.get("age_bars")
            if isinstance(age_bars, (int, float)) and max_age_bars >= 0 and int(age_bars) > max_age_bars:
                continue
            if direction == "buy" and float(mid) >= quote_price:
                continue
            if direction == "sell" and float(mid) <= quote_price:
                continue
            distance_pips = abs(quote_price - float(mid)) / pip_size if pip_size else 0.0
            if max_entry_distance_pips >= 0 and distance_pips > max_entry_distance_pips:
                continue
            item = dict(zone)
            item["timeframe"] = tf
            item["entry_price"] = float(mid)
            item["entry_role"] = "fvg_mid"
            item["distance_to_quote"] = abs(quote_price - float(mid))
            item["distance_to_quote_pips"] = round(distance_pips, 2)
            zones.append(item)
    return sorted(zones, key=lambda z: ({"M1": 0, "M5": 1, "M15": 2}.get(z["timeframe"], 9), z["distance_to_quote"]))


def _pools(
    frames: dict[str, dict],
    *,
    side: str,
    status: str | None = None,
    max_sweep_age_bars: int | None = None,
) -> list[dict]:
    pools: list[dict] = []
    for tf in ("M1", "M5", "M15"):
        liquidity = (frames.get(tf) or {}).get("liquidity") or {}
        for pool in liquidity.get("pools") or []:
            if pool.get("side") != side:
                continue
            if status and pool.get("status") != status:
                continue
            if status == "swept" and max_sweep_age_bars is not None and max_sweep_age_bars >= 0:
                age_bars = pool.get("sweep_age_bars", pool.get("age_bars"))
                if not isinstance(age_bars, (int, float)) or int(age_bars) > max_sweep_age_bars:
                    continue
            item = dict(pool)
            item["timeframe"] = tf
            pools.append(item)
    return pools


def _target_candidates(pools: list[dict], structures: list[dict], direction: str, entry: float) -> list[dict]:
    candidates = []
    if direction == "buy":
        for pool in pools:
            level = pool.get("level")
            if isinstance(level, (int, float)) and float(level) > entry:
                candidates.append({"source": "liquidity", "timeframe": pool.get("timeframe"), "price": float(level), "label": pool.get("visual_label")})
        for structure_data in structures:
            resistance = structure_data.get("resistance")
            if isinstance(resistance, (int, float)) and float(resistance) > entry:
                candidates.append({"source": "structure", "timeframe": structure_data.get("timeframe"), "price": float(resistance), "label": "resistance"})
        return sorted(candidates, key=lambda c: c["price"] - entry)

    for pool in pools:
        level = pool.get("level")
        if isinstance(level, (int, float)) and float(level) < entry:
            candidates.append({"source": "liquidity", "timeframe": pool.get("timeframe"), "price": float(level), "label": pool.get("visual_label")})
    for structure_data in structures:
        support = structure_data.get("support")
        if isinstance(support, (int, float)) and float(support) < entry:
            candidates.append({"source": "structure", "timeframe": structure_data.get("timeframe"), "price": float(support), "label": "support"})
    return sorted(candidates, key=lambda c: entry - c["price"])


def _structure_side(structure_data: dict | None) -> str | None:
    if not structure_data:
        return None
    return _side_from_bias(structure_data.get("bias")) or _side_from_bias(structure_data.get("direction"))


def _structure_stage(structure_data: dict | None) -> str:
    if not structure_data:
        return "range"
    return str(structure_data.get("stage") or structure_data.get("structure") or "range")


def _last_event(structure_data: dict | None) -> dict | None:
    if not structure_data:
        return None
    event = structure_data.get("last_event")
    return event if isinstance(event, dict) else None


def _structure_contract(frames: dict[str, dict], direction: str) -> dict:
    setup_tf = (frames.get("M15") or {}).get("market_structure") or {}
    entry_tf = (frames.get("M5") or {}).get("market_structure") or {}
    internal = setup_tf.get("internal") if isinstance(setup_tf.get("internal"), dict) else {}
    strong_level = internal.get("strong_level") or setup_tf.get("strong_level")
    weak_target = internal.get("weak_level") or setup_tf.get("weak_target")
    permission_sides = {
        tf: _structure_side((frames.get(tf) or {}).get("market_structure"))
        for tf in ("D1", "H4", "M15", "M5", "M1")
    }
    return {
        "permission_timeframes": ["D1", "H4"],
        "setup_timeframe": "M15",
        "entry_timeframe": "M5",
        "bias": "bullish" if direction == "buy" else "bearish",
        "stage": _structure_stage(setup_tf),
        "strong_level": strong_level,
        "weak_target": weak_target,
        "last_confirmed_event": _last_event(setup_tf) or _last_event(entry_tf),
        "timeframe_sides": permission_sides,
    }


def _zone_caused_structure_break(zone: dict | None, frames: dict[str, dict], direction: str) -> bool:
    if not zone:
        return False
    zone_tf = zone.get("timeframe")
    structure_data = (frames.get(str(zone_tf)) or {}).get("market_structure") or {}
    event = _last_event(structure_data)
    event_type = str((event or {}).get("type") or "").upper()
    if event_type not in {"BOS", "CHOCH", "IBOS"}:
        return False
    return _structure_side(structure_data) == direction


def _annotated_poi(zone: dict | None, frames: dict[str, dict], direction: str) -> dict | None:
    if not zone:
        return None
    state = str(zone.get("state") or "").lower()
    item = dict(zone)
    item["type"] = item.get("type") or "fvg"
    item["caused_structure_break"] = _zone_caused_structure_break(zone, frames, direction)
    item["mitigated"] = state in {"partial", "filled"} or float(zone.get("fill_pct") or 0.0) > 0.0
    item["validity_reason"] = (
        "fresh aligned FVG"
        if state == "open"
        else "partial aligned FVG" if state == "partial" else "filled FVG"
    )
    item["poi_quality"] = (
        "primary"
        if item["caused_structure_break"] and not item["mitigated"]
        else "fresh" if state == "open"
        else "secondary" if state == "partial"
        else "invalid"
    )
    return item


def _pool_level(pool: dict) -> float | None:
    level = pool.get("level")
    if isinstance(level, (int, float)):
        return float(level)
    top = pool.get("top")
    bottom = pool.get("bottom")
    if isinstance(top, (int, float)) and isinstance(bottom, (int, float)):
        return (float(top) + float(bottom)) / 2.0
    return None


def _pool_between(pool: dict, lower: float, upper: float) -> bool:
    level = _pool_level(pool)
    if level is None:
        return False
    lo, hi = sorted((float(lower), float(upper)))
    return lo <= level <= hi


def _liquidity_context(
    *,
    frames: dict[str, dict],
    direction: str,
    zone: dict | None,
    quote_price: float,
    pip_size: float,
    swept_pools: list[dict],
    target_pools: list[dict],
    max_entry_distance_pips: float,
    behind_zone_tolerance_pips: float = 15.0,
) -> dict:
    if not zone:
        return {
            "sweep_in_zone_creation": False,
            "opposing_liquidity_in_front": False,
            "liquidity_behind_zone": False,
            "poi_trap_risk": False,
            "nearest_target_liquidity": target_pools[0] if target_pools else None,
            "context_note": "No active POI, so liquidity is informational only.",
        }

    opposing_side = "sell_side" if direction == "buy" else "buy_side"
    open_opposing = _pools(frames, side=opposing_side, status="open")
    lower = float(zone.get("lower", zone.get("entry_price")))
    upper = float(zone.get("upper", zone.get("entry_price")))
    entry_tolerance = pip_size * max(1.0, max_entry_distance_pips)
    behind_tolerance = pip_size * max(1.0, behind_zone_tolerance_pips)

    sweep_in_zone_creation = any(_pool_between(p, lower - behind_tolerance, upper + behind_tolerance) for p in swept_pools)
    if direction == "buy":
        opposing_in_front = (
            any(_pool_between(p, lower, quote_price) for p in open_opposing)
            or any(_pool_between(p, lower, quote_price) for p in swept_pools)
        )
        liquidity_behind = any(_pool_between(p, lower - behind_tolerance, lower) for p in open_opposing)
    else:
        opposing_in_front = (
            any(_pool_between(p, quote_price, upper) for p in open_opposing)
            or any(_pool_between(p, quote_price, upper) for p in swept_pools)
        )
        liquidity_behind = any(_pool_between(p, upper, upper + behind_tolerance) for p in open_opposing)

    nearest_target = None
    if target_pools:
        target_pools = sorted(
            target_pools,
            key=lambda p: abs((_pool_level(p) or quote_price) - quote_price),
        )
        nearest_target = target_pools[0]

    poi_trap_risk = bool(liquidity_behind and not opposing_in_front and not sweep_in_zone_creation)
    return {
        "sweep_in_zone_creation": bool(sweep_in_zone_creation),
        "opposing_liquidity_in_front": bool(opposing_in_front),
        "liquidity_behind_zone": bool(liquidity_behind),
        "poi_trap_risk": poi_trap_risk,
        "nearest_target_liquidity": nearest_target,
        "opposing_side": opposing_side,
        "behind_zone_tolerance_pips": behind_zone_tolerance_pips,
        "entry_tolerance_pips": max_entry_distance_pips,
        "context_note": (
            "Recent sweep or opposing liquidity supports the POI."
            if opposing_in_front or sweep_in_zone_creation
            else "No useful opposing liquidity context in front of the POI."
        ),
    }


def _entry_context(frames: dict[str, dict], direction: str, setup: dict | None) -> dict:
    checks = []
    for tf in ("M1", "M5"):
        structure_data = (frames.get(tf) or {}).get("market_structure") or {}
        internal = structure_data.get("internal") if isinstance(structure_data.get("internal"), dict) else {}
        side = _structure_side(structure_data)
        internal_side = _side_from_bias(internal.get("direction")) if internal else None
        event = internal.get("last_event") if isinstance(internal.get("last_event"), dict) else _last_event(structure_data)
        confirmed = side == direction or internal_side == direction
        opposite = side in {"buy", "sell"} and side != direction
        checks.append({
            "timeframe": tf,
            "side": side,
            "internal_side": internal_side,
            "stage": _structure_stage(structure_data),
            "last_event": event,
            "confirmed": bool(confirmed),
            "opposite": bool(opposite),
        })

    confirmed_tf = next((c for c in checks if c["confirmed"]), None)
    hard_opposite = all(c["opposite"] for c in checks)
    trigger = (
        f"{confirmed_tf['timeframe']} structure aligned"
        if confirmed_tf
        else "wait for M1/M5 shift in setup direction"
    )
    return {
        "model": "fvg_limit" if setup else "wait_for_shift",
        "timeframe": confirmed_tf["timeframe"] if confirmed_tf else "M1",
        "trigger": trigger,
        "entry_price": setup.get("entry") if setup else None,
        "sl": setup.get("sl") if setup else None,
        "tp": setup.get("tp") if setup else None,
        "rr": setup.get("rr") if setup else None,
        "invalidation": setup.get("sl") if setup else None,
        "confirmed": bool(confirmed_tf),
        "hard_opposite": bool(hard_opposite),
        "checks": checks,
    }


def sniper_poc(
    symbol: str,
    *,
    direction: str = "auto",
    bars: int = 300,
    max_spread_points: int = 30,
    min_rr: float = 1.5,
    entry_buffer_points: int = 5,
    min_stop_points: int = 50,
    stop_buffer_pips: float = 1.0,
    max_fvg_age_bars: int = 20,
    max_sweep_age_bars: int = 12,
    max_entry_distance_pips: float = 15.0,
    include_partial_fvg: bool = False,
    avoid_rollover: bool = True,
    include_frames: bool = True,
    generated_at: datetime | None = None,
) -> dict:
    """Build a non-mutating M1 sniper point-of-confluence limit plan.

    This analysis combines Ehukai structure, FVG, liquidity swings, and quote/DOM
    context. It intentionally returns a setup plan or ``no_trade``; order
    placement remains in the guarded order module.
    """
    direction = direction.lower()
    if direction not in {"auto", "buy", "sell"}:
        return _fail("MT5_INVALID_ARGUMENT", "direction must be one of: auto, buy, sell.")
    if (
        max_spread_points < 0
        or entry_buffer_points < 0
        or min_stop_points < 0
        or min_rr <= 0
        or max_fvg_age_bars < 0
        or max_sweep_age_bars < 0
        or max_entry_distance_pips < 0
    ):
        return _fail(
            "MT5_INVALID_ARGUMENT",
            "spread, buffer, stop, age, and distance limits must be >= 0; min_rr must be > 0.",
        )

    info = market.info(symbol)
    if not info.get("ok"):
        return info
    info_data = info["data"]
    tick = market.tick(symbol)
    quote_source = "market tick" if tick.get("ok") else "market info"
    quote = tick["data"] if tick.get("ok") else info_data
    bid = float(quote.get("bid") or info_data.get("bid"))
    ask = float(quote.get("ask") or info_data.get("ask"))
    point = float(info_data.get("point") or 0.00001)
    pip_size = _pip_size_from_info(info_data)
    digits = int(info_data.get("digits", 5) or 5)
    spread_points = int(round((ask - bid) / point)) if point else int(info_data.get("spread") or 0)

    depth = market.depth(symbol, levels=5)
    dom_context = {
        "source": "market depth" if depth.get("ok") else "quote_fallback",
        "available": bool(depth.get("ok")),
        "data": depth.get("data") if depth.get("ok") else None,
        "error": depth.get("error") if not depth.get("ok") else None,
    }

    generated_at = generated_at or datetime.now(tz=timezone.utc)
    frames = {tf: _frame(symbol, tf, bars) for tf in _SNIPER_TIMEFRAMES}
    side_counts = {"buy": 0, "sell": 0, "neutral": 0}
    for tf in ("D1", "H4", "M15", "M5"):
        bias_side = _side_from_bias(((frames.get(tf) or {}).get("market_structure") or {}).get("bias"))
        side_counts[bias_side or "neutral"] += 1

    selected_direction = direction
    if selected_direction == "auto":
        if side_counts["buy"] == side_counts["sell"]:
            selected_direction = "neutral"
        else:
            selected_direction = "buy" if side_counts["buy"] > side_counts["sell"] else "sell"
    if selected_direction == "neutral":
        data = {
            "symbol": symbol.upper(),
            "generated_at": generated_at.isoformat(),
            "status": "no_trade",
            "direction": None,
            "reason": "No directional majority across D1/H4/M15/M5 Ehukai structure.",
            "quote": {"source": quote_source, "bid": bid, "ask": ask, "spread_points": spread_points},
            "dom": dom_context,
            "bias_counts": side_counts,
            "frames_omitted": not include_frames,
        }
        if include_frames:
            data["frames"] = frames
        return {
            "ok": True,
            "data": data,
        }

    quote_trigger = ask if selected_direction == "buy" else bid
    zones = _matching_zones(
        frames,
        selected_direction,
        quote_trigger,
        pip_size=pip_size,
        max_age_bars=max_fvg_age_bars,
        max_entry_distance_pips=max_entry_distance_pips,
        include_partial=include_partial_fvg,
    )
    primary_zone = zones[0] if zones else None
    opposing_sweep_side = "sell_side" if selected_direction == "buy" else "buy_side"
    target_side = "buy_side" if selected_direction == "buy" else "sell_side"
    swept_pools = _pools(
        frames,
        side=opposing_sweep_side,
        status="swept",
        max_sweep_age_bars=max_sweep_age_bars,
    )
    target_pools = _pools(frames, side=target_side, status="open")
    structures = []
    for tf in ("M1", "M5", "M15"):
        structure_data = (frames.get(tf) or {}).get("market_structure")
        if structure_data:
            structures.append({**structure_data, "timeframe": tf})
    poi_context = _annotated_poi(primary_zone, frames, selected_direction)
    liquidity_context = _liquidity_context(
        frames=frames,
        direction=selected_direction,
        zone=poi_context,
        quote_price=quote_trigger,
        pip_size=pip_size,
        swept_pools=swept_pools,
        target_pools=target_pools,
        max_entry_distance_pips=max_entry_distance_pips,
    )
    structure_context = _structure_contract(frames, selected_direction)

    gates = [
        _gate("spread", spread_points <= max_spread_points, f"spread={spread_points} points; max={max_spread_points}"),
        _gate(
            "rollover_window",
            not (avoid_rollover and _is_fx_symbol(symbol) and generated_at.hour in _FX_ROLLOVER_HOURS_UTC),
            f"utc_hour={generated_at.hour}; rollover guard active for FX at 21:00-22:59 UTC",
        ),
        _gate(
            "m1_fvg_poc",
            bool(primary_zone),
            (
                "fresh open M1/M5/M15 FVG midpoint found"
                if primary_zone
                else (
                    "no open FVG midpoint within "
                    f"{max_entry_distance_pips:g} pips and {max_fvg_age_bars} bars"
                )
            ),
        ),
        _gate(
            "valid_poi",
            bool(poi_context and poi_context.get("poi_quality") != "invalid"),
            (
                f"{poi_context.get('timeframe')} {poi_context.get('validity_reason')}"
                if poi_context
                else "no valid FVG/POI in the active setup path"
            ),
        ),
        _gate(
            "liquidity_sweep",
            bool(swept_pools),
            (
                f"recent {opposing_sweep_side} sweep within {max_sweep_age_bars} bars"
                if swept_pools
                else f"no recent swept {opposing_sweep_side} pool in M1/M5/M15 context"
            ),
        ),
        _gate(
            "liquidity_trap",
            not liquidity_context.get("poi_trap_risk", False),
            liquidity_context.get("context_note", "liquidity context unavailable"),
        ),
    ]

    setup = None
    if primary_zone:
        entry = float(primary_zone["entry_price"])
        quote_side_ok = entry <= bid - entry_buffer_points * point if selected_direction == "buy" else entry >= ask + entry_buffer_points * point
        gates.append(_gate(
            "quote_side_limit",
            quote_side_ok,
            (
                f"buy limit entry {entry} must be below bid {bid} by {entry_buffer_points} points"
                if selected_direction == "buy"
                else f"sell limit entry {entry} must be above ask {ask} by {entry_buffer_points} points"
            ),
        ))

        if selected_direction == "buy":
            stop_refs = [float(primary_zone.get("lower", entry))]
            stop_refs += [float(s["support"]) for s in structures if isinstance(s.get("support"), (int, float)) and float(s["support"]) < entry]
            stop_refs += [float(p["bottom"]) for p in swept_pools if isinstance(p.get("bottom"), (int, float)) and float(p["bottom"]) < entry]
            sl = max(stop_refs) - stop_buffer_pips * pip_size
            sl = min(sl, entry - min_stop_points * point)
        else:
            stop_refs = [float(primary_zone.get("upper", entry))]
            stop_refs += [float(s["resistance"]) for s in structures if isinstance(s.get("resistance"), (int, float)) and float(s["resistance"]) > entry]
            stop_refs += [float(p["top"]) for p in swept_pools if isinstance(p.get("top"), (int, float)) and float(p["top"]) > entry]
            sl = min(stop_refs) + stop_buffer_pips * pip_size
            sl = max(sl, entry + min_stop_points * point)

        risk = abs(entry - sl)
        target = None
        reward = 0.0
        rr = 0.0
        for candidate in _target_candidates(target_pools, structures, selected_direction, entry):
            candidate_reward = abs(float(candidate["price"]) - entry)
            candidate_rr = candidate_reward / risk if risk else 0.0
            if target is None or candidate_rr >= min_rr:
                target = candidate
                reward = candidate_reward
                rr = candidate_rr
            if candidate_rr >= min_rr:
                break
        target_ok = target is not None
        gates.append(_gate("liquidity_or_structure_target", target_ok, target.get("label", "target found") if target else "no target beyond entry"))

        tp = float(target["price"]) if target else None
        stop_points = risk / point if point else 0.0
        gates.append(_gate("minimum_stop_distance", stop_points >= min_stop_points, f"stop={stop_points:.0f} points; min={min_stop_points}"))
        gates.append(_gate("minimum_rr", rr >= min_rr, f"rr={rr:.2f}; min={min_rr}"))

        setup = {
            "order_type": "buy_limit" if selected_direction == "buy" else "sell_limit",
            "entry": _round_price(entry, digits),
            "sl": _round_price(sl, digits),
            "tp": _round_price(tp, digits) if tp is not None else None,
            "stop_points": round(stop_points, 1),
            "risk_pips": round(risk / pip_size, 2) if pip_size else None,
            "reward_pips": round(reward / pip_size, 2) if pip_size else None,
            "rr": round(rr, 2),
            "poc": {
                "source": "Ehukai FVG midpoint",
                "timeframe": primary_zone["timeframe"],
                "zone": primary_zone,
            },
            "target": target,
            "strategy_id_suggestion": "ehukai-m1-sniper-poc",
        }

    entry_context = _entry_context(frames, selected_direction, setup)
    if setup:
        gates.append(_gate(
            "entry_structure",
            not entry_context["hard_opposite"],
            (
                entry_context["trigger"]
                if entry_context["confirmed"]
                else "M1/M5 has not shifted against the setup, but no entry confirmation yet"
            ),
            severity="blocker",
        ))

    blockers = [g for g in gates if not g["ok"] and g["severity"] == "blocker"]
    ready = bool(setup and not blockers and entry_context["confirmed"])
    watch = bool(setup and not blockers and not entry_context["confirmed"])
    status = "ready" if ready else "watch" if watch else "no_trade"
    if ready:
        dryrun_command = (
            f"mt5 --json order dryrun {symbol.upper()} {selected_direction} "
            f"--order-type limit --price {setup['entry']} --volume 0.001 --sl {setup['sl']} --tp {setup['tp']} "
            "--strategy-id ehukai-m1-sniper-poc"
        )
        limit_command = (
            f"mt5 --json order limit {symbol.upper()} {selected_direction} "
            f"--price {setup['entry']} --volume 0.001 --sl {setup['sl']} --tp {setup['tp']} "
            "--strategy-id ehukai-m1-sniper-poc"
        )
        setup["dryrun_command"] = dryrun_command
        setup["placement_command"] = limit_command
        setup["order_commands"] = [dryrun_command, limit_command]
        setup["order_command"] = dryrun_command + "\n" + limit_command

    confidence = sum(1 for g in gates if g["ok"]) / len(gates) if gates else 0.0
    explain = [
        structure_context.get("stage", "range"),
        (poi_context or {}).get("validity_reason") or "No active POI.",
        liquidity_context.get("context_note", "No liquidity context."),
        entry_context.get("trigger") or "No entry trigger.",
    ]
    data = {
            "symbol": symbol.upper(),
            "generated_at": generated_at.isoformat(),
            "status": status,
            "legacy_status": "candidate" if status == "ready" else status,
            "direction": selected_direction,
            "confidence_score": round(confidence, 2),
            "quality_score": round(confidence, 2),
            "reason": (
                "ready for dry-run"
                if status == "ready"
                else "watch for M1/M5 entry confirmation"
                if status == "watch"
                else "; ".join(g["detail"] for g in blockers)
            ),
            "quote": {
                "source": quote_source,
                "bid": bid,
                "ask": ask,
                "spread_points": spread_points,
                "point": point,
                "pip_size": pip_size,
                "buy_limits_trigger_on": "ask",
                "sell_limits_trigger_on": "bid",
            },
            "dom": dom_context,
            "bias_counts": side_counts,
            "structure": structure_context,
            "poi": poi_context,
            "liquidity": liquidity_context,
            "entry": entry_context,
            "gates": gates,
            "setup": setup,
            "explain": explain,
            "frames_omitted": not include_frames,
            "visual_contract": {
                "recommended_overlay": "EhukaiTDAOverlay",
                "entry_model": entry_context["model"],
                "visible_priority": ["top_down_panel", "active_poi", "latest_bos_or_choch", "entry_state", "invalidation"],
                "hide_by_default": ["old_structure_rails", "dense_liquidity_rails", "debug_labels"],
                "uses": ["EhukaiMarketStructure", "EhukaiFVG", "EhukaiLiquiditySwings", "market depth or quote fallback"],
            },
    }
    if include_frames:
        data["frames"] = frames
    return {"ok": True, "data": data}


def place_ready_limit(
    symbol: str,
    *,
    direction: str = "auto",
    volume: float | None = None,
    risk_pct: float | None = None,
    strategy_id: str = "ehukai-m1-sniper-poc",
    bars: int = 300,
    max_spread_points: int = 30,
    min_rr: float = 1.5,
    entry_buffer_points: int = 5,
    min_stop_points: int = 50,
    stop_buffer_pips: float = 1.0,
    max_fvg_age_bars: int = 20,
    max_sweep_age_bars: int = 12,
    max_entry_distance_pips: float = 15.0,
    include_partial_fvg: bool = False,
    avoid_rollover: bool = True,
    max_entry_drift_points: int = 5,
    filling: str = "auto",
    cfg: dict,
    is_live_intent: bool,
) -> dict:
    """Place a guarded limit order only when the setup contract remains READY.

    This is a supervised execution bridge. It deliberately does not enforce a
    demo-only account type because some broker demos report like live-capable
    accounts. Live permission stays with the existing CLI live-intent/risk gate.
    """
    if (volume is None) == (risk_pct is None):
        return _fail("MT5_INVALID_ARGUMENT", "Provide exactly one of volume or risk_pct.")
    if not strategy_id:
        return _fail("MT5_INVALID_ARGUMENT", "strategy_id is required for setup placement.")
    if max_entry_drift_points < 0:
        return _fail("MT5_INVALID_ARGUMENT", "max_entry_drift_points must be >= 0.")

    setup_kwargs = {
        "direction": direction,
        "bars": bars,
        "max_spread_points": max_spread_points,
        "min_rr": min_rr,
        "entry_buffer_points": entry_buffer_points,
        "min_stop_points": min_stop_points,
        "stop_buffer_pips": stop_buffer_pips,
        "max_fvg_age_bars": max_fvg_age_bars,
        "max_sweep_age_bars": max_sweep_age_bars,
        "max_entry_distance_pips": max_entry_distance_pips,
        "include_partial_fvg": include_partial_fvg,
        "avoid_rollover": avoid_rollover,
        "include_frames": False,
    }

    initial = sniper_poc(symbol, **setup_kwargs)
    if not initial.get("ok"):
        return initial
    initial_data = initial["data"]
    if initial_data.get("status") != "ready":
        return {
            "ok": False,
            "error": {
                "code": "EHUKAI_SETUP_NOT_READY",
                "message": initial_data.get("reason") or "Setup is not READY.",
                "mt5_retcode": None,
            },
            "data": {"setup": initial_data},
        }

    setup = initial_data.get("setup") or {}
    side = initial_data.get("direction")
    initial_entry = setup.get("entry")
    sl = setup.get("sl")
    tp = setup.get("tp")
    if side not in {"buy", "sell"} or not isinstance(initial_entry, (int, float)):
        return _fail("EHUKAI_SETUP_INVALID", "READY setup has no valid side/entry.")
    if not isinstance(sl, (int, float)) or not isinstance(tp, (int, float)):
        return _fail("EHUKAI_SETUP_INVALID", "READY setup must include SL and TP.")

    first_dryrun = order_module.dryrun(
        symbol.upper(),
        side,
        order_type="limit",
        price=float(initial_entry),
        volume=volume,
        risk_pct=risk_pct,
        sl=float(sl),
        tp=float(tp),
        strategy_id=strategy_id,
        filling=filling,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not first_dryrun.get("ok"):
        return {
            "ok": False,
            "error": first_dryrun.get("error"),
            "data": {"setup": initial_data, "dryrun": first_dryrun},
        }

    final = sniper_poc(symbol, **setup_kwargs)
    if not final.get("ok"):
        return final
    final_data = final["data"]
    if final_data.get("status") != "ready":
        return {
            "ok": False,
            "error": {
                "code": "EHUKAI_SETUP_CHANGED",
                "message": final_data.get("reason") or "Setup stopped being READY after dry-run.",
                "mt5_retcode": None,
            },
            "data": {"initial_setup": initial_data, "final_setup": final_data, "dryrun": first_dryrun},
        }

    final_setup = final_data.get("setup") or {}
    final_entry = final_setup.get("entry")
    final_sl = final_setup.get("sl")
    final_tp = final_setup.get("tp")
    if not isinstance(final_entry, (int, float)) or not isinstance(final_sl, (int, float)) or not isinstance(final_tp, (int, float)):
        return _fail("EHUKAI_SETUP_INVALID", "Final READY setup must include entry, SL, and TP.")
    point = float((final_data.get("quote") or {}).get("point") or 0.0)
    drift_points = abs(float(final_entry) - float(initial_entry)) / point if point else 0.0
    if drift_points > max_entry_drift_points:
        return {
            "ok": False,
            "error": {
                "code": "EHUKAI_SETUP_DRIFTED",
                "message": f"Entry drifted {drift_points:.1f} points after dry-run; max={max_entry_drift_points}.",
                "mt5_retcode": None,
            },
            "data": {"initial_setup": initial_data, "final_setup": final_data, "dryrun": first_dryrun},
        }

    immediate_dryrun = order_module.dryrun(
        symbol.upper(),
        side,
        order_type="limit",
        price=float(final_entry),
        volume=volume,
        risk_pct=risk_pct,
        sl=float(final_sl),
        tp=float(final_tp),
        strategy_id=strategy_id,
        filling=filling,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not immediate_dryrun.get("ok"):
        return {
            "ok": False,
            "error": immediate_dryrun.get("error"),
            "data": {"initial_setup": initial_data, "final_setup": final_data, "dryrun": immediate_dryrun},
        }

    placement = order_module.place_limit(
        symbol.upper(),
        side,
        float(final_entry),
        volume=volume,
        risk_pct=risk_pct,
        sl=float(final_sl),
        tp=float(final_tp),
        strategy_id=strategy_id,
        filling=filling,
        cfg=cfg,
        is_live_intent=is_live_intent,
    )
    if not placement.get("ok"):
        return {
            "ok": False,
            "error": placement.get("error"),
            "data": {"initial_setup": initial_data, "final_setup": final_data, "dryrun": immediate_dryrun, "placement": placement},
        }

    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "status": "placed",
            "strategy_id": strategy_id,
            "initial_setup": initial_data,
            "final_setup": final_data,
            "dryrun": immediate_dryrun["data"],
            "placement": placement["data"],
            "safety": {
                "ready_required": True,
                "dryrun_immediate_before_placement": True,
                "sl_required": True,
                "tp_required": True,
                "strategy_id_required": True,
                "account_type_block": False,
            },
        },
    }
