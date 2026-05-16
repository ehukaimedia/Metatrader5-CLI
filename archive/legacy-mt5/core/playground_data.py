"""Build browser-playground datasets from Strategy Tester artifacts."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from metatrader5_cli.mt5.core import mfe


def _fail(code: str, message: str, data: dict | None = None) -> dict:
    error = {"code": code, "message": message, "mt5_retcode": None}
    result = {"ok": False, "error": error}
    if data is not None:
        result["data"] = data
    return result


def build(
    run_dir: str | Path,
    *,
    timeframe: str = "M5",
    output_name: str = "trade_summary.json",
    chandelier_atr_multiplier: float = 3.0,
    be_trigger_r: float = 0.8,
    default_rr: float = 3.0,
    reconstruct_mfe: bool = False,
) -> dict:
    run_path = Path(run_dir).expanduser()
    if not run_path.exists():
        return _fail("PLAYGROUND_RUN_DIR_NOT_FOUND", f"Run directory not found: {run_path}")

    entries = _read_csv(run_path.glob("*_entries.csv"))
    exits = _read_csv(run_path.glob("*_exits.csv"))
    setups = _read_csv(run_path.glob("*_setups.csv"))
    if not entries or not exits:
        return _fail("PLAYGROUND_MISSING_JOURNALS", "Run directory must contain entries and exits CSV journals.")

    mfe_path = run_path / "mfe_mae.csv"
    mfe_source = "mfe_mae.csv"
    if not mfe_path.exists() and reconstruct_mfe:
        mfe_result = mfe.reconstruct_run(run_path, timeframe=timeframe)
        if not mfe_result.get("ok"):
            return mfe_result
    mfe_rows = _read_csv([mfe_path]) if mfe_path.exists() else []
    if not mfe_rows:
        mfe_source = "realized_r_fallback"

    dataset = _dataset(
        run_path,
        entries,
        exits,
        setups,
        mfe_rows,
        timeframe=timeframe,
        mfe_source=mfe_source,
        chandelier_atr_multiplier=chandelier_atr_multiplier,
        be_trigger_r=be_trigger_r,
        default_rr=default_rr,
    )
    output_path = run_path / output_name
    output_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    summary = dataset["summary"]
    summary_line = (
        f"trades={summary['trades']} "
        f"net_profit={summary['net_profit']:.2f} "
        f"pf={summary['profit_factor']:.2f} "
        f"expectancy_r={summary['expectancy_r']:.3f} "
        f"median_mfe_r={summary['median_mfe_r']:.3f} "
        f"median_extended_mfe_r={summary['median_extended_mfe_r']:.3f} "
        f"mfe_source={mfe_source}"
    )
    return {
        "ok": True,
        "data": {
            "run_dir": str(run_path),
            "output": str(output_path),
            "summary": summary,
            "summary_line": summary_line,
        },
    }


def _dataset(
    run_path: Path,
    entries: list[dict],
    exits: list[dict],
    setups: list[dict],
    mfe_rows: list[dict],
    *,
    timeframe: str,
    mfe_source: str,
    chandelier_atr_multiplier: float,
    be_trigger_r: float,
    default_rr: float,
) -> dict:
    trades = _merge_trades(entries, exits, mfe_rows, default_rr=default_rr, mfe_source=mfe_source)
    summary = _summary(trades, setups)
    symbol = _first_value(entries, "symbol") or _first_value(exits, "symbol") or ""
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_path),
        "symbol": symbol,
        "timeframe": timeframe,
        "inputs": {
            "chandelier_atr_multiplier": chandelier_atr_multiplier,
            "be_trigger_r": be_trigger_r,
            "default_rr": default_rr,
        },
        "feature_set_version": _feature_set_version(entries, exits),
        "mfe_source": mfe_source,
        "summary": summary,
        "setup_summary": _setup_summary(setups),
        "trades": trades,
        "source_files": {
            "entries": [path.name for path in run_path.glob("*_entries.csv")],
            "exits": [path.name for path in run_path.glob("*_exits.csv")],
            "setups": [path.name for path in run_path.glob("*_setups.csv")],
            "mfe_mae": ["mfe_mae.csv"] if (run_path / "mfe_mae.csv").exists() else [],
        },
    }


def _merge_trades(
    entries: list[dict],
    exits: list[dict],
    mfe_rows: list[dict],
    *,
    default_rr: float,
    mfe_source: str,
) -> list[dict]:
    exits_by_position = {row.get("position"): row for row in exits if row.get("position")}
    mfe_by_position = {row.get("position"): row for row in mfe_rows if row.get("position")}
    trades = []
    for index, entry in enumerate(entries, start=1):
        position = entry.get("position")
        exit_row = exits_by_position.get(position)
        if not exit_row:
            continue
        mfe_row = mfe_by_position.get(position, {})
        realized_r = _float(exit_row.get("realized_r"))
        initial_risk = _float(entry.get("initial_risk"))
        planned_rr = _planned_rr(entry, default_rr)
        mfe_r, mae_r = _mfe_mae(realized_r, mfe_row, mfe_source)
        profit = _float(exit_row.get("profit"))
        trade = {
            "index": index,
            "position": position,
            "symbol": entry.get("symbol") or exit_row.get("symbol") or "",
            "direction": entry.get("direction", ""),
            "lots": _float(entry.get("lots")),
            "entry_time": entry.get("time", ""),
            "exit_time": exit_row.get("time", ""),
            "entry_deal": entry.get("deal", ""),
            "exit_deal": exit_row.get("deal", ""),
            "entry_price": _float(entry.get("price")),
            "exit_price": _float(exit_row.get("price")),
            "sl": _float(entry.get("sl")),
            "tp": _float(entry.get("tp")),
            "initial_risk": initial_risk,
            "planned_rr": planned_rr,
            "realized_r": realized_r,
            "profit": profit,
            "commission": _float(exit_row.get("commission")),
            "swap": _float(exit_row.get("swap")),
            "reason": exit_row.get("reason", ""),
            "exit_type": _exit_type(exit_row.get("reason", ""), realized_r, planned_rr),
            "mfe_r": mfe_r,
            "mae_r": mae_r,
            "mfe_price": _optional_float(mfe_row.get("mfe_price")),
            "mae_price": _optional_float(mfe_row.get("mae_price")),
            "bars": int(_float(mfe_row.get("bars"))),
            "extended_mfe_r": _optional_float(mfe_row.get("extended_mfe_r")),
            "extended_mfe_price": _optional_float(mfe_row.get("extended_mfe_price")),
            "extended_event": mfe_row.get("extended_event", ""),
            "extended_bars": int(_float(mfe_row.get("extended_bars"))),
            "htf_momentum_d1": _feature_float(entry, exit_row, "htf_momentum_d1"),
            "time_since_sweep_pivot_bars": _feature_int(entry, exit_row, "time_since_sweep_pivot_bars"),
            "time_since_sweep_event_bars": _feature_int(entry, exit_row, "time_since_sweep_event_bars"),
            "room_to_swing_high_pips": _feature_float(entry, exit_row, "room_to_swing_high_pips"),
            "spread_to_atr_ratio": _feature_float(entry, exit_row, "spread_to_atr_ratio"),
            "m5_m1_event_lag_bars": _feature_int(entry, exit_row, "m5_m1_event_lag_bars"),
            "mfe_source": mfe_source,
        }
        trades.append(trade)
    return trades


def _summary(trades: list[dict], setups: list[dict]) -> dict:
    profits = [trade["profit"] for trade in trades]
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))
    realized = [trade["realized_r"] for trade in trades]
    mfe_values = [trade["mfe_r"] for trade in trades if trade["mfe_r"] is not None]
    mae_values = [trade["mae_r"] for trade in trades if trade["mae_r"] is not None]
    extended_values = [trade["extended_mfe_r"] for trade in trades if trade["extended_mfe_r"] is not None]
    wins = sum(1 for value in profits if value > 0)
    losses = sum(1 for value in profits if value < 0)
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(trades), 4) if trades else 0.0,
        "net_profit": round(sum(profits), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "expected_payoff": round(sum(profits) / len(profits), 2) if profits else 0.0,
        "expectancy_r": round(sum(realized) / len(realized), 4) if realized else 0.0,
        "max_drawdown": round(_max_drawdown(profits), 2),
        "median_mfe_r": round(median(mfe_values), 3) if mfe_values else 0.0,
        "median_mae_r": round(median(mae_values), 3) if mae_values else 0.0,
        "mfe_gte_1_5r": sum(1 for value in mfe_values if value >= 1.5),
        "mfe_lt_1r": sum(1 for value in mfe_values if value < 1.0),
        "median_extended_mfe_r": round(median(extended_values), 3) if extended_values else 0.0,
        "extended_mfe_gte_1_5r": sum(1 for value in extended_values if value >= 1.5),
        "extended_mfe_lt_1r": sum(1 for value in extended_values if value < 1.0),
        "setup_rows": len(setups),
    }


def _setup_summary(setups: list[dict]) -> dict:
    statuses: dict[str, int] = {}
    failures: dict[str, int] = {}
    for row in setups:
        status = row.get("status") or "none"
        failure = row.get("failure") or "none"
        statuses[status] = statuses.get(status, 0) + 1
        failures[failure] = failures.get(failure, 0) + 1
    return {"rows": len(setups), "statuses": statuses, "failure_modes": failures}


def _feature_set_version(entries: list[dict], exits: list[dict]) -> int:
    feature_field = "htf_momentum_d1"
    for row in [*entries, *exits]:
        if feature_field in row:
            return 2
    return 1


def _read_csv(paths) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _planned_rr(entry: dict, default_rr: float) -> float:
    entry_price = _float(entry.get("price"))
    sl = _float(entry.get("sl"))
    tp = _float(entry.get("tp"))
    risk = abs(entry_price - sl)
    reward = abs(tp - entry_price)
    if risk <= 0 or reward <= 0:
        return float(default_rr)
    return round(reward / risk, 3)


def _mfe_mae(realized_r: float, mfe_row: dict, mfe_source: str) -> tuple[float | None, float | None]:
    if mfe_source == "mfe_mae.csv" and mfe_row:
        return _optional_float(mfe_row.get("mfe_r")), _optional_float(mfe_row.get("mae_r"))
    return max(0.0, realized_r), max(0.0, -realized_r)


def _exit_type(reason: str, realized_r: float, planned_rr: float) -> str:
    reason_text = (reason or "").lower()
    if abs(realized_r) < 0.05:
        return "breakeven"
    if realized_r >= planned_rr * 0.9:
        return "tp"
    if "sl" in reason_text:
        return "trail_sl" if abs(realized_r) < 0.85 else "structural_sl"
    return "manual_or_other"


def _max_drawdown(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _first_value(rows: list[dict], field: str) -> str:
    for row in rows:
        if row.get(field):
            return row[field]
    return ""


def _optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    return _float(value)


def _feature_float(entry: dict, exit_row: dict, field: str) -> float | None:
    value = entry.get(field)
    if value in (None, ""):
        value = exit_row.get(field)
    return _optional_float(value)


def _feature_int(entry: dict, exit_row: dict, field: str) -> int:
    value = entry.get(field)
    if value in (None, ""):
        value = exit_row.get(field)
    if value in (None, ""):
        return -1
    return int(_float(value))


def _float(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
