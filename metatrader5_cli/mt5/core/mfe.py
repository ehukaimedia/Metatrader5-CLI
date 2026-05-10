"""Post-hoc MFE/MAE reconstruction for Strategy Tester journals.

This intentionally uses M5 OHLC bars as the cheap review path. Backlog:
EA-side tick-accurate MFE/MAE journaling, tick-level post-hoc reconstruction,
and saved HTML report parsing.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from metatrader5_cli.mt5.core import rates as rates_module


def _fail(code: str, message: str, data: dict | None = None) -> dict:
    error = {"code": code, "message": message, "mt5_retcode": None}
    result = {"ok": False, "error": error}
    if data is not None:
        result["data"] = data
    return result


def reconstruct_run(run_dir: str | Path, *, timeframe: str = "M5", output_name: str = "mfe_mae.csv") -> dict:
    run_path = Path(run_dir).expanduser()
    if not run_path.exists():
        return _fail("MFE_RUN_DIR_NOT_FOUND", f"Run directory not found: {run_path}")

    entries = _read_csv(run_path.glob("*_entries.csv"))
    exits = _read_csv(run_path.glob("*_exits.csv"))
    setups = _read_csv(run_path.glob("*_setups.csv"))
    if not entries or not exits:
        return _fail("MFE_MISSING_JOURNALS", "Run directory must contain entries and exits CSV journals.")

    pairs = _pair_trades(entries, exits)
    if not pairs:
        return _fail("MFE_NO_PAIRED_TRADES", "No entry/exit rows could be paired by position.")

    symbol = pairs[0]["entry"].get("symbol") or "USDJPY"
    data_end = _dataset_end_time(run_path, entries, exits, setups, timeframe)
    rows = []
    for pair in pairs:
        bars_result = _fetch_pair_bars(pair, timeframe)
        if not bars_result.get("ok"):
            return bars_result
        row = calculate_trade_excursion(pair["entry"], pair["exit"], bars_result["data"], timeframe=timeframe)
        extended_result = _fetch_extended_bars(pair, timeframe, data_end)
        if not extended_result.get("ok"):
            return extended_result
        row.update(
            calculate_extended_excursion(
                pair["entry"],
                extended_result["data"],
                setup=_match_setup(pair["entry"], setups),
                timeframe=timeframe,
            )
        )
        rows.append(row)
    output_path = run_path / output_name
    _write_rows(output_path, rows)
    summary = summarize(rows)
    summary_line = (
        f"median_mfe_r={summary['median_mfe_r']:.3f} "
        f"median_mae_r={summary['median_mae_r']:.3f} "
        f"mfe_gte_1_5r={summary['mfe_gte_1_5r']} "
        f"mfe_lt_1r={summary['mfe_lt_1r']} "
        f"median_extended_mfe_r={summary['median_extended_mfe_r']:.3f} "
        f"extended_mfe_gte_1_5r={summary['extended_mfe_gte_1_5r']} "
        f"extended_mfe_lt_1r={summary['extended_mfe_lt_1r']} "
        f"calculated={summary['calculated_trades']}/{summary['trades']}"
    )
    return {
        "ok": True,
        "data": {
            "run_dir": str(run_path),
            "output": str(output_path),
            "symbol": symbol,
            "timeframe": timeframe,
            "summary": summary,
            "summary_line": summary_line,
        },
    }


def calculate_trade_excursion(entry: dict, exit_row: dict, bars: list[dict], *, timeframe: str = "M5") -> dict:
    entry_time = _parse_time(entry["time"])
    exit_time = _parse_time(exit_row["time"])
    if exit_time < entry_time:
        entry_time, exit_time = exit_time, entry_time

    interval_bars = _bars_for_interval(bars, entry_time, exit_time, timeframe)
    base = {
        "position": entry.get("position", ""),
        "entry_deal": entry.get("deal", ""),
        "exit_deal": exit_row.get("deal", ""),
        "symbol": entry.get("symbol", exit_row.get("symbol", "")),
        "direction": entry.get("direction", ""),
        "entry_time": entry.get("time", ""),
        "exit_time": exit_row.get("time", ""),
        "entry_price": _fmt(_float(entry.get("price"))),
        "exit_price": _fmt(_float(exit_row.get("price"))),
        "initial_risk": _fmt(_float(entry.get("initial_risk"))),
    }
    if not interval_bars:
        return {**base, "status": "no_bars", "mfe_price": "", "mae_price": "", "mfe": "", "mae": "", "mfe_r": "", "mae_r": "", "bars": 0}

    entry_price = _float(entry.get("price"))
    risk = _float(entry.get("initial_risk"))
    direction = (entry.get("direction") or "").upper()
    high = max(_float(bar.get("high")) for bar in interval_bars)
    low = min(_float(bar.get("low")) for bar in interval_bars)
    if direction == "SELL":
        mfe_price = low
        mae_price = high
        mfe = max(0.0, entry_price - low)
        mae = max(0.0, high - entry_price)
    else:
        mfe_price = high
        mae_price = low
        mfe = max(0.0, high - entry_price)
        mae = max(0.0, entry_price - low)

    return {
        **base,
        "status": "ok",
        "mfe_price": _fmt(mfe_price),
        "mae_price": _fmt(mae_price),
        "mfe": _fmt(mfe),
        "mae": _fmt(mae),
        "mfe_r": _fmt(mfe / risk if risk > 0 else 0.0, digits=3),
        "mae_r": _fmt(mae / risk if risk > 0 else 0.0, digits=3),
        "bars": len(interval_bars),
    }


def calculate_extended_excursion(
    entry: dict,
    bars: list[dict],
    *,
    setup: dict | None = None,
    timeframe: str = "M5",
    default_rr: float = 3.0,
) -> dict:
    entry_time = _parse_time(entry["time"])
    interval_bars = [bar for bar in bars if _parse_time(str(bar["time"])) + _tf_delta(timeframe) >= entry_time]
    entry_price = _float(entry.get("price"))
    direction = (entry.get("direction") or "").upper()
    risk = _risk_distance(entry, setup)
    rr = _setup_rr(setup, default_rr)
    if risk <= 0 or not interval_bars:
        return {
            "extended_status": "no_bars" if not interval_bars else "bad_risk",
            "extended_mfe_price": "",
            "extended_mfe": "",
            "extended_mfe_r": "",
            "extended_event": "",
            "extended_bars": 0,
            "extended_rr": _fmt(rr, digits=3),
            "extended_sl": "",
            "extended_tp": "",
        }

    if direction == "SELL":
        sl = entry_price + risk
        tp = entry_price - (rr * risk)
        best_price = entry_price
    else:
        sl = entry_price - risk
        tp = entry_price + (rr * risk)
        best_price = entry_price

    event = "end"
    bars_seen = 0
    for bar in interval_bars:
        bars_seen += 1
        high = _float(bar.get("high"))
        low = _float(bar.get("low"))
        if direction == "SELL":
            best_price = min(best_price, low)
            tp_hit = low <= tp
            sl_hit = high >= sl
        else:
            best_price = max(best_price, high)
            tp_hit = high >= tp
            sl_hit = low <= sl
        if tp_hit or sl_hit:
            event = "tp_and_sl_same_bar" if tp_hit and sl_hit else ("tp" if tp_hit else "sl")
            break

    extended_mfe = max(0.0, entry_price - best_price) if direction == "SELL" else max(0.0, best_price - entry_price)
    return {
        "extended_status": "ok",
        "extended_mfe_price": _fmt(best_price),
        "extended_mfe": _fmt(extended_mfe),
        "extended_mfe_r": _fmt(extended_mfe / risk, digits=3),
        "extended_event": event,
        "extended_bars": bars_seen,
        "extended_rr": _fmt(rr, digits=3),
        "extended_sl": _fmt(sl),
        "extended_tp": _fmt(tp),
    }


def _fetch_pair_bars(pair: dict, timeframe: str) -> dict:
    entry = pair["entry"]
    exit_row = pair["exit"]
    symbol = entry.get("symbol") or exit_row.get("symbol") or "USDJPY"
    width = _tf_delta(timeframe)
    date_from = _floor_time(_parse_time(entry["time"]), width)
    date_to = _parse_time(exit_row["time"]) + width
    result = rates_module.range(symbol, timeframe, _as_utc(date_from), _as_utc(date_to))
    if not result.get("ok"):
        if result.get("error", {}).get("code") == "MT5_NO_DATA":
            return {"ok": True, "data": []}
        return result
    return {"ok": True, "data": [_normalize_bar(row) for row in result["data"]]}


def _fetch_extended_bars(pair: dict, timeframe: str, data_end: datetime) -> dict:
    entry = pair["entry"]
    exit_row = pair["exit"]
    symbol = entry.get("symbol") or exit_row.get("symbol") or "USDJPY"
    width = _tf_delta(timeframe)
    date_from = _floor_time(_parse_time(entry["time"]), width)
    result = rates_module.range(symbol, timeframe, _as_utc(date_from), _as_utc(data_end))
    if not result.get("ok"):
        if result.get("error", {}).get("code") == "MT5_NO_DATA":
            return {"ok": True, "data": []}
        return result
    return {"ok": True, "data": [_normalize_bar(row) for row in result["data"]]}


def summarize(rows: list[dict]) -> dict:
    calculated = [row for row in rows if row.get("status") == "ok"]
    mfe_values = [_float(row.get("mfe_r")) for row in calculated]
    mae_values = [_float(row.get("mae_r")) for row in calculated]
    extended_values = [_float(row.get("extended_mfe_r")) for row in rows if row.get("extended_status") == "ok"]
    return {
        "trades": len(rows),
        "calculated_trades": len(calculated),
        "missing_bar_trades": len(rows) - len(calculated),
        "median_mfe_r": round(median(mfe_values), 3) if mfe_values else 0.0,
        "median_mae_r": round(median(mae_values), 3) if mae_values else 0.0,
        "mfe_gte_1_5r": sum(1 for value in mfe_values if value >= 1.5),
        "mfe_lt_1r": sum(1 for value in mfe_values if value < 1.0),
        "median_extended_mfe_r": round(median(extended_values), 3) if extended_values else 0.0,
        "extended_mfe_gte_1_5r": sum(1 for value in extended_values if value >= 1.5),
        "extended_mfe_lt_1r": sum(1 for value in extended_values if value < 1.0),
    }


def _pair_trades(entries: list[dict], exits: list[dict]) -> list[dict]:
    exits_by_position = {row.get("position"): row for row in exits if row.get("position")}
    pairs = []
    for entry in entries:
        exit_row = exits_by_position.get(entry.get("position"))
        if exit_row:
            pairs.append({"entry": entry, "exit": exit_row})
    return pairs


def _bars_for_interval(bars: list[dict], entry_time: datetime, exit_time: datetime, timeframe: str) -> list[dict]:
    width = _tf_delta(timeframe)
    selected = []
    for bar in bars:
        bar_time = _parse_time(str(bar["time"]))
        if bar_time <= exit_time and bar_time + width >= entry_time:
            selected.append(bar)
    return selected


def _match_setup(entry: dict, setups: list[dict]) -> dict | None:
    entry_time = _parse_time(entry["time"])
    entry_price = _float(entry.get("price"))
    symbol = entry.get("symbol")
    direction = entry.get("direction")
    matches = []
    for setup in setups:
        if setup.get("status") != "READY":
            continue
        if symbol and setup.get("symbol") != symbol:
            continue
        if direction and setup.get("direction") != direction:
            continue
        setup_time = _parse_time(setup["time"])
        if setup_time > entry_time:
            continue
        if entry_price and abs(_float(setup.get("entry")) - entry_price) > 0.0002:
            continue
        matches.append((setup_time, setup))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def _risk_distance(entry: dict, setup: dict | None) -> float:
    entry_price = _float(entry.get("price"))
    if setup:
        setup_sl = _float(setup.get("sl"))
        if setup_sl:
            distance = abs(entry_price - setup_sl)
            if distance > 0:
                return distance
    risk = _float(entry.get("initial_risk"))
    if risk > 0:
        return risk
    sl = _float(entry.get("sl"))
    return abs(entry_price - sl) if sl else 0.0


def _setup_rr(setup: dict | None, default_rr: float) -> float:
    if setup:
        rr = _float(setup.get("rr"))
        if rr > 0:
            return rr
    return default_rr


def _dataset_end_time(run_path: Path, entries: list[dict], exits: list[dict], setups: list[dict], timeframe: str) -> datetime:
    cache_end = _cache_end_time(run_path)
    if cache_end is not None:
        return cache_end
    times = [_parse_time(row["time"]) for row in [*entries, *exits, *setups] if row.get("time")]
    if not times:
        return datetime.now()
    return max(times) + _tf_delta(timeframe)


def _cache_end_time(run_path: Path) -> datetime | None:
    for path in run_path.glob("*.tst"):
        parts = path.name.split(".")
        for part in parts:
            if "_" not in part:
                continue
            start_text, end_text = part.split("_", 1)
            if len(start_text) == 8 and len(end_text) == 8 and start_text.isdigit() and end_text.isdigit():
                return datetime(
                    int(end_text[0:4]),
                    int(end_text[4:6]),
                    int(end_text[6:8]),
                    23,
                    59,
                    59,
                )
    return None


def _tf_delta(timeframe: str) -> timedelta:
    label = timeframe.upper()
    if label.startswith("M"):
        return timedelta(minutes=int(label[1:]))
    if label.startswith("H"):
        return timedelta(hours=int(label[1:]))
    if label == "D1":
        return timedelta(days=1)
    return timedelta(minutes=5)


def _floor_time(value: datetime, width: timedelta) -> datetime:
    seconds = int(width.total_seconds())
    if seconds <= 0:
        return value
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((value - midnight).total_seconds())
    return midnight + timedelta(seconds=(elapsed // seconds) * seconds)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc)


def _read_csv(paths) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    fields = [
        "position", "entry_deal", "exit_deal", "symbol", "direction", "entry_time", "exit_time",
        "entry_price", "exit_price", "initial_risk", "status", "mfe_price", "mae_price",
        "mfe", "mae", "mfe_r", "mae_r", "bars", "extended_status", "extended_mfe_price",
        "extended_mfe", "extended_mfe_r", "extended_event", "extended_bars", "extended_rr",
        "extended_sl", "extended_tp",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_bar(row: dict) -> dict:
    return {
        "time": row["time"],
        "high": _float(row.get("high")),
        "low": _float(row.get("low")),
    }


def _parse_time(value: str) -> datetime:
    text = value.strip().replace(".", "-", 2).replace(" ", "T")
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=None)


def _float(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: float, *, digits: int = 5) -> str:
    return f"{value:.{digits}f}"
