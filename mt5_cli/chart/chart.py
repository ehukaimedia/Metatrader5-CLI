"""Win32 chart-control primitives for the agnostic MT5 CLI.

Cherry-pick from archive/legacy-mt5/core/chart.py with TDA-flavored
orchestration removed (no `screenshot_tda` loop, no DOM panel toggle).
The agent composes its own multi-timeframe workflows from these
primitives; the tool is hands, not strategy.

This module talks to an already-running MT5 terminal by sending Win32
messages directly to its window/toolbar HWNDs. Chart UI control is
orthogonal to the MetaTrader5 SDK bridge - the bridge layer is not
referenced from here. pywin32 is imported lazily so the module can be
imported on non-Windows hosts for tests.

Public surface (re-exported from `mt5_cli.chart.__init__`):
- normalize_timeframe(tf) -> str
- parse_chart_title(title) -> tuple[str | None, str | None]
- title_has_symbol_tf(title, symbol, tf=None) -> bool
- find_window(window_substring) -> WindowMatch | None
- list_charts(window_substring="MT5") -> envelope
- current_title(window_substring="MT5", chart_id=None) -> envelope
- activate_chart(hwnd, parent_hwnd=None, settle_seconds=0.1) -> bool
- switch_tf(tf, window_substring="MT5", settle_seconds=0.5, chart_id=None) -> envelope
- symbol(symbol_name, ...) -> envelope
- ensure_chart(symbol_name, timeframe="M15", ...) -> envelope
"""
from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes
from dataclasses import dataclass

from mt5_cli.reports import fail, ok

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN")
TOOLBAR_BUTTON_INDEX = {
    "M1": 0, "M5": 1, "M15": 2, "M30": 3,
    "H1": 4, "H4": 5, "D1": 6, "W1": 7, "MN": 8,
}
TF_TITLE_ALIASES = {
    "M1": ("M1",),
    "M5": ("M5",),
    "M15": ("M15",),
    "M30": ("M30",),
    "H1": ("H1",),
    "H4": ("H4",),
    "D1": ("D1", "Daily"),
    "W1": ("W1", "Weekly"),
    "MN": ("MN", "MN1", "Monthly"),
}
TIMEFRAME_VERIFY_POLLS = 10
TIMEFRAME_VERIFY_POLL_SECONDS = 0.05

# Win32 message constants used here (avoids requiring win32con at module-import time)
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_CLOSE = 0x0010
WM_MDIACTIVATE = 0x0222
WM_MDIGETACTIVE = 0x0229
VK_RETURN = 0x0D
VK_END = 0x23
SW_RESTORE = 9
TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TB_PRESSBUTTON = 0x0403

# Process / memory access flags for the toolbar-button cross-process read
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


@dataclass(frozen=True)
class WindowMatch:
    hwnd: int
    title: str


@dataclass(frozen=True)
class ChartWindow:
    hwnd: int
    title: str
    symbol: str | None = None
    timeframe: str | None = None
    class_name: str = ""
    active: bool = False


def _win32():
    """Lazily import pywin32 modules. Raises RuntimeError if unavailable."""
    try:
        import win32con  # noqa: PLC0415
        import win32gui  # noqa: PLC0415
        import win32process  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pywin32 is required for chart controls on Windows.") from exc
    return win32gui, win32con, win32process


# ---------------------------------------------------------------------------
# Pure title-parsing helpers (no Win32 needed)
# ---------------------------------------------------------------------------


def normalize_timeframe(tf: str) -> str:
    value = tf.upper()
    if value == "MN1":
        value = "MN"
    if value not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return value


_BRACKET_CHART_RE = re.compile(
    r"\[([A-Z0-9._/#-]+)(?:,([A-Z0-9]+|Daily|Weekly|Monthly))?\]",
    re.IGNORECASE,
)
_PLAIN_CHART_RE = re.compile(
    r"^\s*([A-Z0-9._/#-]+)\s*,\s*([A-Z0-9]+|Daily|Weekly|Monthly)\s*$",
    re.IGNORECASE,
)


