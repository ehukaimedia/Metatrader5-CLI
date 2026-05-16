"""Tests for mt5_cli/chart/attach_ea.py - Insert > Experts > <name> menu poke.

Strategy: fake MT5 menu tree representing Insert > Experts with both
top-level EAs and nested category submenus (Examples, Advisors). Same
pattern as test_chart_indicators_attach.py + test_chart_new_chart.py.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest


def _purge_chart_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


# Fake menu tree representing MT5's main menu with the Insert > Experts subtree:
#   100 = main menu bar:
#     -> "&Insert"  (submenu 200)
#   200 = Insert submenu:
#     -> "&Indicators" (submenu 300)  — present for completeness
#     -> "E&xperts"    (submenu 400)
#   400 = Experts submenu (top-level favorites + nested categories):
#     -> "MyTrendEA"          (leaf, cmd 8001)   — top-level user EA
#     -> "AdaptiveTrailEA"    (leaf, cmd 8002)
#     -> "Examples"           (submenu 410)      — built-in samples
#     -> "Advisors"           (submenu 420)      — MQL5/Experts/Advisors/
#   410 = Examples submenu:
#     -> "MACD Sample"        (leaf, cmd 8101)
#     -> "MovingAverage"      (leaf, cmd 8102)
#   420 = Advisors submenu:
#     -> "ExpertMACD"         (leaf, cmd 8201)
#     -> "ExpertMAMA"         (leaf, cmd 8202)
_FAKE_MENU_TREE = {
    100: [("&Insert", 200, -1)],
    200: [("&Indicators", 300, -1), ("E&xperts", 400, -1)],
    300: [],  # unused
    400: [
        ("MyTrendEA", 0, 8001),
        ("AdaptiveTrailEA", 0, 8002),
        ("Examples", 410, -1),
        ("Advisors", 420, -1),
    ],
    410: [
        ("MACD Sample", 0, 8101),
        ("MovingAverage", 0, 8102),
    ],
    420: [
        ("ExpertMACD", 0, 8201),
        ("ExpertMAMA", 0, 8202),
    ],
}


@pytest.fixture
def fake_pywin32(monkeypatch):
    _purge_chart_cache()

    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = "MetaTrader 5"
    fake_gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"
    fake_gui.EnumWindows.side_effect = lambda cb, _: cb(1000, None)
    fake_gui.EnumChildWindows.return_value = None
    fake_gui.GetParent.return_value = 0
    fake_gui.GetFocus.return_value = 0
    fake_gui.GetForegroundWindow.return_value = 9999  # the (fake) EA param dialog
    fake_gui.PostMessage.return_value = 1
    fake_gui.SendMessage.return_value = 0
    fake_gui.GetMenu.return_value = 100
    fake_gui.GetMenuItemCount.side_effect = lambda h: len(_FAKE_MENU_TREE.get(h, []))
    fake_gui.GetSubMenu.side_effect = lambda h, i: _FAKE_MENU_TREE[h][i][1]
    fake_gui.GetMenuItemID.side_effect = lambda h, i: _FAKE_MENU_TREE[h][i][2]

    fake_con = types.SimpleNamespace(MF_BYPOSITION=0x0400)
    fake_process = MagicMock(name="win32process")

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", fake_con)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    # Patch menu_string at the shared helper module
    from mt5_cli.chart import _menu
    monkeypatch.setattr(
        _menu,
        "menu_string",
        lambda hmenu, index: _FAKE_MENU_TREE[hmenu][index][0],
    )

    yield fake_gui

    _purge_chart_cache()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_attach_ea_finds_top_level_user_ea(fake_pywin32):
    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["expert_name"] == "MyTrendEA"
    assert env["data"]["command_id"] == 8001
    assert env["data"]["menu_path"] == "Insert > Experts > MyTrendEA"

    wm_command_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0111
    ]
    assert wm_command_calls
    assert wm_command_calls[0].args == (1000, 0x0111, 8001, 0)


def test_attach_ea_finds_ea_nested_under_advisors_submenu(fake_pywin32):
    """Recursive walk under Experts must descend into Advisors/Examples."""
    from mt5_cli.chart import attach_ea
    env = attach_ea("ExpertMAMA", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 8202


def test_attach_ea_finds_ea_nested_under_examples_submenu(fake_pywin32):
    from mt5_cli.chart import attach_ea
    env = attach_ea("MACD Sample", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 8101


def test_attach_ea_is_case_insensitive(fake_pywin32):
    from mt5_cli.chart import attach_ea
    env = attach_ea("adaptivetrailea", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 8002


def test_attach_ea_handles_ampersand_accelerators(fake_pywin32):
    """The fake tree uses '&Insert' / 'E&xperts'. Walk must strip '&'."""
    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA", settle_seconds=0)
    assert env["ok"] is True  # passes only if '&' is stripped


# ---------------------------------------------------------------------------
# Auto-confirm
# ---------------------------------------------------------------------------


def test_attach_ea_posts_enter_when_auto_confirm_true(fake_pywin32):
    from mt5_cli.chart import attach_ea
    attach_ea("MyTrendEA", settle_seconds=0, auto_confirm=True)
    keydown_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D  # WM_KEYDOWN + VK_RETURN
    ]
    assert keydown_calls
    assert keydown_calls[0].args[0] == 9999  # foreground hwnd


def test_attach_ea_skips_enter_when_auto_confirm_false(fake_pywin32):
    from mt5_cli.chart import attach_ea
    attach_ea("MyTrendEA", settle_seconds=0, auto_confirm=False)
    keydown_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D
    ]
    assert not keydown_calls


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_attach_ea_fails_when_window_missing(monkeypatch):
    _purge_chart_cache()
    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""
    fake_gui.EnumWindows.return_value = None
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", types.SimpleNamespace(MF_BYPOSITION=0x0400))
    monkeypatch.setitem(sys.modules, "win32process", MagicMock())

    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"
    _purge_chart_cache()


def test_attach_ea_fails_when_menu_bar_absent(fake_pywin32):
    fake_pywin32.GetMenu.return_value = 0
    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_NOT_FOUND"


def test_attach_ea_fails_when_experts_submenu_missing(fake_pywin32, monkeypatch):
    broken_tree = dict(_FAKE_MENU_TREE)
    # Insert without Experts
    broken_tree[200] = [("&Indicators", 300, -1)]
    from mt5_cli.chart import _menu
    monkeypatch.setattr(
        _menu, "menu_string",
        lambda h, i: broken_tree[h][i][0],
    )
    fake_pywin32.GetMenuItemCount.side_effect = lambda h: len(broken_tree.get(h, []))
    fake_pywin32.GetSubMenu.side_effect = lambda h, i: broken_tree[h][i][1]

    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_PATH_NOT_FOUND"
    assert "Experts" in env["error"]["message"]


def test_attach_ea_fails_when_ea_not_found(fake_pywin32):
    from mt5_cli.chart import attach_ea
    env = attach_ea("NonexistentEA", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_EA_NOT_FOUND"
    assert "NonexistentEA" in env["error"]["message"]
    assert "deploy" in env["error"]["message"]


# ---------------------------------------------------------------------------
# Chart activation
# ---------------------------------------------------------------------------


def test_attach_ea_activates_chart_when_chart_id_given(fake_pywin32):
    def enum_children(parent, cb, _):
        if parent == 1000:
            cb(7777, None)  # this hwnd will be the MDIClient

    fake_pywin32.EnumChildWindows.side_effect = enum_children
    fake_pywin32.GetClassName.side_effect = (
        lambda h: "MDIClient" if h == 7777 else "MetaQuotes::MetaTrader::Frame"
    )

    from mt5_cli.chart import attach_ea
    env = attach_ea("MyTrendEA", chart_id=5555, settle_seconds=0)
    assert env["ok"] is True
    # WM_MDIACTIVATE (0x0222) should have been sent to MDIClient (7777)
    # with chart_id (5555) as wParam.
    mdi_calls = [
        c for c in fake_pywin32.SendMessage.call_args_list
        if c.args[1] == 0x0222
    ]
    assert mdi_calls
    assert mdi_calls[0].args == (7777, 0x0222, 5555, 0)


# ---------------------------------------------------------------------------
# Bridge isolation
# ---------------------------------------------------------------------------


def test_attach_ea_module_does_not_import_metatrader5():
    """Pure Win32 — never touches the MT5 SDK bridge."""
    import importlib
    import mt5_cli.chart.attach_ea  # noqa: F401
    mod = importlib.import_module("mt5_cli.chart.attach_ea")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
