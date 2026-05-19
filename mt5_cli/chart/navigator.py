"""MT5 Navigator panel control - F5 refresh poke after EA/indicator deploy.

After `mt5_cli.mql5.deployer.deploy_ea` copies the .ex5 into MQL5/Experts/,
MT5's Navigator panel does NOT rescan until the user manually right-clicks
Refresh (or focuses the panel and presses F5). A subsequent
`mt5 chart attach-ea <name>` then fails because the menu item does not
exist yet.

This module posts the F5 keystroke to the Navigator child window so the
rescan happens automatically. The actual rescan is performed by MT5 in
response to F5 and is NOT programmatically verifiable from outside; the
envelope is explicit about that — `attempted=True` means we posted the
keystroke, not that we confirmed a rescan.

Bridge isolation: pure Win32 (lazy-imported via chart._win32). Never
touches the MT5 Python SDK.
"""
from __future__ import annotations

from mt5_cli.chart.chart import _win32, find_window
from mt5_cli.reports import fail, ok

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_F5 = 0x74

_NAVIGATOR_TITLE = "navigator"


def _find_navigator_child(main_hwnd: int) -> int | None:
    """Walk MT5's child windows for the dockable Navigator panel.

    The panel's title bar text is 'Navigator' (case-insensitive match
    handles locale variants that still keep the English token; full
    localization is out of scope for Wave A and would warrant a
    separate spike).
    """
    win32gui, _, _ = _win32()
    found: list[int] = []

    def enum_cb(hwnd, _extra):
        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:  # noqa: BLE001
            return
        if _NAVIGATOR_TITLE in title.lower():
            found.append(hwnd)

    win32gui.EnumChildWindows(main_hwnd, enum_cb, None)
    return found[0] if found else None


def refresh_navigator(window_substring: str = "MT5") -> dict:
    """Post F5 to the MT5 Navigator panel to trigger a rescan.

    Fail-closed: returns NAVIGATOR_NOT_FOUND when either the MT5 main
    window or the Navigator child panel cannot be located. On those
    paths no keystroke is sent.

    Returns:
        ok envelope with {attempted: True, navigator_hwnd, message}
        when F5 was posted. The message documents that the resulting
        rescan is not programmatically verifiable from outside MT5.
    """
    main = find_window(window_substring)
    if main is None:
        return fail(
            "NAVIGATOR_NOT_FOUND",
            f"MT5 main window not found (window_substring={window_substring!r}).",
        )

    nav_hwnd = _find_navigator_child(main.hwnd)
    if nav_hwnd is None:
        return fail(
            "NAVIGATOR_NOT_FOUND",
            "Navigator panel not found inside MT5 main window. The panel "
            "may be hidden — open View > Navigator (or Ctrl+N) and retry.",
        )

    win32gui, _, _ = _win32()
    win32gui.PostMessage(nav_hwnd, WM_KEYDOWN, VK_F5, 0)
    win32gui.PostMessage(nav_hwnd, WM_KEYUP, VK_F5, 0)
    return ok({
        "attempted": True,
        "navigator_hwnd": nav_hwnd,
        "message": (
            "F5 posted to Navigator panel. Rescan is not programmatically "
            "verifiable from outside MT5; if a subsequent attach-ea fails "
            "with CHART_EA_NOT_FOUND, refresh the Navigator manually."
        ),
    })
