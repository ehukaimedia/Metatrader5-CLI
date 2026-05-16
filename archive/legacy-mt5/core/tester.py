"""
tester.py - Local MetaTrader 5 Strategy Tester automation helpers.

This module launches installed MT5 desktop binaries. It does not use the
MetaTrader5 Python package and it never places live orders.
"""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time


EA_FILENAME = "EhukaiTDAEA.mq5"
EA_NAME = "EhukaiTDAEA"
DEFAULT_SYMBOLS = [
    "USDJPY",
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
    "USDCHF",
    "EURJPY",
    "GBPJPY",
    "AUDJPY",
    "EURGBP",
]


def _fail(code: str, message: str, *, data: dict | None = None) -> dict:
    result = {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}
    if data is not None:
        result["data"] = data
    return result


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def repo_ea_path() -> Path:
    return Path(__file__).resolve().parents[1] / "mql5" / "Experts" / EA_FILENAME


def strategy_magic(strategy_id: str) -> int:
    return int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16) % 80000 + 100000


def pair_magic(symbol: str, prefix: str = "ehukai-poc") -> int:
    return strategy_magic(f"{prefix}-{symbol.upper()}")


def locate_terminal(terminal: str | None = None) -> Path | None:
    if terminal:
        path = Path(terminal).expanduser()
        return path if path.exists() else None
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "MetaTrader 5" / "terminal64.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "MetaTrader 5" / "terminal64.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def locate_metaeditor(metaeditor: str | None = None) -> Path | None:
    if metaeditor:
        path = Path(metaeditor).expanduser()
        return path if path.exists() else None
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "MetaTrader 5" / "MetaEditor64.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "MetaTrader 5" / "MetaEditor64.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def terminal_candidates() -> list[Path]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    root = Path(appdata) / "MetaQuotes" / "Terminal"
    if not root.exists():
        return []
    candidates = []
    for child in root.iterdir():
        if (child / "MQL5" / "Experts").is_dir():
            candidates.append(child)
    candidates.sort(key=lambda p: (p / "MQL5" / "Experts" / EA_FILENAME).exists(), reverse=True)
    return candidates


def resolve_data_dir(data_dir: str | None = None, experts_dir: str | None = None) -> Path | None:
    if data_dir:
        path = Path(data_dir).expanduser()
        return path if path.exists() else None
    if experts_dir:
        experts = Path(experts_dir).expanduser()
        if experts.name.lower() == "experts" and experts.parent.name.lower() == "mql5":
            return experts.parent.parent
    candidates = terminal_candidates()
    return candidates[0] if candidates else None


def deploy_ea(*, data_dir: str | None = None, experts_dir: str | None = None) -> dict:
    source = repo_ea_path()
    if not source.exists():
        return _fail("TESTER_EA_NOT_FOUND", f"EA source not found: {source}")
    resolved_data = resolve_data_dir(data_dir=data_dir, experts_dir=experts_dir)
    if resolved_data is None:
        return _fail("TESTER_DATA_DIR_NOT_FOUND", "Could not resolve an MT5 terminal data directory.")
    target_dir = resolved_data / "MQL5" / "Experts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / EA_FILENAME
    shutil.copy2(source, target)
    return {"ok": True, "data": {"source": str(source), "target": str(target), "data_dir": str(resolved_data)}}


