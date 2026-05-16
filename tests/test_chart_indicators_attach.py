"""Tests for mt5_cli/chart/indicators_attach.py - Win32 GUI menu poking.

Strategy: build a small fake menu tree (dict keyed by hmenu) and
monkeypatch the win32gui menu APIs + the _menu_string helper to read
from it. This avoids the ctypes GetMenuStringW path and the real MT5
window dependency.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest


def _purge_chart_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


# Fake menu tree representing MT5's main menu structure:
#   100 = main menu bar
#     -> "File"      (submenu 110, no cmd)
#     -> "&Insert"   (submenu 200, no cmd)
#     -> "View"      (submenu 120, no cmd)
#   200 = Insert submenu
#     -> "&Indicators" (submenu 300)
#     -> "Objects"     (submenu 210)
#     -> "Scripts"     (submenu 220)
#   300 = Indicators submenu
#     -> "Trend"       (submenu 310)
#     -> "Custom"      (submenu 400)
#     -> "Oscillators" (submenu 320)
#   400 = Custom submenu (where user-deployed .ex5 indicators live)
#     -> "MyEMA"                       (leaf, cmd 5001)
#     -> "Advanced_Wavelet_Entry_Signal" (leaf, cmd 5002)
#     -> "EhukaiFVG"                   (leaf, cmd 5003)
_FAKE_MENU_TREE = {
    100: [("File", 110, -1), ("&Insert", 200, -1), ("View", 120, -1)],
    200: [("&Indicators", 300, -1), ("Objects", 210, -1), ("Scripts", 220, -1)],
    300: [("Trend", 310, -1), ("Custom", 400, -1), ("Oscillators", 320, -1)],
    400: [
        ("MyEMA", 0, 5001),
        ("Advanced_Wavelet_Entry_Signal", 0, 5002),
        ("EhukaiFVG", 0, 5003),
    ],
}


def _install_fake_menus(monkeypatch, *, fake_win32gui):
    """Wire fake_win32gui's menu APIs to read from _FAKE_MENU_TREE."""
    fake_win32gui.GetMenu.return_value = 100
    fake_win32gui.GetMenuItemCount.side_effect = lambda h: len(_FAKE_MENU_TREE.get(h, []))
    fake_win32gui.GetSubMenu.side_effect = lambda h, i: _FAKE_MENU_TREE[h][i][1]
    fake_win32gui.GetMenuItemID.side_effect = lambda h, i: _FAKE_MENU_TREE[h][i][2]


@pytest.fixture
def fake_pywin32(monkeypatch):
    """Inject a MagicMock win32gui at sys.modules level + a top-level MT5
    window match, and monkeypatch indicators_attach._menu_string to read
    from the fake menu tree (skips the ctypes GetMenuStringW path)."""
    _purge_chart_cache()

    fake_gui = MagicMock(name="win32gui")
    # Top-level window enumeration: one window titled "MetaTrader 5".
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = "MetaTrader 5"
    fake_gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"
    fake_gui.EnumWindows.side_effect = lambda cb, _: cb(1000, None)
    fake_gui.EnumChildWindows.return_value = None
    fake_gui.GetParent.return_value = 0
    fake_gui.GetFocus.return_value = 0
    fake_gui.GetForegroundWindow.return_value = 9999  # the (fake) param dialog
    fake_gui.PostMessage.return_value = 1
    fake_gui.SendMessage.return_value = 0

    # Win32con shim — only MF_BYPOSITION is referenced by the screenshot
    # helper path; indicators_attach.py uses the bare constant.
    fake_con = types.SimpleNamespace(MF_BYPOSITION=0x0400)
    fake_process = MagicMock(name="win32process")

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", fake_con)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    _install_fake_menus(monkeypatch, fake_win32gui=fake_gui)

    # Replace _menu_string so tests don't hit ctypes/GetMenuStringW.
    from mt5_cli.chart import indicators_attach
    monkeypatch.setattr(
        indicators_attach,
        "_menu_string",
        lambda hmenu, index: _FAKE_MENU_TREE[hmenu][index][0],
    )

    yield fake_gui

    _purge_chart_cache()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_attach_walks_menu_path_and_posts_command(fake_pywin32):
    from mt5_cli.chart import attach
    env = attach("MyEMA", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["indicator_name"] == "MyEMA"
    assert env["data"]["command_id"] == 5001
    assert env["data"]["menu_path"] == "Insert > Indicators > Custom > MyEMA"

    # Verify WM_COMMAND was posted with the correct command id to the MT5 window
    wm_command_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0111  # WM_COMMAND
    ]
    assert wm_command_calls
    assert wm_command_calls[0].args == (1000, 0x0111, 5001, 0)


