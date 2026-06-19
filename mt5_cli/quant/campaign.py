"""Quant campaign orchestration: per-cell explicit two-pass -> quant.v1.

For each (symbol, timeframe) cell, serially (the launcher forbids parallel
terminals): optimize the in-sample window [from, split-1], pick the winner by
in-sample profit factor, then single() the winner over the OOS window
[split, to] and the FULL window [from, to]. Composes the filesystem-only tester
primitives; like the tester package, this module MUST NOT import MetaTrader5.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mt5_cli.reports import fail, ok
from mt5_cli.tester import ea, ini_builder

from . import matrix, passes, report, selection, store

_RANK_BY = ("full_net", "oos_sharpe", "oos_pf")


def _metrics(env: dict[str, Any]) -> dict[str, Any]:
    """Project a single() envelope's stats into a cell metric block."""
    stats = env["data"].get("stats", {}) if env.get("ok") else {}
    return {
        "trades": stats.get("total_trades"),
        "net_profit": stats.get("net_profit"),
        "profit_factor": stats.get("profit_factor"),
        "sharpe": stats.get("sharpe"),
        "max_drawdown_pct": stats.get("max_drawdown_pct"),
        "win_rate": stats.get("win_rate"),
    }


def _clears_is_gates(metrics: dict[str, Any], *, min_pf: float, min_is_trades: int) -> bool:
    pf = metrics.get("profit_factor")
    trades = metrics.get("trades")
    if not isinstance(pf, (int, float)) or pf < min_pf:
        return False
    if min_is_trades <= 0:
        return True
    return isinstance(trades, (int, float)) and trades >= min_is_trades