def _normalize_title_timeframe(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().upper()
    for normalized, aliases in TF_TITLE_ALIASES.items():
        if raw in {alias.upper() for alias in aliases}:
            return normalized
    return None


def parse_chart_title(title: str) -> tuple[str | None, str | None]:
    """Extract (symbol, timeframe) from MT5 child or title-bar text."""
    bracket = _BRACKET_CHART_RE.search(title or "")
    if bracket:
        return bracket.group(1).upper(), _normalize_title_timeframe(bracket.group(2))

    plain = _PLAIN_CHART_RE.match(title or "")
    if plain:
        timeframe = _normalize_title_timeframe(plain.group(2))
        if timeframe:
            return plain.group(1).upper(), timeframe

    return None, None


def title_has_symbol_tf(title: str, symbol_name: str, tf: str | None = None) -> bool:
    title_upper = title.upper()
    parsed_symbol, parsed_tf = parse_chart_title(title)
    symbol_upper = symbol_name.upper()
    if symbol_upper:
        if parsed_symbol:
            if parsed_symbol.upper() != symbol_upper:
                return False
        elif symbol_upper not in title_upper:
            return False
    if tf is None:
        return True
    normalized = normalize_timeframe(tf)
    if parsed_tf:
        return parsed_tf == normalized
    return any(
        re.search(rf"(?<![A-Z0-9]){re.escape(alias.upper())}(?![A-Z0-9])", title_upper)
        for alias in TF_TITLE_ALIASES[normalized]
    )


# ---------------------------------------------------------------------------
# Window / chart enumeration
# ---------------------------------------------------------------------------


def _title_matches(title: str, window_substring: str) -> bool:
    needle = (window_substring or "").lower()
    haystack = title.lower()
    if not needle:
        return True
    if needle in haystack:
        return True
    if needle == "mt5":
        return "mt5" in haystack
    return False


def _is_mt5_window_class(hwnd: int) -> bool:
    try:
        win32gui, _, _ = _win32()
        return win32gui.GetClassName(hwnd).startswith("MetaQuotes::MetaTrader")
    except Exception:  # noqa: BLE001
        return False


def find_window(window_substring: str = "MT5") -> WindowMatch | None:
    """Find the MT5 top-level window by title substring or class match."""
    win32gui, _, _ = _win32()
    class_matches: list[WindowMatch] = []
    title_matches: list[WindowMatch] = []

    def enum_cb(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        match = WindowMatch(hwnd=hwnd, title=title)
        if (window_substring or "").lower() == "mt5" and _is_mt5_window_class(hwnd):
            class_matches.append(match)
        elif _title_matches(title, window_substring):
            title_matches.append(match)

    win32gui.EnumWindows(enum_cb, None)
    matches = class_matches or title_matches
    return matches[0] if matches else None


def _is_chart_child_class(class_name: str) -> bool:
    lowered = (class_name or "").lower()
    return (
        lowered.startswith("afxframeorview")
        or lowered.startswith("afx:")
        or lowered in {"mdichild", "metatrader::chart"}
    )


def _find_mdi_client(parent_hwnd: int) -> int | None:
    win32gui, _, _ = _win32()
    clients: list[int] = []

    def enum_child(hwnd, _extra):
        if win32gui.GetClassName(hwnd) == "MDIClient":
            clients.append(hwnd)
            return False
        return True

    win32gui.EnumChildWindows(parent_hwnd, enum_child, None)
    return clients[0] if clients else None


def _is_descendant(parent_hwnd: int, child_hwnd: int) -> bool:
    if not parent_hwnd or not child_hwnd:
        return False
    win32gui, _, _ = _win32()
    hwnd = child_hwnd
    while hwnd:
        if hwnd == parent_hwnd:
            return True
        hwnd = win32gui.GetParent(hwnd)
    return False


def _active_chart_hwnd(parent_hwnd: int) -> int | None:
    win32gui, _, _ = _win32()
    mdi_client = _find_mdi_client(parent_hwnd)
    if mdi_client:
        try:
            active = int(win32gui.SendMessage(mdi_client, WM_MDIGETACTIVE, 0, 0))
            if active:
                return active
        except Exception:  # noqa: BLE001
            pass

    try:
        focus = win32gui.GetFocus()
    except Exception:  # noqa: BLE001
        focus = 0
    if focus and _is_descendant(parent_hwnd, focus):
        return focus

    try:
        foreground = win32gui.GetForegroundWindow()
        if foreground and _is_descendant(parent_hwnd, foreground):
            return foreground
    except Exception:  # noqa: BLE001
        pass
    return None


def enumerate_chart_children(parent_hwnd: int) -> list[ChartWindow]:
    """Return visible MT5 child chart windows under a terminal HWND."""
    win32gui, _, _ = _win32()
    active_hwnd = _active_chart_hwnd(parent_hwnd)
    charts: list[ChartWindow] = []
    seen: set[int] = set()

    def enum_child(hwnd, _extra):
        if hwnd in seen or not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd) or ""
        class_name = win32gui.GetClassName(hwnd) or ""
        parsed_symbol, timeframe = parse_chart_title(title)
        if title and parsed_symbol and _is_chart_child_class(class_name):
            seen.add(hwnd)
            charts.append(
                ChartWindow(
                    hwnd=hwnd,
                    title=title,
                    symbol=parsed_symbol,
                    timeframe=timeframe,
                    class_name=class_name,
                    active=bool(
                        active_hwnd
                        and (hwnd == active_hwnd or _is_descendant(hwnd, active_hwnd))
                    ),
                )
            )

    win32gui.EnumChildWindows(parent_hwnd, enum_child, None)
    # If the active hwnd is a descendant of one of the chart hwnds, mark that chart active.
    if active_hwnd and all(not chart.active for chart in charts):
        for index, chart_window in enumerate(charts):
            if _is_descendant(chart_window.hwnd, active_hwnd):
                charts[index] = ChartWindow(**{**chart_window.__dict__, "active": True})
                break
    return charts


def _chart_payload(chart_window: ChartWindow) -> dict:
    return {
        "hwnd": chart_window.hwnd,
        "chart_id": chart_window.hwnd,
        "title": chart_window.title,
        "symbol": chart_window.symbol,
        "timeframe": chart_window.timeframe,
        "class_name": chart_window.class_name,
        "active": chart_window.active,
    }


def _charts_snapshot(parent_hwnd: int) -> list[dict]:
    return [_chart_payload(c) for c in enumerate_chart_children(parent_hwnd)]


def _format_detected_charts(charts: list[ChartWindow] | list[dict]) -> str:
    if not charts:
        return "none"
    parts = []
    for chart_window in charts:
        if isinstance(chart_window, dict):
            hwnd = chart_window.get("hwnd")
            sym = chart_window.get("symbol")
            tf = chart_window.get("timeframe")
            title = chart_window.get("title")
        else:
            hwnd = chart_window.hwnd
            sym = chart_window.symbol
            tf = chart_window.timeframe
            title = chart_window.title
        label = sym or "unknown"
        if tf:
            label = f"{label},{tf}"
        parts.append(f"{hwnd}:{label} ({title})")
    return "; ".join(parts)


def _active_or_first_chart(parent_hwnd: int, *, chart_id: int | None = None) -> ChartWindow | None:
    charts = enumerate_chart_children(parent_hwnd)
    if chart_id is not None:
        return next((c for c in charts if c.hwnd == chart_id), None)
    return next((c for c in charts if c.active), charts[0] if charts else None)


def _child_chart_id_from_result(result: dict, requested_chart_id: int | None) -> int | None:
    if requested_chart_id is not None:
        return requested_chart_id
    data = result.get("data", {}) if isinstance(result, dict) else {}
    hwnd = data.get("hwnd")
    parent_hwnd = data.get("parent_hwnd")
    if hwnd and hwnd != parent_hwnd:
        return hwnd
    return None


# ---------------------------------------------------------------------------
# activate_chart
# ---------------------------------------------------------------------------


def activate_chart(
    hwnd: int,
    parent_hwnd: int | None = None,
    settle_seconds: float = 0.1,
) -> bool:
    """Activate a chart without disturbing the MT5 MDI tile layout."""
    win32gui, _, _ = _win32()
    if parent_hwnd:
        mdi_client = _find_mdi_client(parent_hwnd)
        if mdi_client:
            try:
                win32gui.SetForegroundWindow(parent_hwnd)
            except Exception:  # noqa: BLE001
                pass
            try:
                win32gui.SendMessage(mdi_client, WM_MDIACTIVATE, hwnd, 0)
                if settle_seconds > 0:
                    time.sleep(settle_seconds)
                return True
            except Exception:  # noqa: BLE001
                return False

    target_hwnd = parent_hwnd or hwnd
    try:
        win32gui.ShowWindow(target_hwnd, SW_RESTORE)
    except Exception:  # noqa: BLE001
        pass
    try:
        win32gui.BringWindowToTop(target_hwnd)
    except Exception:  # noqa: BLE001
        pass
    try:
        win32gui.SetForegroundWindow(target_hwnd)
    except Exception:  # noqa: BLE001
        pass
    try:
        if target_hwnd != hwnd:
            win32gui.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    return True


# ---------------------------------------------------------------------------
# list_charts / current_title (envelope-returning)
# ---------------------------------------------------------------------------


def list_charts(window_substring: str = "MT5") -> dict:
    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")
    charts = _charts_snapshot(match.hwnd)
    for chart_window in charts:
        chart_window["parent_hwnd"] = match.hwnd
        chart_window["parent_title"] = match.title
    return ok(charts)


def current_title(window_substring: str = "MT5", chart_id: int | None = None) -> dict:
    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")
    try:
        chart_window = _active_or_first_chart(match.hwnd, chart_id=chart_id)
        detected_charts = (
            enumerate_chart_children(match.hwnd)
            if chart_id is not None and chart_window is None
            else []
        )
    except Exception:  # noqa: BLE001
        chart_window = None
        detected_charts = []
    if chart_id is not None and chart_window is None:
        return fail(
            "CHART_ID_NOT_FOUND",
            f"No MT5 child chart matched hwnd {chart_id}. Detected charts: "
            f"{_format_detected_charts(detected_charts)}",
        )
    if chart_window:
        return ok({
            "hwnd": chart_window.hwnd,
            "title": chart_window.title,
            "symbol": chart_window.symbol,
            "timeframe": chart_window.timeframe,
            "parent_hwnd": match.hwnd,
            "parent_title": match.title,
        })
    parsed_symbol, parsed_tf = parse_chart_title(match.title)
    return ok({
        "hwnd": match.hwnd,
        "title": match.title,
        "symbol": parsed_symbol,
        "timeframe": parsed_tf,
        "parent_hwnd": match.hwnd,
        "parent_title": match.title,
    })


# ---------------------------------------------------------------------------
# Toolbar plumbing for switch_tf (cross-process memory read)
# ---------------------------------------------------------------------------


def _wait_for_timeframe_title(
    window_substring: str,
    fallback_title: str,
    tf: str,
    *,
    chart_id: int | None = None,
    attempts: int = TIMEFRAME_VERIFY_POLLS,
    poll_seconds: float = TIMEFRAME_VERIFY_POLL_SECONDS,
) -> tuple[bool, str]:
    """Poll the active child chart title until it reflects the requested timeframe."""
    title = fallback_title
    for attempt in range(max(1, attempts)):
        if poll_seconds > 0 and attempt > 0:
            time.sleep(poll_seconds)
        refreshed = current_title(window_substring, chart_id=chart_id)
        title = refreshed.get("data", {}).get("title", title) if refreshed.get("ok") else title
        if title_has_symbol_tf(title, "", tf):
            return True, title
    return False, title


def _find_period_toolbar(mt5_hwnd: int) -> int | None:
    win32gui, _, _ = _win32()
    toolbars: list[int] = []

    def enum_child(hwnd, _extra):
        if win32gui.GetClassName(hwnd) != "ToolbarWindow32":
            return
        try:
            count = win32gui.SendMessage(hwnd, TB_BUTTONCOUNT, 0, 0)
        except Exception:  # noqa: BLE001
            count = 0
        if count == 9:
            toolbars.append(hwnd)

    win32gui.EnumChildWindows(mt5_hwnd, enum_child, None)
    return toolbars[0] if toolbars else None


class _TBBUTTON(ctypes.Structure):
    _fields_ = [
        ("iBitmap", ctypes.c_int),
        ("idCommand", ctypes.c_int),
        ("fsState", ctypes.c_ubyte),
        ("fsStyle", ctypes.c_ubyte),
        ("bReserved", ctypes.c_ubyte * (6 if ctypes.sizeof(ctypes.c_void_p) == 8 else 2)),
        ("dwData", ctypes.c_void_p),
        ("iString", ctypes.c_void_p),
    ]


def _toolbar_button_id(toolbar_hwnd: int, index: int) -> int | None:
    """Read the toolbar button's idCommand from the MT5 process's memory."""
    win32gui, _, win32process = _win32()
    _thread_id, process_id = win32process.GetWindowThreadProcessId(toolbar_hwnd)
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.VirtualAllocEx.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
    ]
    kernel32.VirtualAllocEx.restype = wintypes.LPVOID
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.VirtualFreeEx.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD,
    ]
    kernel32.VirtualFreeEx.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
        False,
        process_id,
    )
    if not process:
        return None

    remote = None
    try:
        remote = kernel32.VirtualAllocEx(
            process, None, ctypes.sizeof(_TBBUTTON), MEM_COMMIT, PAGE_READWRITE,
        )
        if not remote:
            return None
        ok_msg = win32gui.SendMessage(toolbar_hwnd, TB_GETBUTTON, index, int(remote))
        if not ok_msg:
            return None
        local = _TBBUTTON()
        bytes_read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            process, remote, ctypes.byref(local), ctypes.sizeof(local), ctypes.byref(bytes_read),
        ):
            return None
        return int(local.idCommand)
    finally:
        if remote:
            kernel32.VirtualFreeEx(process, remote, 0, MEM_RELEASE)
        kernel32.CloseHandle(process)


