"""Generate the .ini config file MT5's terminal64.exe /config: needs.

MT5 reads the tester INI as UTF-16-LE with a BOM. Writing UTF-8 here
silently produces empty test runs (terminal64 accepts the file but the
[Tester] block goes unread). write_ini() handles the BOM correctly.

Bridge isolation: pure string + filesystem; no MT5 SDK access.
"""
from __future__ import annotations

from pathlib import Path

# MT5 Strategy Tester Model codes (per MT5 startup configuration docs):
#   0 = Every tick
#   1 = 1 minute OHLC
#   2 = Open prices only
#   3 = Math calculations
#   4 = Every tick based on real ticks
_MODELLING = {
    "every-tick": 0,
    "ohlc-1m": 1,
    "open-only": 2,
    "math": 3,
    "real-ticks": 4,
}


def _modelling_code(modelling: str) -> int:
    if modelling not in _MODELLING:
        raise ValueError(
            f"Unknown modelling {modelling!r}. Known: {sorted(_MODELLING)}"
        )
    return _MODELLING[modelling]


def is_known_modelling(modelling: str) -> bool:
    return modelling in _MODELLING


def _fmt_date(d: str) -> str:
    """`'2024-01-01'` -> `'2024.01.01'` (MT5 ini convention)."""
    return d.replace("-", ".")


def build_ea_ini(
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
    optimization: int = 0,
    forward: str | None = None,
    visual: bool = False,
    report_path: Path | str | None = None,
    set_file: Path | str | None = None,
    replace_report: bool = True,
    shutdown_terminal: bool = True,
) -> str:
    """Render an [Tester] block driving terminal64.exe to backtest an EA.

    `optimization` is the MT5 Optimization code (0 = single run, 1 =
    complete, 2 = genetic, 4 = math). `forward` is the YYYY-MM-DD date
    where forward-test starts (only meaningful with optimization > 0).
    """
    lines = [
        "[Tester]",
        f"Expert={expert}",
        f"Symbol={symbol}",
        f"Period={timeframe}",
        f"FromDate={_fmt_date(from_date)}",
        f"ToDate={_fmt_date(to_date)}",
        f"Model={_modelling_code(modelling)}",
        f"Deposit={int(deposit)}",
        f"Currency={currency}",
        f"Leverage=1:{leverage}",
        f"Optimization={optimization}",
        f"Visual={1 if visual else 0}",
        "UseLocal=1",
        "UseRemote=0",
        "UseCloud=0",
    ]
    if forward:
        lines.append("ForwardMode=1")
        lines.append(f"ForwardDate={_fmt_date(forward)}")
    if report_path:
        lines.append(f"Report={Path(report_path)}")
        lines.append(f"ReplaceReport={1 if replace_report else 0}")
    if set_file:
        lines.append(f"ExpertParameters={Path(set_file).name}")
    lines.append(f"ShutdownTerminal={1 if shutdown_terminal else 0}")
    return "\n".join(lines) + "\n"


def build_indicator_ini(
    *,
    indicator: str,
    symbol: str,
    timeframe: str,
    from_date: str,
    to_date: str,
    modelling: str = "ohlc-1m",
    shutdown_terminal: bool = False,
) -> str:
    """Render an [Tester] block driving an indicator visual test.

    Indicator tests are always visual (Visual=1) — there is no
    non-visual indicator test mode in MT5.
    """
    return "\n".join([
        "[Tester]",
        f"Indicator={indicator}",
        f"Symbol={symbol}",
        f"Period={timeframe}",
        f"FromDate={_fmt_date(from_date)}",
        f"ToDate={_fmt_date(to_date)}",
        f"Model={_modelling_code(modelling)}",
        "Visual=1",
        "UseLocal=1",
        "UseRemote=0",
        "UseCloud=0",
        f"ShutdownTerminal={1 if shutdown_terminal else 0}",
    ]) + "\n"


def write_ini(path: Path | str, content: str) -> Path:
    """Write `content` to `path` as UTF-16-LE with BOM (MT5's required encoding).

    Writing UTF-8 here looks fine to a text editor but silently makes
    terminal64 skip the [Tester] block, producing empty test runs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bom = b"\xff\xfe"
    path.write_bytes(bom + content.encode("utf-16-le"))
    return path


def _set_line(name: str, spec: str) -> str:
    if not name or "=" in name:
        raise ValueError(f"Invalid parameter name {name!r}")
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) == 1:
        if not parts[0]:
            raise ValueError(f"Parameter {name!r} is missing a value")
        return f"{name}={parts[0]}"
    if len(parts) == 4:
        value, start, step, stop = parts
        if not all((value, start, step, stop)):
            raise ValueError(f"Parameter {name!r} range must be value,start,step,stop")
        return f"{name}={value}||{start}||{step}||{stop}||Y"
    raise ValueError(
        f"Parameter {name!r} must be VALUE or VALUE,START,STEP,STOP"
    )


def render_set(params: list[str] | dict[str, str]) -> str:
    """Render EA input parameters as a tester .set file.

    Accepted specs:
    - ``Name=value`` for fixed inputs
    - ``Name=value,start,step,stop`` for optimization ranges
    """
    lines: list[str] = []
    seen: set[str] = set()
    raw_items = params.items() if isinstance(params, dict) else params
    for raw in raw_items:
        if isinstance(params, dict):
            name, spec = raw
        else:
            if "=" not in raw:
                raise ValueError(f"Parameter {raw!r} must be Name=value")
            name, spec = raw.split("=", 1)
        name = name.strip()
        if name in seen:
            raise ValueError(f"Duplicate parameter {name!r}")
        seen.add(name)
        lines.append(_set_line(name, str(spec).strip()))
    return "\n".join(lines) + ("\n" if lines else "")


def write_set(path: Path | str, params: list[str] | dict[str, str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_set(params), encoding="utf-8")
    return path
