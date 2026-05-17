"""High-level Strategy Tester operations for Expert Advisors.

This module composes filesystem-only tester primitives: run cache,
INI rendering, terminal launcher, MQL5 discovery, and result parsing.
It intentionally does not import the MetaTrader5 Python SDK.
"""
from __future__ import annotations

from pathlib import Path

from mt5_cli.mql5 import discovery
from mt5_cli.reports import fail, ok

from . import cache, ini_builder, launcher, results


_OPT_MODES = {"complete": 1, "genetic": 2, "math": 4}


def _unknown_modelling_fail(modelling: str) -> dict | None:
    if ini_builder.is_known_modelling(modelling):
        return None
    return fail(
        "UNKNOWN_MODELLING",
        f"Unknown modelling {modelling!r}. Known: {sorted(ini_builder._MODELLING)}",
    )


def _compiled_ea_or_fail(expert: str) -> tuple[dict | None, dict | None]:
    found = discovery.get_ea(expert)
    if not found:
        return None, fail("EA_NOT_FOUND", f"No EA named {expert!r}. Run `mt5 ea list`.")
    if not found["compiled"]:
        return None, fail(
            "EA_NOT_COMPILED",
            f"EA {expert!r} has no .ex5. Run `mt5 ea compile {expert}`.",
        )
    return found, None


def single(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "real-ticks",
    deposit: float = 10000,
    currency: str = "USD",
    leverage: int = 50,
    visual: bool = False,
    set_file: Path | str | None = None,
    results_root: Path | str = "results",
    timeout: int = 600,
) -> dict:
    """Run one EA backtest and return a standard result envelope."""
    modelling_err = _unknown_modelling_fail(modelling)
    if modelling_err:
        return modelling_err

    _, err = _compiled_ea_or_fail(expert)
    if err:
        return err

    run_id = cache.make_run_id(expert, symbol, timeframe)
    run_path = cache.run_dir(run_id, root=results_root)
    ini_path = run_path / "tester.ini"
    report_path = run_path / "report.html"
    journal_path = run_path / "journal.csv"

    ini_text = ini_builder.build_ea_ini(
        expert=expert,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        modelling=modelling,
        deposit=deposit,
        currency=currency,
        leverage=leverage,
        visual=visual,
        report_path=report_path,
        set_file=set_file,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launched = launcher.run(ini_path=ini_path, run_dir=run_path, timeout=timeout)
    if not launched["ok"]:
        return launched
    if not report_path.exists():
        return fail(
            "TESTER_REPORT_MISSING",
            f"Strategy Tester completed but did not write report.html in {run_path}",
            data={"run_id": run_id, "run_dir": str(run_path)},
        )

    return results.assemble(
        run_id=run_id,
        html_path=report_path,
        journal_path=journal_path,
        extra_metadata={
            "expert": expert,
            "symbol": symbol,
            "timeframe": timeframe,
            "from": from_date,
            "to": to_date,
            "modelling": modelling,
            "deposit": deposit,
            "currency": currency,
            "leverage": leverage,
            "visual": visual,
            "run_dir": str(run_path),
        },
    )


def optimize(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    mode: str = "complete",
    forward: str | None = None,
    set_file: Path | str | None = None,
    params: list[str] | dict[str, str] | None = None,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
    timeout: int = 1800,
) -> dict:
    """Run an EA optimization pass and parse optional optimization XML."""
    modelling_err = _unknown_modelling_fail(modelling)
    if modelling_err:
        return modelling_err
    if mode not in _OPT_MODES:
        return fail(
            "UNKNOWN_OPT_MODE",
            f"Unknown optimization mode {mode!r}. Known: {sorted(_OPT_MODES)}",
        )
    if params and set_file:
        return fail(
            "MT5_INVALID_PARAMS",
            "Pass either params or set_file, not both.",
        )
    if set_file and not Path(set_file).exists():
        return fail("SET_FILE_NOT_FOUND", f"Set file not found: {set_file}")
    _, err = _compiled_ea_or_fail(expert)
    if err:
        return err

    run_id = cache.make_run_id(f"opt-{mode}-{expert}", symbol, timeframe)
    run_path = cache.run_dir(run_id, root=results_root)
    ini_path = run_path / "tester.ini"
    report_path = run_path / "report.html"
    journal_path = run_path / "journal.csv"
    optimization_path = run_path / "optimization.xml"
    generated_set_path: Path | None = None
    effective_set_file = set_file
    if params:
        generated_set_path = run_path / f"{expert}.{symbol}.{timeframe}.set"
        try:
            ini_builder.write_set(generated_set_path, params)
        except ValueError as exc:
            return fail("MT5_INVALID_PARAMS", str(exc))
        effective_set_file = generated_set_path

    ini_text = ini_builder.build_ea_ini(
        expert=expert,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        modelling=modelling,
        optimization=_OPT_MODES[mode],
        forward=forward,
        report_path=report_path,
        set_file=effective_set_file,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launched = launcher.run(ini_path=ini_path, run_dir=run_path, timeout=timeout)
    if not launched["ok"]:
        return launched
    if not report_path.exists() and not optimization_path.exists():
        return fail(
            "TESTER_REPORT_MISSING",
            "Strategy Tester completed but wrote neither report.html nor optimization.xml "
            f"in {run_path}",
            data={"run_id": run_id, "run_dir": str(run_path)},
        )

    return results.assemble(
        run_id=run_id,
        html_path=report_path,
        journal_path=journal_path,
        optimization_path=optimization_path if optimization_path.exists() else None,
        extra_metadata={
            "expert": expert,
            "symbol": symbol,
            "timeframe": timeframe,
            "from": from_date,
            "to": to_date,
            "modelling": modelling,
            "mode": mode,
            "forward": forward,
            "set_file": str(effective_set_file) if effective_set_file else None,
            "generated_set_file": str(generated_set_path) if generated_set_path else None,
            "run_dir": str(run_path),
        },
    )


def scanner(
    *,
    expert: str,
    symbols: list[str],
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
) -> dict:
    """Run single-mode tests across a symbol list and aggregate envelopes."""
    per_symbol: list[dict] = []
    for symbol in symbols:
        env = single(
            expert=expert,
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
            modelling=modelling,
            results_root=results_root,
        )
        per_symbol.append({"symbol": symbol, "envelope": env})
    return ok({"expert": expert, "symbols": symbols, "per_symbol": per_symbol})


def stress(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    delays_ms: int = 50,
    results_root: Path | str = "results",
) -> dict:
    """Run a single backtest and record requested delay-stress metadata."""
    env = single(
        expert=expert,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        results_root=results_root,
    )
    if env["ok"]:
        env["data"]["stress_delay_ms"] = delays_ms
    return env