def _click_toolbar_button(mt5_hwnd: int, toolbar_hwnd: int, tf: str) -> bool:
    win32gui, _, _ = _win32()
    button_id = _toolbar_button_id(toolbar_hwnd, TOOLBAR_BUTTON_INDEX[tf])
    if button_id is None:
        return False
    win32gui.SendMessage(toolbar_hwnd, TB_PRESSBUTTON, button_id, 1)
    time.sleep(0.05)
    win32gui.PostMessage(mt5_hwnd, WM_COMMAND, button_id, toolbar_hwnd)
    time.sleep(0.05)
    win32gui.SendMessage(toolbar_hwnd, TB_PRESSBUTTON, button_id, 0)
    return True


def _press_key(hwnd: int, vk: int) -> None:
    win32gui, _, _ = _win32()
    win32gui.PostMessage(hwnd, WM_KEYDOWN, vk, 0)
    time.sleep(0.03)
    win32gui.PostMessage(hwnd, WM_KEYUP, vk, 0)


def _send_text(hwnd: int, text: str) -> None:
    win32gui, _, _ = _win32()
    for ch in text:
        win32gui.PostMessage(hwnd, WM_CHAR, ord(ch), 0)
        time.sleep(0.01)
    _press_key(hwnd, VK_RETURN)


