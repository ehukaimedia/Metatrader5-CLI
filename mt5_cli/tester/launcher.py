"""Run MT5's terminal64.exe in tester mode via /config:<ini>."""
import os
import subprocess
from pathlib import Path

from mt5_cli.reports import fail, ok

_CANDIDATE_PATHS = [
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe"),
]


def locate_terminal() -> Path | None:
    """Find terminal64.exe from env first, then common Windows locations."""
    env = os.environ.get("MT5_TERMINAL_PATH")
    if env:
        terminal = Path(env)
        if terminal.exists():
            return terminal

    for terminal in _CANDIDATE_PATHS:
        if terminal.exists():
            return terminal
    return None


def run(*, ini_path: Path, run_dir: Path, timeout: int = 600) -> dict:
    """Invoke terminal64.exe with MT5 Strategy Tester config."""
    ini_path = Path(ini_path)
    run_dir = Path(run_dir)

    if not ini_path.exists():
        return fail("INI_NOT_FOUND", f"INI file not found: {ini_path}")

    terminal = locate_terminal()
    if not terminal:
        return fail(
            "TERMINAL_NOT_FOUND",
            "Could not locate terminal64.exe. Set MT5_TERMINAL_PATH.",
        )

    cmd = [str(terminal), f"/config:{ini_path}", "/portable"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return fail("TESTER_TIMEOUT", f"terminal64 did not finish in {timeout}s")

    stdout = proc.stdout[-4000:] if proc.stdout else ""
    stderr = proc.stderr[-4000:] if proc.stderr else ""
    if proc.returncode != 0:
        detail = stderr or stdout or f"terminal64 exited with code {proc.returncode}"
        return fail(
            "TESTER_FAILED",
            detail,
            data={
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "run_dir": str(run_dir),
            },
        )

    return ok(
        {
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "run_dir": str(run_dir),
        }
    )
