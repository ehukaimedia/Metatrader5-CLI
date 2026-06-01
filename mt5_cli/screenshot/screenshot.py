"""Screenshot primitives for the agnostic MT5 CLI.

Low-level capture primitives with no multi-timeframe orchestration and no
manifest/context writing. The agent composes its own screenshot workflows
from these primitives; the tool is hands, not strategy.

Bridge isolation: this module never touches the MT5 SDK bridge. It uses
mss for monitor / region capture, pygetwindow for window bound lookup,
PIL for annotation / post-processing, and win32gui for the DOM menu
poke. All heavy deps are imported lazily so the module imports cleanly
on hosts without them (and tests can sys.modules-mock them).

Public surface (re-exported from `mt5_cli.screenshot.__init__`):
- take(output_path=None, window_substring="MT5", monitor=None, cfg=None) -> envelope
- annotate(input_path, output_path, text, xy=(10,10)) -> envelope
- dom(symbol, output_path=None, ..., open_panel=True, close_panel=True) -> envelope
- list_screenshots(directory=None, cfg=None) -> envelope
"""
from __future__ import annotations

import ctypes
import tempfile
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

from mt5_cli.reports import fail, ok

_DEFAULT_SCREENSHOT_DIR = Path(tempfile.gettempdir()) / "mt5-cli" / "screenshots"

# Win32 message constants for DOM menu poking (keeps us off win32con).
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
MF_BYPOSITION = 0x0400
DEPTH_OF_MARKET_MENU_TEXT = "depth of market"