# ---------------------------------------------------------------------------
# switch_tf / symbol / ensure_chart (top-level primitives)
# ---------------------------------------------------------------------------


def switch_tf(
    tf: str,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    chart_id: int | None = None,
) -> dict:
    """Switch the active chart timeframe through MT5's period toolbar."""
    try:
        normalized = normalize_timeframe(tf)
    except ValueError as exc:
        return fail("CHART_INVALID_TIMEFRAME", str(exc))

    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    target_chart = None
    try:
        target_chart = _active_or_first_chart(match.hwnd, chart_id=chart_id)
    except Exception:  # noqa: BLE001
        target_chart = None
    if chart_id is not None and target_chart is None:
        try:
            detected_charts = enumerate_chart_children(match.hwnd)
        except Exception:  # noqa: BLE001
            detected_charts = []
        return fail(
            "CHART_ID_NOT_FOUND",
            f"No MT5 child chart matched hwnd {chart_id}. Detected charts: "
            f"{_format_detected_charts(detected_charts)}",
        )
    if target_chart:
        activate_chart(target_chart.hwnd, match.hwnd, settle_seconds=0)

    toolbar = _find_period_toolbar(match.hwnd)
    if not toolbar:
        return fail("CHART_TOOLBAR_NOT_FOUND", "Could not find the MT5 period toolbar.")

    if not _click_toolbar_button(match.hwnd, toolbar, normalized):
        return fail(
            "CHART_TOOLBAR_BUTTON_NOT_FOUND",
            f"Could not resolve toolbar button for {normalized}.",
        )
    _press_key(match.hwnd, VK_END)
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    time.sleep(TIMEFRAME_VERIFY_POLL_SECONDS)
    fallback_title = target_chart.title if target_chart else match.title
    verified, title = _wait_for_timeframe_title(
        window_substring,
        fallback_title,
        normalized,
        chart_id=target_chart.hwnd if target_chart else chart_id,
    )
    if not verified:
        try:
            detected_charts = enumerate_chart_children(match.hwnd)
        except Exception:  # noqa: BLE001
            detected_charts = []
        return fail(
            "CHART_TIMEFRAME_VERIFY_FAILED",
            f"MT5 active child title did not show timeframe {normalized}: {title}. "
            f"Detected charts: {_format_detected_charts(detected_charts)}",
        )

    return ok({
        "timeframe": normalized,
        "title": title,
        "hwnd": target_chart.hwnd if target_chart else match.hwnd,
        "parent_hwnd": match.hwnd,
    })


