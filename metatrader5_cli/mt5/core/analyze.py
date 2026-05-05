"""
analyze.py — Top-down multi-timeframe analysis and price structure for the MT5 CLI.

This module NEVER imports MetaTrader5 directly.  MT5 access stays behind core
modules such as rates, market, and the structured Ehukai mirrors.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from metatrader5_cli.mt5.core import ehukai, market, rates as rates_module


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
    """Return TF market-structure classification or None on any data error."""
    result = structure(symbol, timeframe, bars=bars)
    if not result["ok"]:
        return None
    data = result["data"]
    swing_highs = data["swing_highs"]
    swing_lows = data["swing_lows"]

    structure_state = "range"
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        prev_high, last_high = swing_highs[-2]["price"], swing_highs[-1]["price"]
        prev_low, last_low = swing_lows[-2]["price"], swing_lows[-1]["price"]
        if last_high > prev_high and last_low > prev_low:
            structure_state = "HH_HL"
        elif last_high < prev_high and last_low < prev_low:
            structure_state = "LH_LL"
        else:
            structure_state = "mixed"

    if structure_state == "HH_HL":
        trend = "bullish"
    elif structure_state == "LH_LL":
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "timeframe": timeframe,
        "trend": trend,
        "structure": structure_state,
        "current_price": data["current_price"],
        "support": data["support"],
        "resistance": data["resistance"],
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
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
            f"support={r['support']}, resistance={r['resistance']}"
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
_SNIPER_TIMEFRAMES = ["H4", "H1", "M15", "M5", "M1"]
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


def _frame(symbol: str, timeframe: str, bars: int) -> dict:
    frame = {"timeframe": timeframe}
    structure = ehukai.market_structure(symbol, timeframe, bars=bars)
    fvg = ehukai.fvg(symbol, timeframe, bars=min(bars, 100), max_zones=4)
    liquidity = ehukai.liquidity(symbol, timeframe, bars=bars, max_pools=10)
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
    for tf in ("H4", "H1", "M15", "M5"):
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
            "reason": "No directional majority across H4/H1/M15/M5 Ehukai structure.",
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
            "liquidity_sweep",
            bool(swept_pools),
            (
                f"recent {opposing_sweep_side} sweep within {max_sweep_age_bars} bars"
                if swept_pools
                else f"no recent swept {opposing_sweep_side} pool in M1/M5/M15 context"
            ),
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
        if all(g["ok"] for g in gates):
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
            setup["order_command"] = (
                dryrun_command + "\n" + limit_command
            )

    status = "candidate" if setup and all(g["ok"] for g in gates) else "no_trade"
    confidence = sum(1 for g in gates if g["ok"]) / len(gates) if gates else 0.0
    blockers = [g for g in gates if not g["ok"] and g["severity"] == "blocker"]
    data = {
            "symbol": symbol.upper(),
            "generated_at": generated_at.isoformat(),
            "status": status,
            "direction": selected_direction,
            "confidence_score": round(confidence, 2),
            "reason": "candidate ready for dry-run" if status == "candidate" else "; ".join(g["detail"] for g in blockers),
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
            "gates": gates,
            "setup": setup,
            "frames_omitted": not include_frames,
            "visual_contract": {
                "recommended_overlay": "EhukaiTDAOverlay",
                "entry_model": "M1 sniper point-of-confluence limit plan",
                "uses": ["EhukaiMarketStructure", "EhukaiFVG", "EhukaiLiquiditySwings", "market depth or quote fallback"],
            },
    }
    if include_frames:
        data["frames"] = frames
    return {"ok": True, "data": data}
