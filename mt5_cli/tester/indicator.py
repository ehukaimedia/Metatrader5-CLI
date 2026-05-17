"""Strategy Tester visual-mode operations for custom indicators."""
from __future__ import annotations

from pathlib import Path

from mt5_cli.mql5 import discovery
from mt5_cli.reports import fail, ok

from . import cache, ini_builder, launcher


def visual(
    *,
    indicator_name: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
    results_root: Path | str = "results",
    timeout: int = 600,
) -> dict:
    """Run a visual Strategy Tester pass for a compiled custom indicator."""
    if not ini_builder.is_known_modelling(modelling):
        return fail(
            "UNKNOWN_MODELLING",
            f"Unknown modelling {modelling!r}. Known: {sorted(ini_builder._MODELLING)}",
        )

    found = discovery.get_indicator(indicator_name)
    if not found:
        return fail(
            "INDICATOR_NOT_FOUND",
            f"No indicator named {indicator_name!r}. Run `mt5 indicator list`.",
        )
    if not found["compiled"]:
        return fail(
            "INDICATOR_NOT_COMPILED",
            f"Indicator {indicator_name!r} has no .ex5. "
            f"Run `mt5 indicator compile {indicator_name}`.",
        )

    run_id = cache.make_run_id(f"ind-{indicator_name}", symbol, timeframe)
    run_path = cache.run_dir(run_id, root=results_root)
    ini_path = run_path / "tester.ini"
    ini_text = ini_builder.build_indicator_ini(
        indicator=indicator_name,
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
        modelling=modelling,
    )
    ini_builder.write_ini(ini_path, ini_text)

    launched = launcher.run(ini_path=ini_path, run_dir=run_path, timeout=timeout)
    if not launched["ok"]:
        return launched

    return ok({
        "run_id": run_id,
        "indicator": indicator_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "from": from_date,
        "to": to_date,
        "modelling": modelling,
        "run_dir": str(run_path),
    })