def symbol(
    symbol_name: str,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    chart_id: int | None = None,
) -> dict:
    """Activate or switch a chart symbol; verify via the active child title."""
    symbol_name = symbol_name.upper()
    match = find_window(window_substring)
    if not match:
        return fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    try:
        charts = enumerate_chart_children(match.hwnd)
    except Exception:  # noqa: BLE001
        charts = []

    target_chart = None
    activated_existing = False
    if chart_id is not None:
        target_chart = next((c for c in charts if c.hwnd == chart_id), None)
        if target_chart is None:
            return fail(
                "CHART_ID_NOT_FOUND",
                f"No MT5 child chart matched hwnd {chart_id}. Detected charts: "
                f"{_format_detected_charts(charts)}",
            )
    else:
        target_chart = next(
            (c for c in charts if c.symbol and c.symbol.upper() == symbol_name),
            None,
        )
        activated_existing = target_chart is not None
        if target_chart is None:
            target_chart = next((c for c in charts if c.active), charts[0] if charts else None)

    if target_chart:
        activate_chart(target_chart.hwnd, match.hwnd, settle_seconds=0)
        title = target_chart.title
    else:
        title = match.title

    if not target_chart or not target_chart.symbol or target_chart.symbol.upper() != symbol_name:
        input_hwnd = target_chart.hwnd if target_chart else match.hwnd
        _send_text(input_hwnd, symbol_name)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        refreshed = current_title(
            window_substring,
            chart_id=input_hwnd if target_chart else chart_id,
        )
        title = refreshed.get("data", {}).get("title", title) if refreshed.get("ok") else title

    if not title_has_symbol_tf(title, symbol_name):
        chart_list = list_charts(window_substring)
        detected_charts = chart_list.get("data", []) if chart_list.get("ok") else charts
        return fail(
            "CHART_SYMBOL_VERIFY_FAILED",
            f"MT5 active child title did not show symbol {symbol_name}: {title}. "
            f"Detected charts: {_format_detected_charts(detected_charts)}",
        )

    current = current_title(
        window_substring,
        chart_id=target_chart.hwnd if target_chart else chart_id,
    )
    current_data = current.get("data", {}) if current.get("ok") else {}
    return ok({
        "symbol": symbol_name,
        "title": current_data.get("title", title),
        "hwnd": current_data.get("hwnd", target_chart.hwnd if target_chart else match.hwnd),
        "parent_hwnd": match.hwnd,
        "activated_existing": activated_existing,
    })


