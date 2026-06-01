"""Tests for mt5_cli/chart/new_chart.py - File > New Chart > <symbol> menu poke.

Strategy: build a fake MT5 menu tree representing the File > New Chart
subtree (with both top-level favorite symbols AND nested Forex/Indices
category submenus) and monkeypatch mt5_cli.chart._menu.menu_string to
read from it. Avoids the ctypes GetMenuStringW path and the real MT5
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


# Fake menu tree representing MT5's main menu structure with the File >
# New Chart subtree:
#   100 = main menu bar:
#     -> "&File"      (submenu 110)
#     -> "&Insert"    (submenu 200)
#   110 = File submenu:
#     -> "&New Chart" (submenu 130)
#     -> "Open Deleted" (submenu 140)
#     -> "Profiles"   (submenu 150)
#   130 = New Chart submenu (favorites at top + categories below):
#     -> "EURUSD"     (leaf, cmd 7001)   <- top-level favorite
#     -> "GBPUSD"     (leaf, cmd 7002)
#     -> "USDJPY"     (leaf, cmd 7003)
#     -> "Forex"      (submenu 131)      <- category for non-favorites
#     -> "Indices"    (submenu 132)
#   131 = Forex submenu:
#     -> "AUDCAD"     (leaf, cmd 7101)
#     -> "EURGBP"     (leaf, cmd 7102)
#     -> "USDCHF"     (leaf, cmd 7103)
#   132 = Indices submenu:
#     -> "SP500"      (leaf, cmd 7201)
#     -> "NAS100"     (leaf, cmd 7202)
_FAKE_MENU_TREE = {
    100: [("&File", 110, -1), ("&Insert", 200, -1)],
    110: [
        ("&New Chart", 130, -1),
        ("Open Deleted", 140, -1),
        ("Profiles", 150, -1),
    ],
    130: [
        ("EURUSD", 0, 7001),
        ("GBPUSD", 0, 7002),
        ("USDJPY", 0, 7003),
        ("Forex", 131, -1),
        ("Indices", 132, -1),
    ],
    131: [
        ("AUDCAD", 0, 7101),
        ("EURGBP", 0, 7102),
        ("USDCHF", 0, 7103),
    ],
    132: [
        ("SP500", 0, 7201),
        ("NAS100", 0, 7202),
    ],
    # Unused; present to avoid KeyError on incidental walks
    200: [],
    140: [],
    150: [],
}


@pytest.fixture
def fake_pywin32(monkeypatch):
    """Inject a MagicMock win32gui + a top-level MT5 window match, and
    monkeypatch mt5_cli.chart._menu.menu_string to read from the fake
    menu tree (skips the ctypes GetMenuStringW path)."""
    _purge_chart_cache()

    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetClassName.return_value = "MetaQuotes::MetaTrader::Frame"
    fake_gui.EnumWindows.side_effect = lambda cb, _: cb(1000, None)
    fake_gui.GetParent.return_value = 0

    # Default chart-list diff: before-snapshot returns no charts; after the
    # WM_COMMAND post we simulate ONE new chart appearing (hwnd 5500).
    # Tests that need a different diff (e.g., to verify hwnd identification
    # with multiple charts) override fake_gui.EnumChildWindows.side_effect
    # themselves.
    new_chart_state = {"posted": False}
    NEW_CHART_HWND = 5500

    def fake_enum_child_default(parent, cb, _extra):
        # _find_mdi_client calls EnumChildWindows looking for MDIClient;
        # we return nothing so _active_chart_hwnd falls through to None.
        # The chart-enumeration calls then drive the diff.
        if not new_chart_state["posted"]:
            return  # before-snapshot: zero charts
        # after-snapshot: the new chart appears
        cb(NEW_CHART_HWND, None)

    fake_gui.EnumChildWindows.side_effect = fake_enum_child_default

    def remember_post(hwnd, msg, *args):
        # Mark "posted" so the next EnumChildWindows call reports the new chart.
        if msg == 0x0111:  # WM_COMMAND
            new_chart_state["posted"] = True
        return 1
    fake_gui.PostMessage.side_effect = remember_post

    # GetWindowText: hwnd 1000 = main MT5 window; 5500 = the new chart
    fake_gui.GetWindowText.side_effect = lambda hwnd: {
        1000: "MetaTrader 5",
        NEW_CHART_HWND: "[NEW,M1]",
    }.get(hwnd, "")
    # GetClassName: hwnd 1000 = MT5 main; 5500 = chart child class
    fake_gui.GetClassName.side_effect = lambda hwnd: {
        1000: "MetaQuotes::MetaTrader::Frame",
        NEW_CHART_HWND: "AfxFrameOrView140s",
    }.get(hwnd, "")
    fake_gui.GetFocus.return_value = 0
    fake_gui.GetForegroundWindow.return_value = 0
    fake_gui.SendMessage.return_value = 0
    fake_gui.GetMenu.return_value = 100

    # Menu APIs read from the fake tree
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


def test_new_chart_finds_top_level_favorite(fake_pywin32):
    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["symbol"] == "USDJPY"
    assert env["data"]["command_id"] == 7003
    assert env["data"]["menu_path"] == "File > New Chart > USDJPY"

    # WM_COMMAND posted to the MT5 main window with the correct command id
    wm_command_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0111
    ]
    assert wm_command_calls
    assert wm_command_calls[0].args == (1000, 0x0111, 7003, 0)


def test_new_chart_finds_symbol_nested_under_forex_submenu(fake_pywin32):
    """find_leaf_command_id_recursive must descend into category submenus
    when the symbol isn't a top-level favorite."""
    from mt5_cli.chart import new_chart
    env = new_chart("EURGBP", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 7102


def test_new_chart_finds_symbol_in_indices_submenu(fake_pywin32):
    from mt5_cli.chart import new_chart
    env = new_chart("SP500", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["command_id"] == 7201


def test_new_chart_uppercases_symbol_argument(fake_pywin32):
    """Caller passes "usdjpy" lowercase; menu compare normalizes."""
    from mt5_cli.chart import new_chart
    env = new_chart("usdjpy", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["symbol"] == "USDJPY"
    assert env["data"]["command_id"] == 7003


# ---------------------------------------------------------------------------
# hwnd identification via before/after diff
# ---------------------------------------------------------------------------


def test_new_chart_identifies_new_chart_hwnd_via_diff(fake_pywin32):
    """After posting WM_COMMAND, enumerate_chart_children is called twice
    (once before, once after). The hwnd that appears in 'after' but not
    'before' is the new chart."""
    # Track which child enumeration this is (before vs after the post)
    state = {"call_count": 0}

    def fake_enum_children(parent, cb, _):
        # _find_mdi_client uses EnumChildWindows too; let it return nothing
        # (the helper falls back to other paths). Then for the diff calls
        # we feed our chart list.
        state["call_count"] += 1
        if state["call_count"] == 1:
            # First call: _find_mdi_client looking for MDIClient class.
            # Return nothing so _active_chart_hwnd falls through.
            return
        if state["call_count"] == 2:
            # First chart enumeration (before posting): one existing chart
            cb(2000, None)
        if state["call_count"] == 3:
            # MDIClient lookup for the second enumerate (after posting)
            return
        if state["call_count"] == 4:
            # Second chart enumeration (after posting): two charts now
            cb(2000, None)
            cb(2500, None)  # the new one

    fake_pywin32.EnumChildWindows.side_effect = fake_enum_children
    fake_pywin32.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5",
        2000: "[EURUSD,H1]",
        2500: "[USDJPY,M15]",
    }.get(h, "")
    fake_pywin32.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        2000: "AfxFrameOrView140s",
        2500: "AfxFrameOrView140s",
    }.get(h, "")

    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["hwnd"] == 2500  # the diffed new chart


# ---------------------------------------------------------------------------
# Optional timeframe switch
# ---------------------------------------------------------------------------


def test_new_chart_calls_switch_tf_when_timeframe_given(fake_pywin32, monkeypatch):
    # Import the MODULE, not the re-exported function, so we can patch
    # the module-level switch_tf binding used inside new_chart().
    # The submodule mt5_cli.chart.new_chart is shadowed at the package
    # namespace by the re-exported function (chart/__init__.py does
    # `from .new_chart import new_chart`). Pull the actual module via
    # importlib so we can patch its module-level switch_tf binding.
    import importlib
    new_chart_mod = importlib.import_module("mt5_cli.chart.new_chart")
    switch_calls: list = []

    def fake_switch_tf(tf, *, window_substring="MT5", settle_seconds=0.5,
                      chart_id=None):
        switch_calls.append({"tf": tf, "chart_id": chart_id})
        return {"ok": True, "data": {"timeframe": tf.upper(), "title": "..."}}

    monkeypatch.setattr(new_chart_mod, "switch_tf", fake_switch_tf)

    env = new_chart_mod.new_chart("USDJPY", timeframe="H4", settle_seconds=0)
    assert env["ok"] is True
    assert env["data"]["timeframe"] == "H4"
    assert switch_calls and switch_calls[0]["tf"] == "H4"


def test_new_chart_returns_partial_success_when_tf_switch_fails(
    fake_pywin32, monkeypatch
):
    """Chart opened OK; switch_tf failed. Return ok envelope with a
    tf_switch_warning so the caller knows the chart is there but the
    TF didn't apply."""
    # The submodule mt5_cli.chart.new_chart is shadowed at the package
    # namespace by the re-exported function (chart/__init__.py does
    # `from .new_chart import new_chart`). Pull the actual module via
    # importlib so we can patch its module-level switch_tf binding.
    import importlib
    new_chart_mod = importlib.import_module("mt5_cli.chart.new_chart")

    def fake_switch_tf(tf, **kwargs):
        return {"ok": False, "error": {"code": "CHART_TIMEFRAME_VERIFY_FAILED",
                                       "message": "title did not update"}}

    monkeypatch.setattr(new_chart_mod, "switch_tf", fake_switch_tf)

    env = new_chart_mod.new_chart("USDJPY", timeframe="Q1", settle_seconds=0)
    assert env["ok"] is True  # chart opened
    assert env["data"]["timeframe"] is None  # TF not applied
    assert env["data"]["tf_switch_warning"]["code"] == "CHART_TIMEFRAME_VERIFY_FAILED"


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_new_chart_fails_when_window_missing(monkeypatch):
    _purge_chart_cache()
    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""
    fake_gui.EnumWindows.return_value = None
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con", types.SimpleNamespace(MF_BYPOSITION=0x0400))
    monkeypatch.setitem(sys.modules, "win32process", MagicMock())

    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY")
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_WINDOW_NOT_FOUND"
    _purge_chart_cache()


def test_new_chart_fails_when_menu_bar_absent(fake_pywin32):
    fake_pywin32.GetMenu.return_value = 0
    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_NOT_FOUND"


def test_new_chart_fails_when_file_submenu_missing(fake_pywin32, monkeypatch):
    broken_tree = dict(_FAKE_MENU_TREE)
    broken_tree[100] = [("&Insert", 200, -1)]  # drop File
    from mt5_cli.chart import _menu
    monkeypatch.setattr(
        _menu, "menu_string",
        lambda h, i: broken_tree[h][i][0],
    )
    fake_pywin32.GetMenuItemCount.side_effect = lambda h: len(broken_tree.get(h, []))
    fake_pywin32.GetSubMenu.side_effect = lambda h, i: broken_tree[h][i][1]

    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_PATH_NOT_FOUND"
    assert "File" in env["error"]["message"]


def test_new_chart_fails_when_new_chart_submenu_missing(fake_pywin32, monkeypatch):
    broken_tree = dict(_FAKE_MENU_TREE)
    # File submenu without New Chart
    broken_tree[110] = [("Open Deleted", 140, -1), ("Profiles", 150, -1)]
    from mt5_cli.chart import _menu
    monkeypatch.setattr(
        _menu, "menu_string",
        lambda h, i: broken_tree[h][i][0],
    )
    fake_pywin32.GetMenuItemCount.side_effect = lambda h: len(broken_tree.get(h, []))
    fake_pywin32.GetSubMenu.side_effect = lambda h, i: broken_tree[h][i][1]

    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_MENU_PATH_NOT_FOUND"
    assert "New Chart" in env["error"]["message"]


def test_new_chart_fails_when_symbol_not_in_any_submenu(fake_pywin32):
    """Symbol absent from top-level favorites AND every category submenu."""
    from mt5_cli.chart import new_chart
    env = new_chart("XXXYYY", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_SYMBOL_NOT_FOUND_IN_MENU"
    assert "XXXYYY" in env["error"]["message"]
    assert "Market Watch" in env["error"]["message"]  # actionable hint


# ---------------------------------------------------------------------------
# Codex post-fix P2 #3: fail-closed when the new chart can't be identified
# ---------------------------------------------------------------------------


def test_new_chart_fails_closed_when_no_new_hwnd_appeared(fake_pywin32):
    """If the menu post does NOT result in a new chart (MT5 focused an
    existing chart, refused the command, or the symbol is disabled),
    return CHART_NEW_CHART_NOT_DETECTED rather than fabricating success."""
    # Override the default fixture behavior: both before and after
    # enumerations return the same set of charts (no diff).
    existing_chart_hwnd = 2000

    def fake_enum_unchanged(parent, cb, _extra):
        # _find_mdi_client iterates too; return nothing so it falls through
        # to other paths, then both chart enumerations return the existing
        # chart only - no diff regardless of how many times we're called.
        cb(existing_chart_hwnd, None)

    fake_pywin32.EnumChildWindows.side_effect = fake_enum_unchanged
    fake_pywin32.GetWindowText.side_effect = lambda h: {
        1000: "MetaTrader 5",
        existing_chart_hwnd: "[EURUSD,H1]",
    }.get(h, "")
    fake_pywin32.GetClassName.side_effect = lambda h: {
        1000: "MetaQuotes::MetaTrader::Frame",
        existing_chart_hwnd: "AfxFrameOrView140s",
    }.get(h, "")

    from mt5_cli.chart import new_chart
    env = new_chart("USDJPY", settle_seconds=0)
    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_NEW_CHART_NOT_DETECTED"
    assert "USDJPY" in env["error"]["message"]


def test_new_chart_fails_closed_when_before_snapshot_raises(fake_pywin32):
    """If the before-snapshot enumerate_chart_children raises, refuse to
    post WM_COMMAND - we can't reliably identify the result."""
    import importlib
    new_chart_mod = importlib.import_module("mt5_cli.chart.new_chart")

    def raising_enum(*args, **kwargs):
        raise RuntimeError("simulated Win32 failure")

    # Patch enumerate_chart_children at the new_chart module level
    # (it was imported there from chart.chart).
    import pytest as _pytest
    monkey = _pytest.MonkeyPatch()
    monkey.setattr(new_chart_mod, "enumerate_chart_children", raising_enum)
    try:
        from mt5_cli.chart import new_chart
        env = new_chart("USDJPY", settle_seconds=0)
    finally:
        monkey.undo()

    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_NEW_CHART_SNAPSHOT_FAILED"
    # And critically: WM_COMMAND was NOT posted (no chart-id to verify)
    wm_command_calls = [
        c for c in fake_pywin32.PostMessage.call_args_list
        if c.args[1] == 0x0111
    ]
    assert not wm_command_calls


def test_new_chart_fails_when_after_snapshot_raises(fake_pywin32):
    """before-snapshot succeeds (empty), WM_COMMAND posted, but the
    after-snapshot raises. Should return CHART_NEW_CHART_VERIFY_FAILED."""
    import importlib
    new_chart_mod = importlib.import_module("mt5_cli.chart.new_chart")

    call_state = {"n": 0}

    def flaky_enum(parent):
        call_state["n"] += 1
        if call_state["n"] == 1:
            return []  # before-snapshot succeeds with empty list
        raise RuntimeError("simulated post-post enum failure")

    import pytest as _pytest
    monkey = _pytest.MonkeyPatch()
    monkey.setattr(new_chart_mod, "enumerate_chart_children", flaky_enum)
    try:
        from mt5_cli.chart import new_chart
        env = new_chart("USDJPY", settle_seconds=0)
    finally:
        monkey.undo()

    assert env["ok"] is False
    assert env["error"]["code"] == "CHART_NEW_CHART_VERIFY_FAILED"


# ---------------------------------------------------------------------------
# Bridge isolation
# ---------------------------------------------------------------------------


def test_new_chart_module_does_not_import_metatrader5():
    """Pure Win32 — never touches the MT5 SDK bridge."""
    import importlib
    import mt5_cli.chart.new_chart  # noqa: F401
    mod = importlib.import_module("mt5_cli.chart.new_chart")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "import MetaTrader5" not in src
    assert "from MetaTrader5" not in src
