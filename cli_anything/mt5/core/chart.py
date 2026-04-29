"""
chart.py - Win32 chart controls for the MT5 CLI.

This module controls only the already-open MT5 terminal window. It avoids
global focus changes by sending Win32 messages directly to the terminal and
timeframe toolbar HWNDs.
"""
from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from ctypes import wintypes


TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN")
TOOLBAR_BUTTON_INDEX = {
    "M1": 0,
    "M5": 1,
    "M15": 2,
    "M30": 3,
    "H1": 4,
    "H4": 5,
    "D1": 6,
    "W1": 7,
    "MN": 8,
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

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
VK_RETURN = 0x0D
VK_END = 0x23
TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TB_PRESSBUTTON = 0x0403

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


def _fail(code: str, message: str, *, mt5_retcode: int | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": mt5_retcode}}


def _win32():
    try:
        import win32con  # noqa: PLC0415
        import win32gui  # noqa: PLC0415
        import win32process  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pywin32 is required for chart controls on Windows.") from exc
    return win32gui, win32con, win32process


def normalize_timeframe(tf: str) -> str:
    value = tf.upper()
    if value == "MN1":
        value = "MN"
    if value not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return value


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
    """Find the MT5 top-level window by title substring or common aliases."""
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


def current_title(window_substring: str = "MT5") -> dict:
    match = find_window(window_substring)
    if not match:
        return _fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")
    return {"ok": True, "data": {"hwnd": match.hwnd, "title": match.title}}


def title_has_symbol_tf(title: str, symbol: str, tf: str | None = None) -> bool:
    title_upper = title.upper()
    if symbol.upper() not in title_upper:
        return False
    if tf is None:
        return True
    normalized = normalize_timeframe(tf)
    return any(alias.upper() in title_upper for alias in TF_TITLE_ALIASES[normalized])


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
    win32gui, _, win32process = _win32()
    _thread_id, process_id = win32process.GetWindowThreadProcessId(toolbar_hwnd)
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.VirtualAllocEx.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel32.VirtualAllocEx.restype = wintypes.LPVOID
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
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
            process,
            None,
            ctypes.sizeof(_TBBUTTON),
            MEM_COMMIT,
            PAGE_READWRITE,
        )
        if not remote:
            return None
        ok = win32gui.SendMessage(toolbar_hwnd, TB_GETBUTTON, index, int(remote))
        if not ok:
            return None
        local = _TBBUTTON()
        bytes_read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            process,
            remote,
            ctypes.byref(local),
            ctypes.sizeof(local),
            ctypes.byref(bytes_read),
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


def switch_tf(tf: str, window_substring: str = "MT5", settle_seconds: float = 0.5) -> dict:
    """Switch the active chart timeframe through MT5's period toolbar."""
    try:
        normalized = normalize_timeframe(tf)
    except ValueError as exc:
        return _fail("CHART_INVALID_TIMEFRAME", str(exc))

    match = find_window(window_substring)
    if not match:
        return _fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    toolbar = _find_period_toolbar(match.hwnd)
    if not toolbar:
        return _fail("CHART_TOOLBAR_NOT_FOUND", "Could not find the MT5 period toolbar.")

    if not _click_toolbar_button(match.hwnd, toolbar, normalized):
        return _fail("CHART_TOOLBAR_BUTTON_NOT_FOUND", f"Could not resolve toolbar button for {normalized}.")
    _press_key(match.hwnd, VK_END)
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    refreshed = find_window(window_substring)
    title = refreshed.title if refreshed else match.title
    if not title_has_symbol_tf(title, "", normalized):
        return _fail(
            "CHART_TIMEFRAME_VERIFY_FAILED",
            f"MT5 title did not show timeframe {normalized}: {title}",
        )

    return {"ok": True, "data": {"timeframe": normalized, "title": title, "hwnd": match.hwnd}}


def symbol(symbol_name: str, window_substring: str = "MT5", settle_seconds: float = 0.5) -> dict:
    """Switch the active chart symbol and verify it from the MT5 title bar."""
    symbol_name = symbol_name.upper()
    match = find_window(window_substring)
    if not match:
        return _fail("CHART_WINDOW_NOT_FOUND", f"No MT5 window matched '{window_substring}'.")

    if not title_has_symbol_tf(match.title, symbol_name):
        _send_text(match.hwnd, symbol_name)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        refreshed = find_window(window_substring)
        title = refreshed.title if refreshed else match.title
    else:
        title = match.title

    if not title_has_symbol_tf(title, symbol_name):
        return _fail(
            "CHART_SYMBOL_VERIFY_FAILED",
            f"MT5 title did not show symbol {symbol_name}: {title}",
        )

    return {"ok": True, "data": {"symbol": symbol_name, "title": title, "hwnd": match.hwnd}}
