"""Run MT5's terminal64.exe in tester mode via /config:<ini>."""
import os
import shutil
import subprocess
import time
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


def is_terminal_running() -> bool:
    """Return True when a terminal64.exe process already exists.

    MT5 /config tester mode is a startup contract. When the same terminal
    is already open, Windows wakes the existing instance and the [Tester]
    block may not be applied.
    """
    if os.name != "nt":
        return False
    try:
        proc = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq terminal64.exe",
                "/FO",
                "CSV",
                "/NH",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        return False
    return "terminal64.exe" in (proc.stdout or "").lower()


def locate_terminal_data_dir(terminal: Path | None = None) -> Path | None:
    """Find the MT5 data directory paired with terminal64.exe.

    MT5 writes Strategy Tester reports relative to the terminal data
    directory, not relative to the Python process working directory. The
    data directory contains an origin.txt file with the install path.
    """
    env = os.environ.get("MT5_TERMINAL_DATA_PATH")
    if env:
        data_dir = Path(env)
        if data_dir.exists():
            return data_dir

    terminal = terminal or locate_terminal()
    origin_target = None
    if terminal is not None:
        origin_target = str(Path(terminal).parent).rstrip("\\/").lower()

    root = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    if not root.exists():
        return None

    candidates = [p for p in root.iterdir() if p.is_dir()]
    if origin_target is not None:
        for candidate in candidates:
            origin = candidate / "origin.txt"
            if not origin.exists():
                continue
            try:
                text = origin.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if text.strip().rstrip("\\/").lower() == origin_target:
                return candidate

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def prepare_report_target(
    *,
    run_id: str,
    filename: str,
    terminal_data_dir: Path | None = None,
) -> tuple[str, Path] | None:
    """Return (INI-relative report path, absolute MT5 report path).

    Per MetaQuotes startup configuration docs, Report is relative to the
    trading platform directory and its subdirectory must already exist.
    """
    data_dir = terminal_data_dir or locate_terminal_data_dir()
    if data_dir is None:
        return None
    relative = Path("reports") / "metatrader5-cli" / run_id / filename
    absolute = Path(data_dir) / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    try:
        absolute.unlink()
    except FileNotFoundError:
        pass
    return str(relative), absolute


def copy_back_artifact(source: Path | str, dest: Path | str) -> bool:
    """Copy an MT5-created artifact into the CLI run snapshot."""
    source = Path(source)
    dest = Path(dest)
    if not source.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return True


def stage_expert_parameters(
    set_file: Path | str,
    *,
    terminal_data_dir: Path | None = None,
) -> Path | None:
    """Copy an EA .set file to MQL5/Profiles/Tester for MT5 /config."""
    source = Path(set_file)
    if not source.exists():
        return None
    data_dir = terminal_data_dir or locate_terminal_data_dir()
    if data_dir is None:
        return None
    target_dir = Path(data_dir) / "MQL5" / "Profiles" / "Tester"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return target


def wait_for_artifact(path: Path | str, timeout: int, interval: float = 1.0) -> bool:
    """Wait for MT5 to finish writing an expected report artifact."""
    target = Path(path)
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_count = 0
    while time.monotonic() <= deadline:
        if target.exists():
            size = target.stat().st_size
            if size > 0 and size == last_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
                last_size = size
        time.sleep(interval)
    return target.exists() and target.stat().st_size > 0


def run(
    *,
    ini_path: Path,
    run_dir: Path,
    timeout: int = 600,
    portable: bool = False,
    allow_existing_terminal: bool = False,
) -> dict:
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
    if not allow_existing_terminal and is_terminal_running():
        return fail(
            "TERMINAL_ALREADY_RUNNING",
            "MT5 terminal64.exe is already running. Close the terminal before "
            "running Strategy Tester batch mode, or use a separate terminal "
            "installation via MT5_TERMINAL_PATH.",
        )

    cmd = [str(terminal), f"/config:{ini_path}"]
    if portable:
        cmd.append("/portable")
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