def ensure_chart(
    symbol_name: str,
    timeframe: str | None = "M15",
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    chart_id: int | None = None,
) -> dict:
    """Ensure a chart for `symbol_name` (and optional timeframe) is active.

    Behavior:
      1. If a chart already exists for the symbol → activate it via
         symbol() (no destructive symbol-typing).
      2. If no chart exists for the symbol → open a new one via
         new_chart(symbol_name, timeframe=timeframe). This is additive:
         the user's other charts are preserved.

    The pre-upgrade implementation (before the new_chart primitive
    existed) called symbol() which would TYPE the symbol into the
    currently-active chart, OVERWRITING that chart's symbol. That was
    destructive - an agent calling ensure_chart("USDJPY") could
    silently destroy a EURUSD chart the user wanted to keep. The new
    behavior preserves existing charts.

    If `chart_id` is given, the activate-existing branch is forced
    (the caller is naming a specific MDI child to operate on). The
    new-chart branch is skipped because a chart_id implies the chart
    already exists.
    """
    normalized_timeframe = None
    if timeframe and str(timeframe).lower() not in {"none", "off", "false"}:
        try:
            normalized_timeframe = normalize_timeframe(str(timeframe))
        except ValueError as exc:
            return fail("CHART_INVALID_TIMEFRAME", str(exc))

    # Decide which branch: activate-existing vs open-new.
    # When chart_id is supplied, the caller has named a specific MDI
    # child - treat that as "use existing", skip the lookup.
    should_open_new = False
    if chart_id is None:
        match = find_window(window_substring)
        if match:
            try:
                existing_charts = enumerate_chart_children(match.hwnd)
            except Exception:  # noqa: BLE001
                existing_charts = []
            symbol_upper = symbol_name.upper()
            already_exists = any(
                c.symbol and c.symbol.upper() == symbol_upper
                for c in existing_charts
            )
            should_open_new = not already_exists

    if should_open_new:
        # Lazy import to avoid the chart.py <-> new_chart.py cycle.
        from mt5_cli.chart.new_chart import new_chart  # noqa: PLC0415
        new_result = new_chart(
            symbol_name,
            timeframe=normalized_timeframe,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
        )
        if not new_result.get("ok"):
            return new_result
        # new_chart's envelope already contains symbol + timeframe + hwnd
        # in the shape ensure_chart promises.
        return ok({
            "symbol": symbol_name.upper(),
            "timeframe": normalized_timeframe,
            "title": new_result.get("data", {}).get("menu_path"),
            "hwnd": new_result.get("data", {}).get("hwnd"),
            "parent_hwnd": new_result.get("data", {}).get("parent_hwnd"),
            "activated_existing": False,
            "opened_new": True,
        })

    # Activate-existing branch (chart_id supplied OR a chart already
    # exists for this symbol).
    symbol_result = symbol(
        symbol_name,
        window_substring=window_substring,
        settle_seconds=settle_seconds,
        chart_id=chart_id,
    )
    if not symbol_result.get("ok"):
        return symbol_result
    target_chart_id = _child_chart_id_from_result(symbol_result, chart_id)

    if normalized_timeframe:
        tf_result = switch_tf(
            normalized_timeframe,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
            chart_id=target_chart_id,
        )
        if not tf_result.get("ok"):
            return tf_result

    title_result = current_title(window_substring, chart_id=target_chart_id)
    title = title_result.get("data", {}).get("title", symbol_result.get("data", {}).get("title"))
    if not title_has_symbol_tf(title or "", symbol_name, normalized_timeframe):
        chart_list = list_charts(window_substring)
        detected_charts = chart_list.get("data", []) if chart_list.get("ok") else []
        return fail(
            "CHART_VERIFY_FAILED",
            f"MT5 title did not show {symbol_name.upper()}"
            + (f",{normalized_timeframe}" if normalized_timeframe else "")
            + f": {title}. Detected charts: {_format_detected_charts(detected_charts)}",
        )

    return ok({
        "symbol": symbol_name.upper(),
        "timeframe": normalized_timeframe,
        "title": title,
        "hwnd": title_result.get("data", {}).get("hwnd", symbol_result.get("data", {}).get("hwnd")),
        "parent_hwnd": title_result.get("data", {}).get("parent_hwnd"),
        "activated_existing": bool(symbol_result.get("data", {}).get("activated_existing")),
        "opened_new": False,
    })