def compile_ea(
    *,
    metaeditor: str | None = None,
    data_dir: str | None = None,
    experts_dir: str | None = None,
    timeout_seconds: int = 120,
) -> dict:
    deployed = deploy_ea(data_dir=data_dir, experts_dir=experts_dir)
    if not deployed.get("ok"):
        return deployed
    editor = locate_metaeditor(metaeditor)
    if editor is None:
        return _fail("TESTER_METAEDITOR_NOT_FOUND", "Could not locate MetaEditor64.exe.", data=deployed.get("data"))

    target = Path(deployed["data"]["target"])
    log_path = repo_root() / "docs" / "backtests" / "compile" / "EhukaiTDAEA-compile.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        log_path.unlink()
    cmd = [str(editor), f"/compile:{target}", f"/log:{log_path}"]
    completed = subprocess.run(cmd, cwd=str(target.parent), timeout=timeout_seconds, capture_output=True, text=True)
    log_text = log_path.read_text(encoding="utf-16", errors="ignore") if log_path.exists() else ""
    errors = _compile_error_count(log_text)
    warnings = _compile_warning_count(log_text)
    ex5_path = target.with_suffix(".ex5")
    ok = errors == 0 and ex5_path.exists()
    data = {
        **deployed["data"],
        "metaeditor": str(editor),
        "command": cmd,
        "returncode": completed.returncode,
        "compile_log": str(log_path),
        "errors": errors,
        "warnings": warnings,
        "ex5": str(ex5_path) if ex5_path.exists() else None,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if not ok:
        return _fail("TESTER_COMPILE_FAILED", f"EA compile failed: errors={errors}, warnings={warnings}.", data=data)
    return {"ok": True, "data": data}


def _compile_error_count(log_text: str) -> int:
    for line in reversed(log_text.splitlines()):
        if " errors," in line:
            try:
                return int(line.strip().split(" errors,", 1)[0].split()[-1])
            except (ValueError, IndexError):
                return 1
    return 0


def _compile_warning_count(log_text: str) -> int:
    for line in reversed(log_text.splitlines()):
        if " warnings" in line:
            try:
                before = line.strip().split(" warnings", 1)[0]
                return int(before.split(",")[-1].strip())
            except (ValueError, IndexError):
                return 0
    return 0


def build_config(
    *,
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
    run_dir: Path,
    data_dir: Path | None = None,
    deposit: float = 10000.0,
    leverage: str = "1:50",
    model: int = 1,
    entry_mode: str = "limit",
    risk_percent: float = 0.25,
    fixed_lots: float = 0.0,
    strategy_id_prefix: str = "ehukai-poc",
    extra_inputs: dict[str, str] | None = None,
) -> Path:
    symbol = symbol.upper()
    run_dir.mkdir(parents=True, exist_ok=True)
    report_name = f"{run_dir.name}_{symbol}_{timeframe}_report"
    set_name = f"{symbol}_{timeframe}_{EA_NAME}.set"
    magic = pair_magic(symbol, strategy_id_prefix)
    input_lines = {
        "InpStrategyIdPrefix": strategy_id_prefix,
        "InpMagicOverride": str(magic),
        "InpEntryMode": "1" if entry_mode.lower() == "market" else "0",
        "InpRiskPercent": f"{risk_percent:g}",
        "InpFixedLots": f"{fixed_lots:g}",
        "InpJournalEnabled": "true",
        "InpJournalNoTrade": "true",
    }
    if extra_inputs:
        input_lines.update({str(k): str(v) for k, v in extra_inputs.items()})
    inputs = "\n".join(f"{key}={value}" for key, value in input_lines.items())
    config_text = f"""[Tester]
Expert={EA_NAME}
ExpertParameters={set_name}
Symbol={symbol}
Period={timeframe}
Model={model}
FromDate={_mt5_date(date_from)}
ToDate={_mt5_date(date_to)}
ForwardMode=0
Deposit={deposit:g}
Currency=USD
Leverage={leverage}
Optimization=0
Visual=0
Report=reports\\{report_name}
ReplaceReport=1
ShutdownTerminal=1

[Inputs]
{inputs}
"""
    ini_path = run_dir / f"{symbol}_{timeframe}_tester.ini"
    set_path = run_dir / set_name
    ini_path.write_text(config_text, encoding="utf-8")
    set_path.write_text(inputs + "\n", encoding="utf-16")
    if data_dir is not None:
        tester_profile_dir = data_dir / "MQL5" / "Profiles" / "Tester"
        tester_profile_dir.mkdir(parents=True, exist_ok=True)
        reports_dir = data_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(set_path, tester_profile_dir / set_name)
    return ini_path


def run_backtest(
    *,
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
    terminal: str | None = None,
    metaeditor: str | None = None,
    data_dir: str | None = None,
    experts_dir: str | None = None,
    output_dir: str | None = None,
    compile_first: bool = True,
    timeout_seconds: int = 900,
    entry_mode: str = "limit",
) -> dict:
    terminal_path = locate_terminal(terminal)
    if terminal_path is None:
        return _fail("TESTER_TERMINAL_NOT_FOUND", "Could not locate terminal64.exe.")

    resolved_data = resolve_data_dir(data_dir=data_dir, experts_dir=experts_dir)
    if resolved_data is None:
        return _fail("TESTER_DATA_DIR_NOT_FOUND", "Could not resolve an MT5 terminal data directory.")

    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{symbol.upper()}-{timeframe}"
    run_dir = Path(output_dir).expanduser() if output_dir else repo_root() / "docs" / "backtests" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    compile_result = None
    if compile_first:
        compile_result = compile_ea(metaeditor=metaeditor, data_dir=str(resolved_data), timeout_seconds=120)
        if not compile_result.get("ok"):
            compile_result["data"] = {**compile_result.get("data", {}), "run_dir": str(run_dir)}
            return compile_result
    else:
        deployed = deploy_ea(data_dir=str(resolved_data))
        if not deployed.get("ok"):
            return deployed

    ini_path = build_config(
        symbol=symbol,
        timeframe=timeframe,
        date_from=date_from,
        date_to=date_to,
        run_dir=run_dir,
        data_dir=resolved_data,
        entry_mode=entry_mode,
    )
    cmd = [str(terminal_path), f"/config:{ini_path}"]
    started = time.time()
    completed = subprocess.run(cmd, cwd=str(terminal_path.parent), timeout=timeout_seconds, capture_output=True, text=True)
    elapsed = round(time.time() - started, 2)
    collected = collect_artifacts(run_dir=run_dir, data_dir=resolved_data, symbol=symbol)
    summary = summarize_run(run_dir)
    data = {
        "run_dir": str(run_dir),
        "terminal": str(terminal_path),
        "data_dir": str(resolved_data),
        "command": cmd,
        "config": str(ini_path),
        "returncode": completed.returncode,
        "elapsed_seconds": elapsed,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "compile": compile_result.get("data") if compile_result else None,
        "artifacts": collected,
        "summary": summary,
    }
    if completed.returncode != 0:
        return _fail("TESTER_RUN_FAILED", f"Strategy Tester command exited {completed.returncode}.", data=data)
    if not _has_collected_artifacts(collected):
        return _fail(
            "TESTER_NO_ARTIFACTS",
            "Strategy Tester process exited successfully but produced no report or EA journal artifacts.",
            data=data,
        )
    return {"ok": True, "data": data}


def collect_manual_run(
    *,
    symbol: str,
    timeframe: str = "M5",
    data_dir: str | None = None,
    experts_dir: str | None = None,
    output_dir: str | None = None,
) -> dict:
    """Collect artifacts after a Strategy Tester run launched from the MT5 GUI."""
    resolved_data = resolve_data_dir(data_dir=data_dir, experts_dir=experts_dir)
    if resolved_data is None:
        return _fail("TESTER_DATA_DIR_NOT_FOUND", "Could not resolve an MT5 terminal data directory.")

    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{symbol.upper()}-{timeframe}-manual"
    run_dir = Path(output_dir).expanduser() if output_dir else repo_root() / "docs" / "backtests" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    collected = collect_artifacts(run_dir=run_dir, data_dir=resolved_data, symbol=symbol)
    summary = summarize_run(run_dir)
    data = {
        "run_dir": str(run_dir),
        "data_dir": str(resolved_data),
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "artifacts": collected,
        "summary": summary,
    }
    if not _has_collected_artifacts(collected):
        return _fail(
            "TESTER_NO_ARTIFACTS",
            "No Strategy Tester report or EhukaiTDAEA journal artifacts were found to collect.",
            data=data,
        )
    return {"ok": True, "data": data}


def _mt5_date(value: str) -> str:
    return value.replace("-", ".")


def collect_artifacts(*, run_dir: Path, data_dir: Path, symbol: str) -> dict:
    copied: list[str] = []
    for files_dir in _ea_file_dirs(data_dir):
        for path in files_dir.glob(f"EhukaiTDAEA_{symbol.upper()}_*.csv"):
            target = run_dir / path.name
            shutil.copy2(path, target)
            copied.append(str(target))

    report_paths: list[Path] = list(run_dir.glob("*report*"))
    reports_dir = data_dir / "reports"
    if reports_dir.exists():
        for path in reports_dir.glob(f"*{symbol.upper()}*report*"):
            target = run_dir / path.name
            if path.resolve() != target.resolve():
                shutil.copy2(path, target)
            report_paths.append(target)

    logs: list[str] = []
    for logs_dir in _tester_log_dirs(data_dir):
        for path in _latest_logs(logs_dir):
            target = run_dir / f"{logs_dir.parent.name}_{path.name}"
            shutil.copy2(path, target)
            logs.append(str(target))

    caches: list[str] = []
    cache_dir = data_dir / "Tester" / "cache"
    if cache_dir.exists():
        for path in cache_dir.glob(f"EhukaiTDAEA*{symbol.upper()}*"):
            target = run_dir / path.name
            shutil.copy2(path, target)
            caches.append(str(target))

    reports = [str(path) for path in report_paths]
    return {"journals": copied, "reports": reports, "logs": logs, "cache": caches}


def _has_collected_artifacts(collected: dict) -> bool:
    return any(collected.get(kind) for kind in ("journals", "reports", "logs", "cache"))


def _ea_file_dirs(data_dir: Path) -> list[Path]:
    dirs = [
        data_dir / "MQL5" / "Files" / "EhukaiTDAEA",
        data_dir / "MQL5" / "Files",
    ]
    for agent_dir in _tester_agent_dirs(data_dir):
        dirs.extend(
            [
                agent_dir / "MQL5" / "Files" / "EhukaiTDAEA",
                agent_dir / "MQL5" / "Files",
            ]
        )
    return _existing_unique_dirs(dirs)


def _tester_log_dirs(data_dir: Path) -> list[Path]:
    dirs = [data_dir / "Tester" / "logs"]
    dirs.extend(agent_dir / "logs" for agent_dir in _tester_agent_dirs(data_dir))
    return _existing_unique_dirs(dirs)


def _tester_agent_dirs(data_dir: Path) -> list[Path]:
    tester_root = data_dir.parent.parent / "Tester" / data_dir.name
    if not tester_root.exists():
        return []
    return [path for path in tester_root.glob("Agent-*") if path.is_dir()]


def _latest_logs(logs_dir: Path) -> list[Path]:
    logs = [path for path in logs_dir.glob("*.log") if path.is_file()]
    if not logs:
        return []
    logs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [logs[0]]


def _existing_unique_dirs(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    dirs: list[Path] = []
    for path in paths:
        if not path.exists() or not path.is_dir():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        dirs.append(path)
    return dirs


def summarize_run(run_dir: Path) -> dict:
    exits = list(_read_csvs(run_dir.glob("*_exits.csv")))
    setups = list(_read_csvs(run_dir.glob("*_setups.csv")))
    failures: dict[str, int] = {}
    for row in setups:
        reason = row.get("failure") or "none"
        failures[reason] = failures.get(reason, 0) + 1
    net = 0.0
    wins = 0
    losses = 0
    r_values: list[float] = []
    for row in exits:
        profit = _float(row.get("profit")) + _float(row.get("commission")) + _float(row.get("swap"))
        net += profit
        if profit > 0:
            wins += 1
        elif profit < 0:
            losses += 1
        if row.get("realized_r"):
            r_values.append(_float(row["realized_r"]))
    trades = wins + losses
    return {
        "setup_rows": len(setups),
        "exit_rows": len(exits),
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / trades, 4) if trades else 0.0,
        "net_profit": round(net, 2),
        "expectancy": round(net / trades, 2) if trades else 0.0,
        "avg_r": round(sum(r_values) / len(r_values), 3) if r_values else 0.0,
        "failure_modes": failures,
    }


def _read_csvs(paths) -> list[dict]:
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
            rows.extend(csv.DictReader(handle))
    return _unique_rows(rows)


def _unique_rows(rows: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        key = tuple(sorted((str(k), str(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _float(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except ValueError:
        return 0.0