def _run_cell(*, expert: str, symbol: str, tf: str, from_date: str, to_date: str,
              split_day: str, is_end_day: str, params: list[str], param_names: list[str],
              fixed_params: dict[str, str],
              mode: str, min_pf: float, min_is_trades: int, modelling: str,
              results_root: Path | str, timeout: int) -> dict[str, Any]:
    base: dict[str, Any] = {"symbol": symbol, "timeframe": tf}
    child_runs: list[str] = []

    def _track(env: dict[str, Any]) -> dict[str, Any]:
        """Record a successful launch's run_id so the manifest can list every child run."""
        if env.get("ok"):
            rid = env["data"].get("run_id")
            if rid:
                child_runs.append(rid)
        return env

    if not param_names:
        is_env = _track(ea.single(expert=expert, symbol=symbol, timeframe=tf,
                                  from_date=from_date, to_date=is_end_day,
                                  modelling=modelling, params=fixed_params or None,
                                  run_label=f"quant-is-{expert}",
                                  results_root=results_root, timeout=timeout))
        if not is_env["ok"]:
            return {**base, "reason": "CELL_FAILED", "envelope": is_env,
                    "child_runs": child_runs}
        is_metrics = _metrics(is_env)
        if (is_metrics.get("trades") or 0) == 0:
            return {**base, "reason": "NO_TRADES", "child_runs": child_runs,
                    "note": "fixed-parameter in-sample run produced zero trades"}
        if not _clears_is_gates(is_metrics, min_pf=min_pf, min_is_trades=min_is_trades):
            return {**base, "reason": "NO_WINNER", "child_runs": child_runs}

        set_path = is_env["data"].get("generated_set_file") or is_env["data"].get("set_file")
        oos = _track(ea.single(expert=expert, symbol=symbol, timeframe=tf,
                               from_date=split_day, to_date=to_date,
                               set_file=set_path, run_label=f"quant-oos-{expert}",
                               results_root=results_root, timeout=timeout))
        if not oos["ok"]:
            return {**base, "reason": "CELL_FAILED", "envelope": oos,
                    "child_runs": child_runs}
        full = _track(ea.single(expert=expert, symbol=symbol, timeframe=tf,
                                from_date=from_date, to_date=to_date,
                                set_file=set_path, run_label=f"quant-full-{expert}",
                                results_root=results_root, timeout=timeout))
        if not full["ok"]:
            return {**base, "reason": "CELL_FAILED", "envelope": full,
                    "child_runs": child_runs}

        return {**base, "side": None, "set_file": set_path, "run_id": full["data"].get("run_id"),
                "params": fixed_params, "is": is_metrics, "oos": _metrics(oos),
                "full": _metrics(full), "equity_curve": full["data"].get("equity_curve", []),
                "child_runs": child_runs}

    opt = _track(ea.optimize(expert=expert, symbol=symbol, timeframe=tf, from_date=from_date,
                             to_date=is_end_day, mode=mode, params=params, modelling=modelling,
                             results_root=results_root, timeout=timeout))
    if not opt["ok"]:
        return {**base, "reason": "CELL_FAILED", "envelope": opt, "child_runs": child_runs}

    rows = passes.read_rows(opt["data"].get("optimization") or [], param_names=param_names)
    if rows and all((row.get("is", {}).get("trades") or 0) == 0 for row in rows):
        return {**base, "reason": "NO_TRADES", "child_runs": child_runs,
                "note": "optimization produced zero in-sample trades across every pass"}
    winner = selection.pick_winner(rows, min_pf=min_pf, min_is_trades=min_is_trades)
    if winner is None:
        return {**base, "reason": "NO_WINNER", "child_runs": child_runs}
    if any(v is None for v in winner["params"].values()):
        return {**base, "reason": "CELL_FAILED",
                "note": "winning pass is missing optimized parameter columns "
                        "(confirm the optimization report includes the requested input columns)",
                "child_runs": child_runs}

    # Write the winner's FIXED parameters to a distinct file. ea.optimize(params=...)
    # already wrote the optimization RANGE set at <run_dir>/<expert>.<symbol>.<tf>.set
    # and that run's tester.ini references it; reusing the same name would overwrite
    # the optimize child's artifact with single-pass values that no longer match the
    # search it ran. The `winner.` prefix keeps both intact, side by side.
    winner_params = {**fixed_params, **winner["params"]}
    set_path = Path(opt["data"]["run_dir"]) / f"winner.{expert}.{symbol}.{tf}.set"
    ini_builder.write_set(set_path, [f"{k}={v}" for k, v in winner_params.items()])

    # Phase-specific run labels so OOS and FULL never collide on a second-resolution
    # run id (the same hazard stress() avoids by folding a token into the label).
    oos = _track(ea.single(expert=expert, symbol=symbol, timeframe=tf, from_date=split_day,
                           to_date=to_date, set_file=set_path, run_label=f"quant-oos-{expert}",
                           results_root=results_root, timeout=timeout))
    if not oos["ok"]:
        return {**base, "reason": "CELL_FAILED", "envelope": oos, "child_runs": child_runs}
    full = _track(ea.single(expert=expert, symbol=symbol, timeframe=tf, from_date=from_date,
                            to_date=to_date, set_file=set_path, run_label=f"quant-full-{expert}",
                            results_root=results_root, timeout=timeout))
    if not full["ok"]:
        return {**base, "reason": "CELL_FAILED", "envelope": full, "child_runs": child_runs}

    return {**base, "side": None, "set_file": str(set_path), "run_id": full["data"].get("run_id"),
            "params": winner_params, "is": winner["is"], "oos": _metrics(oos), "full": _metrics(full),
            "equity_curve": full["data"].get("equity_curve", []), "child_runs": child_runs}