# ---------------------------------------------------------------------------
# cycle_chart — sugar over list_charts + activate_chart (next/prev)
# ---------------------------------------------------------------------------


def cycle_chart(
    direction: str = "next",
    window_substring: str = "MT5",
    settle_seconds: float = 0.1,
) -> dict:
    """Activate the next (or previous) chart in MDI tab order.

    Equivalent to clicking the next chart tab at the bottom of the MT5
    window. Wraps around: from the last chart, "next" returns to the
    first; from the first chart, "prev" returns to the last.

    Args:
        direction: "next" or "prev" (case-insensitive).
        window_substring: MT5 window matcher (default "MT5").
        settle_seconds: Delay after WM_MDIACTIVATE before returning.

    Returns ok({hwnd, title, symbol, timeframe, parent_hwnd, direction,
    cycled_from}) or fail envelope:
        CHART_INVALID_DIRECTION    direction not in {"next", "prev"}
        CHART_WINDOW_NOT_FOUND     no MT5 top-level window matched
        CHART_NO_CHARTS_OPEN       zero chart children to cycle through
        CHART_ONLY_ONE_OPEN        single chart - cycling is a no-op
    """
    direction_lower = direction.lower()
    if direction_lower not in {"next", "prev"}:
        return fail(
            "CHART_INVALID_DIRECTION",
            f"direction must be 'next' or 'prev', got {direction!r}.",
        )

    match = find_window(window_substring)
    if not match:
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"No MT5 window matched {window_substring!r}.",
        )

    try:
        charts = enumerate_chart_children(match.hwnd)
    except Exception as exc:  # noqa: BLE001
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"Could not enumerate chart children: {exc!r}",
        )

    if not charts:
        return fail(
            "CHART_NO_CHARTS_OPEN",
            "No MT5 chart windows are open. Use chart.new_chart(symbol) "
            "to open one before cycling.",
        )
    if len(charts) == 1:
        return fail(
            "CHART_ONLY_ONE_OPEN",
            "Only one chart is open; cycling is a no-op. Open additional "
            "charts via chart.new_chart(...) first.",
        )

    # Find the currently-active chart's index in the MDI order.
    active_index = None
    for i, chart_window in enumerate(charts):
        if chart_window.active:
            active_index = i
            break
    if active_index is None:
        # No chart is marked active - default to index 0 so "next" goes
        # to index 1 and "prev" wraps to the last chart.
        active_index = 0

    n = len(charts)
    if direction_lower == "next":
        target_index = (active_index + 1) % n
    else:
        target_index = (active_index - 1) % n

    target = charts[target_index]
    activate_chart(target.hwnd, match.hwnd, settle_seconds=settle_seconds)

    return ok({
        "hwnd": target.hwnd,
        "title": target.title,
        "symbol": target.symbol,
        "timeframe": target.timeframe,
        "parent_hwnd": match.hwnd,
        "direction": direction_lower,
        "cycled_from": charts[active_index].hwnd,
    })


