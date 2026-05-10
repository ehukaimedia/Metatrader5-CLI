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
    if not entries or not exits:
        return _fail("MFE_MISSING_JOURNALS", "Run directory must contain entries and exits CSV journals.")

    pairs = _pair_trades(entries, exits)
    if not pairs:
        return _fail("MFE_NO_PAIRED_TRADES", "No entry/exit rows could be paired by position.")

    symbol = pairs[0]["entry"].get("symbol") or "USDJPY"
    rows = []
    for pair in pairs:
        bars_result = _fetch_pair_bars(pair, timeframe)
        if not bars_result.get("ok"):
            return bars_result
        rows.append(calculate_trade_excursion(pair["entry"], pair["exit"], bars_result["data"], timeframe=timeframe))
    output_path = run_path / output_name
    _write_rows(output_path, rows)
    summary = summarize(rows)
    summary_line = (
        f"median_mfe_r={summary['median_mfe_r']:.3f} "
        f"median_mae_r={summary['median_mae_r']:.3f} "
        f"mfe_gte_1_5r={summary['mfe_gte_1_5r']} "
        f"mfe_lt_1r={summary['mfe_lt_1r']} "
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


def summarize(rows: list[dict]) -> dict:
    calculated = [row for row in rows if row.get("status") == "ok"]
    mfe_values = [_float(row.get("mfe_r")) for row in calculated]
    mae_values = [_float(row.get("mae_r")) for row in calculated]
    return {
        "trades": len(rows),
        "calculated_trades": len(calculated),
        "missing_bar_trades": len(rows) - len(calculated),
        "median_mfe_r": round(median(mfe_values), 3) if mfe_values else 0.0,
        "median_mae_r": round(median(mae_values), 3) if mae_values else 0.0,
        "mfe_gte_1_5r": sum(1 for value in mfe_values if value >= 1.5),
        "mfe_lt_1r": sum(1 for value in mfe_values if value < 1.0),
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
        "mfe", "mae", "mfe_r", "mae_r", "bars",
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