def run(*, expert: str, symbols: list[str], timeframes: list[str], from_date: str,
        to_date: str, split: str, params: list[str] | None = None, mode: str = "genetic",
        min_trades: int = 300, min_pf: float = 1.0, min_is_trades: int | None = None,
        oos_min_pf: float = 1.0, rank_by: str = "full_net", per_asset: int = 2,
        modelling: str = "ohlc-1m", results_root: Path | str = "results",
        dry_run: bool = False, html: bool = True, timeout: int = 1800,
        label: str | None = None) -> dict[str, Any]:
    """Run a quant campaign and return a ``quant.v1`` envelope."""
    try:
        cells = matrix.expand(symbols, timeframes)
    except matrix.EmptyMatrix as exc:
        return fail("EMPTY_MATRIX", str(exc))
    try:
        split_day = matrix.resolve_split(from_date, to_date, split)
        is_end_day = matrix.is_end(split_day)
    except matrix.InvalidSplit as exc:
        return fail("INVALID_SPLIT", str(exc))
    try:
        param_list = matrix.parse_params(list(params or []))
    except matrix.InvalidParam as exc:
        return fail("INVALID_PARAM", str(exc))
    if rank_by not in _RANK_BY:
        return fail("INVALID_RANK_BY", "--rank-by must be one of full_net, oos_sharpe, oos_pf.")
    per_asset = max(1, per_asset)  # 0/negative is nonsensical; keep at least the top 1
    # The in-sample winner floor defaults to --min-trades: since the FULL window
    # contains the in-sample window, a winner with that many in-sample trades also
    # clears the FULL MIN_TRADES gate (no sparse pass crowned then rejected). A
    # user can decouple them (e.g. a lower floor for slower strategies).
    eff_min_is_trades = min_trades if min_is_trades is None else max(0, min_is_trades)

    matrix_field = {
        "symbols": list(dict.fromkeys(s.strip() for s in symbols if s and s.strip())),
        "timeframes": list(dict.fromkeys(t.strip() for t in timeframes if t and t.strip())),
    }

    if dry_run:
        return ok({"schema": "quant.v1", "dry_run": True, "matrix": matrix_field,
                   "from": from_date, "to": to_date, "split": split_day,
                   "cells": len(cells), "planned_launches": len(cells) * 3})

    pnames = matrix.optimized_param_names(param_list)
    fixed = matrix.fixed_params(param_list)
    all_cells: list[dict[str, Any]] = [
        _run_cell(expert=expert, symbol=symbol, tf=tf, from_date=from_date, to_date=to_date,
                  split_day=split_day, is_end_day=is_end_day, params=param_list,
                  param_names=pnames, fixed_params=fixed, mode=mode, min_pf=min_pf,
                  min_is_trades=eff_min_is_trades, modelling=modelling,
                  results_root=results_root, timeout=timeout)
        for symbol, tf in cells
    ]
    # Every attempted launch (optimize / OOS / FULL), in order, across all cells —
    # including rejected cells' partial runs — so the manifest lists every child.
    child_run_ids = [rid for c in all_cells for rid in c.get("child_runs", [])]
    for c in all_cells:
        c.pop("child_runs", None)

    assembled = [c for c in all_cells if not c.get("reason")]
    cell_rejected = [c for c in all_cells if c.get("reason")]
    graded = selection.gate_and_rank(assembled, min_trades=min_trades, oos_min_pf=oos_min_pf,
                                     rank_by=rank_by, per_asset=per_asset)
    rejected = cell_rejected + graded["rejected"]
    if not graded["ranked"] and not rejected and not graded["capped"]:
        return fail("NO_RESULTS", "No cell produced a ranked or rejected record.")

    cid = store.make_campaign_id(label or expert)
    cdir = store.campaign_dir(cid, root=results_root)
    data: dict[str, Any] = {
        "schema": "quant.v1", "campaign_id": cid, "expert": expert, "matrix": matrix_field,
        "from": from_date, "to": to_date, "split": split_day,
        "selection": {"min_trades": min_trades, "min_pf": min_pf,
                      "min_is_trades": eff_min_is_trades, "oos_min_pf": oos_min_pf,
                      "rank_by": rank_by, "per_asset": per_asset},
        "rank_caveat": graded["rank_caveat"], "ranked": graded["ranked"], "rejected": rejected,
        "capped": graded["capped"], "child_run_ids": child_run_ids,
    }
    if not graded["ranked"] and rejected and all(r.get("reason") == "NO_WINNER" for r in rejected):
        data["hint"] = ("Every cell was NO_WINNER — no optimization pass cleared the in-sample "
                        "gates (profit factor >= --min-pf and in-sample trades >= --min-is-trades). "
                        "Lower --min-pf or --min-is-trades, widen the parameter grid, or check the "
                        "EA produces enough profitable in-sample trades.")
    # Populate artifacts (paths under the actual results_root) BEFORE persisting,
    # so a reloaded manifest carries them. The manifest always exists; the report
    # only when html is on.
    artifacts: dict[str, str] = {"manifest": (cdir / "manifest.json").as_posix()}
    if html:
        report_path = cdir / "report.html"
        report_path.write_text(report.render(data), encoding="utf-8")
        artifacts["report_html"] = report_path.as_posix()
    data["artifacts"] = artifacts
    store.write_manifest(cid, data, root=results_root)
    return ok(data)