# ---------------------------------------------------------------------------
# close_chart — WM_CLOSE on a chart child window
# ---------------------------------------------------------------------------


def close_chart(
    chart_id: int,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
) -> dict:
    """Close an MT5 chart by posting WM_CLOSE to its child HWND.

    Args:
        chart_id: The MDI child HWND of the chart to close (from
            list_charts() or any function returning chart_id).
        window_substring: MT5 window matcher (default "MT5").
        settle_seconds: Delay before verifying the chart is gone.

    Returns ok({hwnd, parent_hwnd, closed=True}) on success, or:
        CHART_WINDOW_NOT_FOUND      no MT5 top-level window matched
        CHART_ID_NOT_FOUND          chart_id is not an MDI child of the
                                    MT5 window (already closed, or wrong
                                    parent)
        CHART_CLOSE_VERIFY_FAILED   WM_CLOSE posted but the chart hwnd
                                    is still present after settle (MT5
                                    may have shown a confirmation dialog;
                                    the agent should screenshot to check)

    MT5 may show a "Save chart profile?" confirmation dialog when
    closing the last chart of a profile. If that happens, the chart
    won't actually close on its own. Callers can post Enter to confirm
    or check the result via screenshot.take().
    """
    import win32gui  # noqa: PLC0415

    match = find_window(window_substring)
    if not match:
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"No MT5 window matched {window_substring!r}.",
        )

    # Verify the chart_id is currently an MDI child of this MT5 window.
    try:
        before_charts = enumerate_chart_children(match.hwnd)
    except Exception as exc:  # noqa: BLE001
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"Could not enumerate chart children: {exc!r}",
        )
    before_hwnds = {c.hwnd for c in before_charts}
    if chart_id not in before_hwnds:
        return fail(
            "CHART_ID_NOT_FOUND",
            f"chart_id {chart_id} is not an open MDI child of the MT5 window. "
            f"Detected charts: {_format_detected_charts(before_charts)}",
        )

    win32gui.PostMessage(chart_id, WM_CLOSE, 0, 0)
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    # Verify the chart is actually gone (MT5 may have shown a save-profile
    # confirmation dialog and kept the chart open).
    try:
        after_charts = enumerate_chart_children(match.hwnd)
    except Exception:  # noqa: BLE001
        after_charts = []
    after_hwnds = {c.hwnd for c in after_charts}
    if chart_id in after_hwnds:
        return fail(
            "CHART_CLOSE_VERIFY_FAILED",
            f"Posted WM_CLOSE to chart_id {chart_id} but it is still open "
            "after settle. MT5 may be showing a confirmation dialog; check "
            "via screenshot.take() and dismiss manually.",
        )

    return ok({
        "hwnd": chart_id,
        "parent_hwnd": match.hwnd,
        "closed": True,
    })
