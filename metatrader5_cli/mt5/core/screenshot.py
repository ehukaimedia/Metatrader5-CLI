"""
screenshot.py — Screen capture for the MT5 CLI.

Uses ``mss`` for monitor capture and ``pygetwindow`` (Windows-only) for
window targeting.  This module does NOT interact with MT5 internals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

import mss
import mss.tools

_DEFAULT_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "mt5-cli" / "screenshots"


def _fail(code: str, message: str, *, mt5_retcode: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": mt5_retcode}}


def _resolve_dir(directory: str | None, cfg: dict | None) -> Path:
    if directory:
        return Path(directory).expanduser()
    if cfg:
        screenshot_cfg = cfg.get("screenshot") if isinstance(cfg.get("screenshot"), dict) else {}
        configured = (
            screenshot_cfg.get("output_dir")
            or cfg.get("screenshot_output_dir")
            or cfg.get("screenshot_path")
        )
        if configured:
            return Path(configured).expanduser()
    return Path(_DEFAULT_SCREENSHOT_DIR).expanduser()


def _resolve_monitor(monitor: int | None, cfg: dict | None) -> int:
    if monitor is not None:
        return int(monitor)
    if cfg:
        return int(cfg.get("screenshot_monitor", 0))
    return 0


def _resolve_window_substring(window_substring: str, cfg: dict | None) -> str:
    if cfg and window_substring == "MT5":
        screenshot_cfg = cfg.get("screenshot") if isinstance(cfg.get("screenshot"), dict) else {}
        return screenshot_cfg.get("window_substring") or window_substring
    return window_substring


# ---------------------------------------------------------------------------
# window matching
# ---------------------------------------------------------------------------

def _window_title_matches(title: str, window_substring: str) -> bool:
    needle = (window_substring or "").lower()
    haystack = title.lower()
    if not needle:
        return False
    if needle in haystack:
        return True
    if needle == "mt5":
        return "mt5" in haystack
    return False


def _is_mt5_window_class(win) -> bool:
    hwnd = getattr(win, "_hWnd", None) or getattr(win, "hWnd", None)
    if not hwnd:
        return False
    try:
        import win32gui  # noqa: PLC0415
        return win32gui.GetClassName(hwnd).startswith("MetaQuotes::MetaTrader")
    except Exception:  # noqa: BLE001
        return False


def _find_window(window_substring: str):
    import pygetwindow as gw  # noqa: PLC0415 (Windows-only; lazy import)

    class_matches = []
    title_matches = []
    if hasattr(gw, "getAllWindows"):
        for win in gw.getAllWindows():
            title = getattr(win, "title", "") or ""
            if (window_substring or "").lower() == "mt5" and _is_mt5_window_class(win):
                class_matches.append(win)
            elif _window_title_matches(title, window_substring):
                title_matches.append(win)
        if class_matches:
            return class_matches[0]
        if title_matches:
            return title_matches[0]

    for win in gw.getWindowsWithTitle(window_substring):
        title = getattr(win, "title", "") or ""
        if _window_title_matches(title, window_substring) or window_substring in title:
            return win
    return None


# ---------------------------------------------------------------------------
# take
# ---------------------------------------------------------------------------

def take(
    output_path: str | None = None,
    window_substring: str = "MT5",
    monitor: int | None = None,
    cfg: dict | None = None,
) -> dict:
    """Capture the MT5 window (or, with window_substring="", full monitor) as PNG.

    If ``monitor`` is None, uses ``cfg["screenshot_monitor"]`` (default 0 = primary).
    When ``window_substring`` is set and pygetwindow finds a matching window, the
    capture is cropped to the window bounds. If no window is found, returns a
    fail-closed error instead of silently capturing the wrong monitor.
    """
    monitor_idx = _resolve_monitor(monitor, cfg)
    window_substring = _resolve_window_substring(window_substring, cfg)

    if output_path is None:
        screenshot_dir = _resolve_dir(None, cfg)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = str(screenshot_dir / f"mt5_{ts_str}.png")

    region = None
    window_matched = False
    window_title = None
    if window_substring:
        try:
            win = _find_window(window_substring)
            if win:
                region = {
                    "left": win.left,
                    "top": win.top,
                    "width": win.width,
                    "height": win.height,
                }
                window_matched = True
                window_title = getattr(win, "title", None)
        except Exception:  # noqa: BLE001 (not available on non-Windows or MT5 not open)
            pass

        if not window_matched:
            return _fail(
                "SCREENSHOT_WINDOW_NOT_FOUND",
                f"No window matched '{window_substring}'. Use --window '' for monitor capture.",
            )

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
    data["window_matched"] = window_matched
    if window_title:
        data["window_title"] = window_title

    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# tda
# ---------------------------------------------------------------------------

def _parse_timeframes(timeframes: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(timeframes, str):
        raw = timeframes.replace(" ", ",").split(",")
    else:
        raw = []
        for item in timeframes:
            raw.extend(str(item).replace(" ", ",").split(","))
    return [tf.strip().upper() for tf in raw if tf.strip()]


def _postprocess_image(path: Path, crop: str, max_width: int | None) -> tuple[int, int]:
    from PIL import Image  # noqa: PLC0415

    with Image.open(path) as img:
        work = img.convert("RGB")
        if crop == "chart" and work.width > 200 and work.height > 160:
            top = min(90, max(0, work.height // 8))
            bottom = max(top + 1, work.height - min(30, work.height // 20))
            work = work.crop((0, top, work.width, bottom))
        if max_width and max_width > 0 and work.width > max_width:
            height = int(work.height * (max_width / work.width))
            work = work.resize((max_width, height))
        work.save(path)
        return work.width, work.height


def tda(
    symbol: str,
    timeframes: str | list[str] | tuple[str, ...] = "D1,H4,H1,M15,M5,M1",
    output_dir: str | None = None,
    crop: str = "chart",
    max_width: int | None = 1280,
    monitor: int | None = None,
    cfg: dict | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
) -> dict:
    """Capture a visual top-down-analysis screenshot set for one symbol."""
    from metatrader5_cli.mt5.core import chart  # noqa: PLC0415

    frames: list[dict] = []
    output_root = _resolve_dir(output_dir, cfg)
    window_substring = _resolve_window_substring(window_substring, cfg)
    output_root.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in ("_", "-"))

    symbol_result = chart.symbol(symbol, window_substring=window_substring, settle_seconds=settle_seconds)
    if not symbol_result.get("ok"):
        return symbol_result

    for tf in _parse_timeframes(timeframes):
        switch_result = chart.switch_tf(tf, window_substring=window_substring, settle_seconds=settle_seconds)
        if not switch_result.get("ok"):
            return switch_result

        out_path = output_root / f"{safe_symbol}_{tf}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.png"
        shot_result = take(
            output_path=str(out_path),
            window_substring=window_substring,
            monitor=monitor,
            cfg=cfg,
        )
        if not shot_result.get("ok"):
            return shot_result

        width, height = _postprocess_image(out_path, crop, max_width)
        frame = {
            "tf": tf,
            "path": str(out_path),
            "w": width,
            "h": height,
        }
        title = switch_result.get("data", {}).get("title")
        if title:
            frame["title"] = title
        frames.append(frame)

    return {
        "ok": True,
        "data": {
            "symbol": symbol.upper(),
            "captured_at": captured_at,
            "frames": frames,
        },
    }


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
