"""Tests for mt5_cli/chart/navigator.py - Navigator panel refresh via F5 poke.

Hermetic: fakes pywin32 at sys.modules level (same fixture pattern as
test_chart.py). The implementation only sends a keystroke; whether MT5
actually rescans the Navigator is not programmatically verifiable, so
tests assert behavior we CAN verify: the right keystroke was posted to
the located Navigator child window.
"""
import sys
import types
from unittest.mock import MagicMock, call

import pytest


def _purge_chart_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


@pytest.fixture
def fake_pywin32(monkeypatch):
    _purge_chart_cache()

    fake_gui = MagicMock(name="win32gui")
    fake_con = types.SimpleNamespace(MF_BYPOSITION=0x0400)
    fake_process = MagicMock(name="win32process")

    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""
    fake_gui.GetClassName.return_value = ""
    fake_gui.GetParent.return_value = 0
    fake_gui.PostMessage.return_value = 1
    fake_gui.EnumWindows.return_value = None
    fake_gui.EnumChildWindows.return_value = None

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", fake_con)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    yield fake_gui, fake_con, fake_process

    _purge_chart_cache()


# Win32 constants the implementation must use
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_VK_F5 = 0x74


# ---------------------------------------------------------------------------
# refresh_navigator
# ---------------------------------------------------------------------------


def test_refresh_navigator_fails_closed_when_mt5_window_missing(fake_pywin32):
    """No MT5 main window -> NAVIGATOR_NOT_FOUND, attempted=False."""
    fake_gui, _, _ = fake_pywin32

    # EnumWindows finds nothing
    def enum_windows(cb, _extra):
        return None
    fake_gui.EnumWindows.side_effect = enum_windows

    from mt5_cli.chart.navigator import refresh_navigator
    result = refresh_navigator()
    assert result["ok"] is False
    assert result["error"]["code"] == "NAVIGATOR_NOT_FOUND"
    assert "MT5" in result["error"]["message"]
    # No keystroke posted when the window can't be found
    fake_gui.PostMessage.assert_not_called()


def test_refresh_navigator_fails_closed_when_panel_not_found(fake_pywin32):
    """MT5 found but no Navigator child -> NAVIGATOR_NOT_FOUND."""
    fake_gui, _, _ = fake_pywin32

    # MT5 main window
    main_hwnd = 1000
    fake_gui.GetClassName.side_effect = lambda h: (
        "MetaQuotes::MetaTrader::5.00" if h == main_hwnd else "Random"
    )
    fake_gui.GetWindowText.side_effect = lambda h: (
        "MetaTrader 5 Terminal" if h == main_hwnd else "Other Child"
    )
    fake_gui.IsWindowVisible.return_value = True

    def enum_windows(cb, _extra):
        cb(main_hwnd, None)
    fake_gui.EnumWindows.side_effect = enum_windows

    # EnumChildWindows yields children with no Navigator title
    def enum_children(parent, cb, _extra):
        cb(2001, None)
        cb(2002, None)
    fake_gui.EnumChildWindows.side_effect = enum_children

    from mt5_cli.chart.navigator import refresh_navigator
    result = refresh_navigator()
    assert result["ok"] is False
    assert result["error"]["code"] == "NAVIGATOR_NOT_FOUND"
    assert "Navigator" in result["error"]["message"]
    fake_gui.PostMessage.assert_not_called()


def test_refresh_navigator_posts_f5_keystroke_to_panel(fake_pywin32):
    """Happy path: located Navigator child receives WM_KEYDOWN+WM_KEYUP VK_F5."""
    fake_gui, _, _ = fake_pywin32

    main_hwnd = 1000
    nav_hwnd = 2042

    # Make MT5 main window discoverable
    fake_gui.GetClassName.side_effect = lambda h: (
        "MetaQuotes::MetaTrader::5.00" if h == main_hwnd else "Afx:something"
    )
    fake_gui.GetWindowText.side_effect = lambda h: {
        main_hwnd: "MetaTrader 5 Terminal",
        2001: "Market Watch",
        nav_hwnd: "Navigator",
        2003: "Toolbox",
    }.get(h, "")
    fake_gui.IsWindowVisible.return_value = True

    def enum_windows(cb, _extra):
        cb(main_hwnd, None)
    fake_gui.EnumWindows.side_effect = enum_windows

    def enum_children(parent, cb, _extra):
        for h in (2001, nav_hwnd, 2003):
            cb(h, None)
    fake_gui.EnumChildWindows.side_effect = enum_children

    from mt5_cli.chart.navigator import refresh_navigator
    result = refresh_navigator()
    assert result["ok"] is True
    assert result["data"]["attempted"] is True
    assert result["data"]["navigator_hwnd"] == nav_hwnd
    # F5 down then up to the Navigator child
    fake_gui.PostMessage.assert_has_calls([
        call(nav_hwnd, _WM_KEYDOWN, _VK_F5, 0),
        call(nav_hwnd, _WM_KEYUP, _VK_F5, 0),
    ], any_order=False)


def test_refresh_navigator_matches_panel_case_insensitively(fake_pywin32):
    """Panel title 'navigator' (lowercase) still matches."""
    fake_gui, _, _ = fake_pywin32

    main_hwnd = 1000
    nav_hwnd = 2099

    fake_gui.GetClassName.side_effect = lambda h: (
        "MetaQuotes::MetaTrader::5.00" if h == main_hwnd else "Afx:x"
    )
    fake_gui.GetWindowText.side_effect = lambda h: {
        main_hwnd: "MetaTrader 5",
        nav_hwnd: "navigator",   # lowercase
    }.get(h, "")
    fake_gui.IsWindowVisible.return_value = True

    def enum_windows(cb, _extra):
        cb(main_hwnd, None)
    fake_gui.EnumWindows.side_effect = enum_windows

    def enum_children(parent, cb, _extra):
        cb(nav_hwnd, None)
    fake_gui.EnumChildWindows.side_effect = enum_children

    from mt5_cli.chart.navigator import refresh_navigator
    result = refresh_navigator()
    assert result["ok"] is True
    assert result["data"]["navigator_hwnd"] == nav_hwnd


def test_refresh_navigator_envelope_documents_unverifiable_rescan(fake_pywin32):
    """Success envelope must include a message making clear F5 was sent
    but rescan is NOT programmatically verifiable. The CLI consumer
    needs to know the operator may still need to refresh manually."""
    fake_gui, _, _ = fake_pywin32

    main_hwnd = 1000
    nav_hwnd = 2042
    fake_gui.GetClassName.side_effect = lambda h: (
        "MetaQuotes::MetaTrader::5.00" if h == main_hwnd else "Afx:x"
    )
    fake_gui.GetWindowText.side_effect = lambda h: {
        main_hwnd: "MetaTrader 5",
        nav_hwnd: "Navigator",
    }.get(h, "")
    fake_gui.IsWindowVisible.return_value = True

    def enum_windows(cb, _extra):
        cb(main_hwnd, None)
    fake_gui.EnumWindows.side_effect = enum_windows

    def enum_children(parent, cb, _extra):
        cb(nav_hwnd, None)
    fake_gui.EnumChildWindows.side_effect = enum_children

    from mt5_cli.chart.navigator import refresh_navigator
    result = refresh_navigator()
    msg = result["data"].get("message", "").lower()
    assert "not" in msg and "verif" in msg, (
        "envelope must document that rescan is not programmatically verifiable"
    )