# ---------------------------------------------------------------------------
# cfg resolvers
# ---------------------------------------------------------------------------


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
# Window matching (pygetwindow, not win32gui - mss wants pixel bounds)
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
    import pygetwindow as gw  # noqa: PLC0415 (Windows-only; lazy)
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
    """Capture the MT5 window (or, with window_substring='', a monitor) as PNG.

    With window_substring set, the capture is cropped to the matched window
    bounds via pygetwindow. If no window matches, returns SCREENSHOT_WINDOW_NOT_FOUND
    fail-closed (no silent fallback to wrong-monitor capture).

    monitor_idx mapping (handled here to keep the cfg/CLI surface stable):
      0   -> sct.monitors[1] (primary; 0 means 'primary' in our spec)
      n>0 -> sct.monitors[n] (mss 1-based physical index, matches Windows 'Monitor n')
    """
    import mss  # noqa: PLC0415 (heavy dep; lazy)
    import mss.tools  # noqa: PLC0415

    monitor_idx = _resolve_monitor(monitor, cfg)
    window_substring = _resolve_window_substring(window_substring, cfg)

    if output_path is None:
        screenshot_dir = _resolve_dir(None, cfg)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = str(screenshot_dir / f"mt5_{ts_str}.png")
    else:
        Path(output_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

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
        except Exception:  # noqa: BLE001
            pass

        if not window_matched:
            return fail(
                "SCREENSHOT_WINDOW_NOT_FOUND",
                f"No window matched '{window_substring}'. Use window_substring='' for monitor capture.",
            )

    with mss.mss() as sct:
        mss_idx = 1 if monitor_idx == 0 else monitor_idx
        target = region if window_matched else sct.monitors[mss_idx]
        shot = sct.grab(target)
        mss.tools.to_png(shot.rgb, shot.size, output=output_path)

    data: dict = {
        "path": output_path,
        "width": shot.width,
        "height": shot.height,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "window_matched": window_matched,
    }
    if window_title:
        data["window_title"] = window_title
    return ok(data)


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
    from PIL import Image, ImageDraw  # noqa: PLC0415 (heavy dep; lazy)

    img = Image.open(input_path)
    draw = ImageDraw.Draw(img)
    draw.text(xy, text, fill="white")
    img.save(output_path)
    return ok({"path": output_path})


# ---------------------------------------------------------------------------
# Post-processing helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# DOM panel toggle helpers (inline, so chart.py stays focused on charts)
# ---------------------------------------------------------------------------


def _normalize_menu_text(text: str) -> str:
    return " ".join(text.replace("&", "").split()).split("\t", 1)[0].strip().lower()


def _menu_string(hmenu: int, index: int, flags: int) -> str:
    user32 = ctypes.windll.user32
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetMenuStringW(
        wintypes.HMENU(hmenu),
        wintypes.UINT(index),
        buffer,
        ctypes.sizeof(buffer) // ctypes.sizeof(ctypes.c_wchar),
        wintypes.UINT(flags),
    )
    return buffer.value


def _find_menu_command_id(hwnd: int, target_text: str) -> int | None:
    import win32gui  # noqa: PLC0415
    menu = win32gui.GetMenu(hwnd)
    if not menu:
        return None
    target = target_text.lower()

    def walk(hmenu: int) -> int | None:
        count = win32gui.GetMenuItemCount(hmenu)
        for index in range(count):
            text = _menu_string(hmenu, index, MF_BYPOSITION)
            if target in _normalize_menu_text(text):
                command_id = win32gui.GetMenuItemID(hmenu, index)
                if command_id != -1:
                    return int(command_id)
            submenu = win32gui.GetSubMenu(hmenu, index)
            if submenu:
                found = walk(submenu)
                if found is not None:
                    return found
        return None

    return walk(menu)


def _open_dom_panel(symbol_name: str, window_substring: str, settle_seconds: float) -> dict:
    """Send WM_COMMAND for the 'Charts > Depth Of Market' menu item."""
    import win32gui  # noqa: PLC0415

    # Use chart.find_window for window discovery (mt5_cli.chart is
    # the canonical chart-window matcher).
    from mt5_cli.chart import find_window
    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    command_id = _find_menu_command_id(match.hwnd, DEPTH_OF_MARKET_MENU_TEXT)
    if command_id is None:
        return fail(
            "CHART_MENU_ITEM_NOT_FOUND",
            "Could not find Charts > Depth Of Market in the MT5 menu.",
        )

    win32gui.PostMessage(match.hwnd, WM_COMMAND, command_id, 0)
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    refreshed = find_window(window_substring)
    title = refreshed.title if refreshed else match.title
    return ok({
        "symbol": symbol_name.upper(),
        "menu": "Charts > Depth Of Market",
        "command_id": command_id,
        "title": title,
        "hwnd": match.hwnd,
    })


def _is_dom_child_title(title: str, symbol_name: str) -> bool:
    """Return True for MT5 DOM child window titles (not normal chart titles)."""
    symbol_upper = symbol_name.upper()
    title_upper = title.upper().strip()
    if symbol_upper not in title_upper or "," not in title_upper or "[" in title_upper:
        return False
    # Common timeframe-suffixed chart titles (e.g., "USDJPY,M15") are NOT DOM windows.
    timeframe_suffixes = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN")
    return not any(title_upper == f"{symbol_upper},{tf}" for tf in timeframe_suffixes)


def _close_dom_panel(symbol_name: str, window_substring: str) -> dict:
    import win32gui  # noqa: PLC0415
    from mt5_cli.chart import find_window
    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    symbol_upper = symbol_name.upper()
    candidates: list[int] = []

    def enum_child(hwnd, _extra):
        title = win32gui.GetWindowText(hwnd) or ""
        if _is_dom_child_title(title, symbol_upper):
            candidates.append(hwnd)

    win32gui.EnumChildWindows(match.hwnd, enum_child, None)
    if not candidates:
        # No DOM child found - try menu toggle as fallback
        command_id = _find_menu_command_id(match.hwnd, DEPTH_OF_MARKET_MENU_TEXT)
        if command_id is None:
            return fail(
                "CHART_MENU_ITEM_NOT_FOUND",
                "Could not find Charts > Depth Of Market in the MT5 menu.",
            )
        win32gui.PostMessage(match.hwnd, WM_COMMAND, command_id, 0)
        return ok({
            "symbol": symbol_upper, "closed": 0, "hwnds": [],
            "parent_hwnd": match.hwnd, "method": "menu_toggle", "command_id": command_id,
        })

    for hwnd in candidates:
        win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)

    return ok({
        "symbol": symbol_upper,
        "closed": len(candidates),
        "hwnds": candidates,
        "parent_hwnd": match.hwnd,
    })


