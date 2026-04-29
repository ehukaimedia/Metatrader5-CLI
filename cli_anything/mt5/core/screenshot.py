"""
screenshot.py — Screen capture for the MT5 CLI.

Uses ``mss`` for monitor capture and ``pygetwindow`` (Windows-only) for
window targeting.  This module does NOT interact with MT5 internals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import mss
import mss.tools

_DEFAULT_SCREENSHOT_DIR = "~/mt5-screenshots"


def _fail(code: str, message: str, *, mt5_retcode: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": mt5_retcode}}


def _resolve_dir(directory: str | None, cfg: dict | None) -> Path:
    if directory:
        return Path(directory).expanduser()
    if cfg:
        return Path(cfg.get("screenshot_path", _DEFAULT_SCREENSHOT_DIR)).expanduser()
    return Path(_DEFAULT_SCREENSHOT_DIR).expanduser()


def _resolve_monitor(monitor: int | None, cfg: dict | None) -> int:
    if monitor is not None:
        return int(monitor)
    if cfg:
        return int(cfg.get("screenshot_monitor", 0))
    return 0


# ---------------------------------------------------------------------------
# take
# ---------------------------------------------------------------------------

def take(
    output_path: str | None = None,
    window_substring: str = "MetaTrader 5",
    monitor: int | None = None,
    cfg: dict | None = None,
) -> dict:
    """Capture the MT5 window (or full monitor) and save as PNG.

    If ``monitor`` is None, uses ``cfg["screenshot_monitor"]`` (default 0 = primary).
    When ``window_substring`` is set and pygetwindow finds a matching window, the
    capture is cropped to the window bounds.  If no window is found, falls back
    to full-monitor capture and includes ``window_matched: False`` in the data.
    """
    monitor_idx = _resolve_monitor(monitor, cfg)

    if output_path is None:
        screenshot_dir = _resolve_dir(None, cfg)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = str(screenshot_dir / f"mt5_{ts_str}.png")

    region = None
    window_matched = False
    if window_substring:
        try:
            import pygetwindow as gw  # noqa: PLC0415 (Windows-only; lazy import)
            windows = gw.getWindowsWithTitle(window_substring)
            if windows:
                win = windows[0]
                region = {
                    "left": win.left,
                    "top": win.top,
                    "width": win.width,
                    "height": win.height,
                }
                window_matched = True
        except Exception:  # noqa: BLE001 (not available on non-Windows or MT5 not open)
            pass

    with mss.mss() as sct:
        # monitor_idx mapping:
        #   0   → sct.monitors[1]  (primary; 0 is the spec's alias for "primary")
        #   n>0 → sct.monitors[n]  (mss 1-based physical index; matches Windows "Monitor n")
        # This prevents config value 2 from becoming sct.monitors[3] on a 2-monitor setup.
        mss_idx = 1 if monitor_idx == 0 else monitor_idx
        target = region if window_matched else sct.monitors[mss_idx]
        shot = sct.grab(target)
        mss.tools.to_png(shot.rgb, shot.size, output=output_path)

    data: dict = {
        "path": output_path,
        "width": shot.width,
        "height": shot.height,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not window_matched:
        data["window_matched"] = False

    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# annotate
# ---------------------------------------------------------------------------

def annotate(
    input_path: str,
    output_path: str,
    text: str,
    xy: tuple[int, int] = (10, 10),
) -> dict:
    """Add a text overlay to an existing screenshot using Pillow."""
    from PIL import Image, ImageDraw  # noqa: PLC0415 (heavy dep; lazy import)

    img = Image.open(input_path)
    draw = ImageDraw.Draw(img)
    draw.text(xy, text, fill="white")
    img.save(output_path)
    return {"ok": True, "data": {"path": output_path}}


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def list(directory: str | None = None, cfg: dict | None = None) -> dict:  # noqa: A001
    """List PNGs in the screenshots directory, sorted by mtime descending."""
    target = _resolve_dir(directory, cfg)
    if not target.exists():
        return {"ok": True, "data": []}

    pngs = sorted(target.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "ok": True,
        "data": [
            {
                "path": str(p),
                "timestamp": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                "size_kb": round(p.stat().st_size / 1024, 2),
            }
            for p in pngs
        ],
    }