def test_attach_resolves_user_indicator_name_exactly(fake_pywin32):
    """Exact match prevents 'ATR' colliding with built-in indicators
    that share substrings."""
    from mt5_cli.chart import attach
    env = attach("Advanced_Wavelet_Entry_Signal", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 5002


def test_attach_is_case_insensitive_for_indicator_name(fake_pywin32):
    """Menu text comparison is normalized to lowercase."""
    from mt5_cli.chart import attach
    env = attach("ehukaifvg", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 5003


def test_attach_handles_ampersand_accelerators_in_menu_path(fake_pywin32):
    """The fake menu tree uses '&Insert' / '&Indicators' (MT5's real
    accelerator markers). Walk must strip the ampersand before
    comparing to 'insert' / 'indicators'."""
    from mt5_cli.chart import attach
    env = attach("MyEMA", settle_seconds=0)
    assert env["ok"] is True  # passes only if the & is stripped


# ---------------------------------------------------------------------------
# Auto-confirm behavior
# ---------------------------------------------------------------------------


def test_attach_posts_enter_when_auto_confirm_true(fake_pywin32):
    from mt5_cli.chart import attach
    attach("MyEMA", settle_seconds=0, auto_confirm=True)
    # Look for WM_KEYDOWN with VK_RETURN posted to the foreground window (9999)
    keydown_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D  # WM_KEYDOWN + VK_RETURN
    ]
    assert keydown_calls
    assert keydown_calls[0].args[0] == 9999  # the foreground hwnd we mocked


def test_attach_skips_enter_when_auto_confirm_false(fake_pywin32):
    from mt5_cli.chart import attach
    attach("MyEMA", settle_seconds=0, auto_confirm=False)
    keydown_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D
    ]
    assert not keydown_calls  # no Enter posted


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_attach_fails_when_window_missing(monkeypatch):
    _purge_chart_cache()
    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""  # no window text -> no match
    fake_gui.EnumWindows.return_value = None  # callback never fires
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", types.SimpleNamespace(MF_BYPOSITION=0x0400))
    monkeypatch.setitem(sys.modules, "win32process", MagicMock())

    from mt5_cli.chart import attach
    env = attach("MyEMA")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"
    _purge_chart_cache()


def test_attach_fails_when_menu_bar_absent(fake_pywin32):
    fake_pywin32.GetMenu.return_value = 0  # no menu bar
    from mt5_cli.chart import attach
    env = attach("MyEMA", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_NOT_FOUND"


def test_attach_fails_when_indicators_submenu_missing(fake_pywin32, monkeypatch):
    """If MT5's menu structure changes and 'Indicators' isn't under
    Insert, the walk halts with CHART_MENU_PATH_NOT_FOUND."""
    broken_tree = dict(_FAKE_MENU_TREE)
    # Replace Insert's children: drop Indicators
    broken_tree[200] = [("Objects", 210, -1), ("Scripts", 220, -1)]
    from mt5_cli.chart import indicators_attach
    monkeypatch.setattr(
        indicators_attach,
        "_menu_string",
        lambda hmenu, index: broken_tree[hmenu][index][0],
    )
    fake_pywin32.GetMenuItemCount.side_effect = lambda h: len(broken_tree.get(h, []))
    fake_pywin32.GetSubMenu.side_effect = lambda h, i: broken_tree[h][i][1]
    fake_pywin32.GetMenuItemID.side_effect = lambda h, i: broken_tree[h][i][2]

    from mt5_cli.chart import attach
    env = attach("MyEMA", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_PATH_NOT_FOUND"
    assert "Indicators" in env["error"]["message"]


def test_attach_fails_when_indicator_leaf_not_found(fake_pywin32):
    from mt5_cli.chart import attach
    env = attach("NonexistentIndicator", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_INDICATOR_NOT_FOUND"
    assert "NonexistentIndicator" in env["error"]["message"]
    assert "deploy" in env["error"]["message"]  # actionable hint


# ---------------------------------------------------------------------------
# Chart activation
# ---------------------------------------------------------------------------


def test_attach_activates_chart_when_chart_id_given(fake_pywin32):
    """When chart_id is provided, activate_chart() runs first so the
    indicator lands on the right chart."""
    # _find_mdi_client enumerates children of parent 1000 looking for MDIClient.
    def enum_children(parent, cb, _):
        if parent == 1000:
            cb(7777, None)  # this hwnd will be the "MDIClient"

    fake_pywin32.EnumChildWindows.side_effect = enum_children
    fake_pywin32.GetClassName.side_effect = (
        lambda h: "MDIClient" if h == 7777 else "MetaQuotes::MetaTrader::Frame"
    )

    from mt5_cli.chart import attach
    env = attach("MyEMA", chart_id=4242, settle_seconds=0)
    assert env["ok"] is True
    # WM_MDIACTIVATE (0x0222) should have been sent to MDIClient (7777)
    # with chart_id (4242) as wParam.
    mdi_calls = [
        c for c in fake_pywin32.SendMessage.call_args_list
        if c.args[1] == 0x0222
    ]
    assert mdi_calls
    assert mdi_calls[0].args == (7777, 0x0222, 4242, 0)


# ---------------------------------------------------------------------------
# Bridge isolation
# ---------------------------------------------------------------------------


def test_indicators_attach_does_not_import_metatrader5():
    """The whole point of the GUI-poking rewrite: indicators_attach.py
    must NOT touch the MT5 SDK. Pure Win32."""
    import importlib
    import mt5_cli.chart.indicators_attach  # noqa: F401
    mod = importlib.import_module("mt5_cli.chart.indicators_attach")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