# ---------------------------------------------------------------------------
# dom
# ---------------------------------------------------------------------------


def dom(
    symbol: str,
    output_path: str | None = None,
    output_dir: str | None = None,
    crop: str = "window",
    max_width: int | None = 1280,
    monitor: int | None = None,
    cfg: dict | None = None,
    window_substring: str | None = None,
    open_panel: bool = True,
    close_panel: bool = True,
    settle_seconds: float = 0.5,
) -> dict:
    """Capture the GUI Depth of Market window for *symbol* as PNG.

    Counterpart to market.depth() (which returns structured data). This
    captures the visual GUI panel. With open_panel=True, the DOM panel is
    opened via the Charts menu, captured, then closed (if close_panel=True).
    """
    safe_symbol = "".join(ch for ch in symbol.upper() if ch.isalnum() or ch in ("_", "-"))
    target_window = window_substring or "MT5"
    if output_path is None:
        output_root = _resolve_dir(output_dir, cfg)
        output_root.mkdir(parents=True, exist_ok=True)
        output_path = str(
            output_root
            / f"{safe_symbol}_DOM_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}.png"
        )

    activate_result = None
    if open_panel:
        # Activate the symbol's chart BEFORE opening the DOM panel.
        # Without this, MT5 opens the DOM for whatever chart is currently
        # active - so dom("USDJPY") on an active EURUSD chart would
        # capture EURUSD DOM but the envelope would report symbol=USDJPY
        # (a label-vs-reality mismatch).
        from mt5_cli.chart import symbol as chart_symbol  # noqa: PLC0415
        activate_result = chart_symbol(
            symbol,
            window_substring=target_window,
            settle_seconds=settle_seconds,
        )
        if not activate_result.get("ok"):
            return activate_result

    open_result = None
    if open_panel:
        open_result = _open_dom_panel(symbol, target_window, settle_seconds)
        if not open_result.get("ok"):
            return open_result

    close_result = None
    try:
        result = take(
            output_path=output_path,
            window_substring=target_window,
            monitor=monitor,
            cfg=cfg,
        )
        if not result.get("ok"):
            return result
    finally:
        if close_panel and open_panel:
            close_result = _close_dom_panel(symbol, target_window)

    width, height = _postprocess_image(Path(output_path), crop, max_width)
    data = dict(result["data"])
    data.update({
        "symbol": symbol.upper(),
        "path": output_path,
        "w": width,
        "h": height,
        "dom_window_substring": target_window,
        "source": "gui_depth_of_market_window",
        "panel_opened": bool(open_panel),
        "panel_closed": bool(close_panel and open_panel and close_result and close_result.get("ok")),
    })
    if activate_result:
        data["activate_result"] = activate_result.get("data", {})
    if open_result:
        data["open_result"] = open_result.get("data", {})
    if close_result:
        data["close_result"] = close_result
    return ok(data)


# ---------------------------------------------------------------------------
# list_screenshots
# ---------------------------------------------------------------------------


def list_screenshots(directory: str | None = None, cfg: dict | None = None) -> dict:
    """List PNGs in the screenshots directory, newest first."""
    target = _resolve_dir(directory, cfg)
    if not target.exists():
        return ok([])

    pngs = sorted(target.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return ok([
        {
            "path": str(p),
            "timestamp": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
            "size_kb": round(p.stat().st_size / 1024, 2),
        }
        for p in pngs
    ])
