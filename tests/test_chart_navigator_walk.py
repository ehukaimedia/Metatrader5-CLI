"""Tests for mt5_cli/chart/_navigator_walk.py - Navigator tree-walk helpers.

The walk has two cleanly-separable concerns:

1. Pure-logic tree traversal (find_ea_node, find_navigator_tree, constant
   discipline): tested hermetically against a fake NavigatorTreeReader.

2. Win32 plumbing (right_click_and_attach: PostMessage right-click, popup
   ownership check, caret-drift verify, VK_RETURN dispatch, VK_ESCAPE on
   drift): tested with mocked pywin32.

The ctypes-backed real NavigatorTreeReader (TVM_GETITEMRECT, 64-bit
VirtualAllocEx + SendMessageW) is exercised live during operator
confirmation, not in pytest. Wave A.1 contract acknowledges this gap and
ships with operator hand-off as the verification step.
"""
import sys
import types
from unittest.mock import MagicMock, call

import pytest


def _purge_chart_cache():
    for name in list(sys.modules):
        if name.startswith("mt5_cli.chart"):
            sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Fake reader — pure-Python stand-in for the ctypes-backed real reader
# ---------------------------------------------------------------------------


class FakeNavigatorTreeReader:
    """In-memory tree mirroring MT5's Navigator structure for hermetic tests.

    Mirrors Claude's empirical observation: root = 'MetaTrader 5',
    children = Accounts / Indicators / Expert Advisors / Services /
    Scripts. Under 'Expert Advisors': 3 folders (Advisors, Examples,
    Free Robots) then a flat list of user EAs.
    """

    # Each node: (text, parent_id, [child_ids])
    def __init__(self):
        self._nodes: dict[int, tuple[str, int | None]] = {}
        self._children: dict[int, list[int]] = {}
        self._rects: dict[int, tuple[int, int, int, int]] = {}
        self._next_id = 1
        self._selected: int | None = None
        # Tracks which items have been "made visible" via ensure_visible.
        # item_rect returns (0,0,0,0) for items NOT in this list, which
        # mirrors the live MT5 behavior where TVM_GETITEMRECT on items
        # inside collapsed folders returns NONE. This mechanism (Scotty
        # F1 from Wave A.1d review) turns the "ensure_visible-before-
        # item_rect" ordering into a real invariant: if production code
        # swaps the order, item_rect returns zero → NAV_TREE_RECT_ZERO
        # fires, and any happy-path test that expects ok=True will fail.
        self._ensured_visible: list[int] = []

    def add(self, text: str, parent: int | None = None,
            rect: tuple[int, int, int, int] | None = None) -> int:
        item = self._next_id
        self._next_id += 1
        self._nodes[item] = (text, parent)
        self._children[item] = []
        if rect is not None:
            self._rects[item] = rect
        if parent is not None:
            self._children[parent].append(item)
        return item

    # Reader interface ------------------------------------------------------

    def root_item(self) -> int | None:
        roots = [i for i, (_, p) in self._nodes.items() if p is None]
        return roots[0] if roots else None

    def first_child(self, item: int) -> int | None:
        kids = self._children.get(item, [])
        return kids[0] if kids else None

    def next_sibling(self, item: int) -> int | None:
        parent = self._nodes[item][1]
        if parent is None:
            return None
        siblings = self._children[parent]
        idx = siblings.index(item)
        return siblings[idx + 1] if idx + 1 < len(siblings) else None

    def item_text(self, item: int) -> str:
        return self._nodes[item][0]

    def item_rect(self, item: int) -> tuple[int, int, int, int]:
        # Mirror live MT5: items inside collapsed folders return zero
        # rect. ensure_visible must be called first to "expand" them.
        # Without this gate the ordering test would only check presence
        # and miss a production code path that read the rect before
        # expanding the parent chain.
        if item not in self._ensured_visible:
            return (0, 0, 0, 0)
        return self._rects.get(item, (0, 0, 0, 0))

    def selected_item(self) -> int | None:
        return self._selected

    def set_selected(self, item: int | None) -> None:
        self._selected = item

    def ensure_visible(self, item: int) -> None:
        """Track which items were ensure_visible'd. Tests inspect this.

        After this call, item_rect() will return the pre-set rect for
        the item; before, it returns (0,0,0,0) per F1 ordering invariant.
        """
        self._ensured_visible.append(item)


@pytest.fixture
def navigator_tree():
    """Standard Navigator tree shape per Claude's empirical probe."""
    tree = FakeNavigatorTreeReader()
    root = tree.add("MetaTrader 5")
    tree.add("Accounts", parent=root)
    tree.add("Indicators", parent=root)
    experts = tree.add("Expert Advisors", parent=root)
    tree.add("Advisors", parent=experts)
    tree.add("Examples", parent=experts)
    tree.add("Free Robots", parent=experts)
    # Flat user EAs after the 3 folder children
    tree.add("AdaptiveTrailEA", parent=experts,
             rect=(0, 500, 292, 520))
    tree.add("Advanced_Wavelet_Entry_ResearchEA", parent=experts,
             rect=(0, 520, 292, 540))
    tree.add("SmartFibChandelierManager", parent=experts,
             rect=(0, 540, 292, 560))
    # Nested EA under Advisors
    advisors_id = [i for i, (t, _) in tree._nodes.items()
                   if t == "Advisors"][0]
    tree.add("MyNestedEA", parent=advisors_id,
             rect=(0, 600, 292, 620))
    return tree


# ---------------------------------------------------------------------------
# find_ea_node — pure-logic tree walk
# ---------------------------------------------------------------------------


def test_find_ea_node_finds_top_level_ea(navigator_tree):
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import find_ea_node
    item = find_ea_node(navigator_tree, "SmartFibChandelierManager")
    assert item is not None
    assert navigator_tree.item_text(item) == "SmartFibChandelierManager"


def test_find_ea_node_is_case_insensitive(navigator_tree):
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import find_ea_node
    item = find_ea_node(navigator_tree, "smartfibchandeliermanager")
    assert item is not None
    assert navigator_tree.item_text(item) == "SmartFibChandelierManager"


def test_find_ea_node_finds_nested_ea_under_advisors(navigator_tree):
    """The walk must descend into Advisors / Examples / Free Robots
    folders to find EAs nested under category subtrees."""
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import find_ea_node
    item = find_ea_node(navigator_tree, "MyNestedEA")
    assert item is not None
    assert navigator_tree.item_text(item) == "MyNestedEA"


def test_find_ea_node_returns_none_for_unknown_ea(navigator_tree):
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import find_ea_node
    assert find_ea_node(navigator_tree, "DoesNotExistAtAll") is None


def test_find_ea_node_returns_none_when_no_experts_folder_present():
    """If the tree has no 'Expert Advisors' folder under root, the
    walk must return None — do NOT silently scan the whole tree
    looking for the EA in unrelated categories like Indicators."""
    _purge_chart_cache()
    tree = FakeNavigatorTreeReader()
    root = tree.add("MetaTrader 5")
    tree.add("Accounts", parent=root)
    tree.add("Indicators", parent=root)
    # 'Expert Advisors' deliberately absent
    from mt5_cli.chart._navigator_walk import find_ea_node
    assert find_ea_node(tree, "AnyEA") is None


# ---------------------------------------------------------------------------
# Constants — regression guards for build-specific Win32 magic numbers
# ---------------------------------------------------------------------------


def test_tvm_getitemrect_constant_is_0x1104():
    """Claude burned 3 probe cycles on a 0x1004 (ListView) vs 0x1104
    (TreeView) typo. Lock the value via a regression test so a future
    refactor can't silently regress to the wrong message ID."""
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import TVM_GETITEMRECT
    assert TVM_GETITEMRECT == 0x1104, (
        f"TVM_GETITEMRECT must be 0x1104 (TreeView), not {TVM_GETITEMRECT:#06x} "
        "— 0x1004 is ListView LVM_GETSUBITEMRECT and will return wrong data"
    )


def test_tree_selection_settle_seconds_is_documented_constant():
    """Empirical 20ms caret-state settle per Claude probe 2026-05-18.
    Lock as a named constant, not an inline magic number, so reviewers
    see the rationale."""
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import TREE_SELECTION_SETTLE_SECONDS
    assert TREE_SELECTION_SETTLE_SECONDS == 0.02


def test_popup_appear_timeout_seconds_is_documented_constant():
    """Empirical 150ms hard budget for #32768 popup appearance (4x
    observed avg of ~11ms per Claude probe 2026-05-18)."""
    _purge_chart_cache()
    from mt5_cli.chart._navigator_walk import POPUP_APPEAR_TIMEOUT_SECONDS
    assert POPUP_APPEAR_TIMEOUT_SECONDS == 0.15


def test_tvitemw_struct_is_56_bytes():
    """TVITEMW on 64-bit Windows MUST be exactly 56 bytes for MT5's
    TVM_GETITEMW to read the fields at the expected offsets.

    Regression-locked after Wave A.1b shipped with a 68-byte format
    string (extra '8x' after stateMask + extra '4x' after cchTextMax)
    that put pszText at offset 32 instead of 24. The struct overran
    the 56-byte VirtualAllocEx allocation AND MT5 read garbage for
    pszText → wrote text to a bogus address → item_text() returned
    empty → find_ea_node never matched anything → NAV_EA_NOT_FOUND
    on every live attach. Caught by Claude during live verification
    on Trading.com 2026-05-18."""
    _purge_chart_cache()
    from mt5_cli.chart import _navigator_walk
    packed = _navigator_walk._build_tvitemw_struct(
        item=0xDEADBEEF, pszText_remote=0xCAFEBABE,
        cch_text_max_chars=260,
    )
    assert len(packed) == 56, (
        f"TVITEMW struct must be 56 bytes for x64 Windows; got {len(packed)}. "
        "Check _build_tvitemw_struct format string for spurious padding."
    )


def test_tvitemw_struct_field_offsets():
    """Verify the fields land at the offsets MT5's TVM_GETITEMW reads
    from, NOT just that the total size happens to match.

    A struct could be 56 bytes total but with internal misalignment;
    this test catches that by decoding individual fields back out and
    comparing to the input sentinels."""
    _purge_chart_cache()
    import struct
    from mt5_cli.chart import _navigator_walk
    sentinel_item = 0x1122334455667788
    sentinel_pszText = 0xAABBCCDDEEFF1100
    sentinel_cch = 260
    packed = _navigator_walk._build_tvitemw_struct(
        item=sentinel_item, pszText_remote=sentinel_pszText,
        cch_text_max_chars=sentinel_cch,
    )
    # mask @ 0 (UINT, should be TVIF_TEXT=1)
    assert struct.unpack_from("<I", packed, 0)[0] == 1
    # hItem @ 8 (HTREEITEM = uint64)
    assert struct.unpack_from("<Q", packed, 8)[0] == sentinel_item
    # pszText @ 24 (LPWSTR = uint64 pointer) — THIS is the bit Wave A.1b
    # got wrong; the misaligned offset broke text reads silently.
    assert struct.unpack_from("<Q", packed, 24)[0] == sentinel_pszText, (
        "pszText must land at offset 24; misalignment causes MT5 to read "
        "garbage and write the item text to a bogus address."
    )
    # cchTextMax @ 32 (int)
    assert struct.unpack_from("<i", packed, 32)[0] == sentinel_cch
    # lParam @ 48 (LPARAM = int64)
    assert struct.unpack_from("<q", packed, 48)[0] == 0


# ---------------------------------------------------------------------------
# find_navigator_tree — locate the SysTreeView32 inside Navigator panel
# ---------------------------------------------------------------------------


def _fake_win32_with_children(monkeypatch, children: list[tuple[int, str]]):
    """Inject a fake pywin32 where EnumChildWindows yields the given
    (hwnd, class_name) pairs for any parent."""
    _purge_chart_cache()
    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.GetWindowText.return_value = ""
    fake_gui.GetClassName.side_effect = lambda h: dict(children).get(h, "")
    fake_gui.PostMessage.return_value = 1
    fake_gui.SendMessage.return_value = 0

    def enum_children(_parent, cb, _extra):
        for hwnd, _cls in children:
            cb(hwnd, None)
    fake_gui.EnumChildWindows.side_effect = enum_children

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con",
                        types.SimpleNamespace(MF_BYPOSITION=0x0400))
    monkeypatch.setitem(sys.modules, "win32process", MagicMock())
    return fake_gui


def test_find_navigator_tree_locates_sys_tree_view32(monkeypatch):
    """Happy path: Navigator panel contains a SysTreeView32 child."""
    _fake_win32_with_children(monkeypatch, [
        (1001, "SysTabControl32"),
        (1002, "SysTreeView32"),
        (1003, "SysListView32"),
        (1004, "SysHeader32"),
    ])
    from mt5_cli.chart._navigator_walk import find_navigator_tree
    tree_hwnd = find_navigator_tree(navigator_panel_hwnd=999)
    assert tree_hwnd == 1002


def test_find_navigator_tree_returns_none_when_absent(monkeypatch):
    """No SysTreeView32 child → return None so the caller can decide
    whether to fall back to menu_legacy."""
    _fake_win32_with_children(monkeypatch, [
        (1001, "SysTabControl32"),
        (1003, "SysListView32"),
    ])
    from mt5_cli.chart._navigator_walk import find_navigator_tree
    assert find_navigator_tree(navigator_panel_hwnd=999) is None


# ---------------------------------------------------------------------------
# attach_via_navigator — orchestrates the full right-click + ENTER flow
# ---------------------------------------------------------------------------


def _setup_attach_environment(monkeypatch, navigator_tree, *,
                              ea_name: str = "SmartFibChandelierManager",
                              mt5_pid: int = 5000,
                              mt5_tid: int = 6000,
                              popup_hwnd: int | None = 99999,
                              popup_owner_pid: int | None = None,
                              popup_owner_tid: int | None = None,
                              drift_to: str | None = None):
    """Wire fake pywin32 + popup-discovery for attach_via_navigator tests."""
    _purge_chart_cache()
    fake_gui = MagicMock(name="win32gui")
    fake_gui.IsWindowVisible.return_value = True
    fake_gui.PostMessage.return_value = 1
    fake_gui.SendMessage.return_value = 0
    fake_gui.GetWindowText.return_value = ""

    # EnumWindows yields the popup hwnd once it "appears"
    popup_visible = {"appeared": popup_hwnd is not None}

    def enum_windows(cb, _extra):
        if popup_visible["appeared"] and popup_hwnd is not None:
            # Simulate class-name check: only return the popup hwnd
            fake_gui.GetClassName.side_effect = (
                lambda h: "#32768" if h == popup_hwnd else ""
            )
            cb(popup_hwnd, None)
    fake_gui.EnumWindows.side_effect = enum_windows

    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    monkeypatch.setitem(sys.modules, "win32con",
                        types.SimpleNamespace(MF_BYPOSITION=0x0400))

    fake_process = MagicMock(name="win32process")
    owner_pid = popup_owner_pid if popup_owner_pid is not None else mt5_pid
    owner_tid = popup_owner_tid if popup_owner_tid is not None else mt5_tid
    fake_process.GetWindowThreadProcessId.side_effect = lambda h: (
        owner_tid, owner_pid,
    ) if h == popup_hwnd else (0, 0)
    monkeypatch.setitem(sys.modules, "win32process", fake_process)

    # Simulate the right-click auto-selecting the target item; or, when
    # drift_to is set, simulate selection landing on a different item
    target_item = None
    if ea_name:
        from mt5_cli.chart._navigator_walk import find_ea_node
        target_item = find_ea_node(navigator_tree, ea_name)
        if drift_to is not None:
            drift_item = find_ea_node(navigator_tree, drift_to)
            navigator_tree.set_selected(drift_item)
        elif target_item is not None:
            navigator_tree.set_selected(target_item)

    return fake_gui, fake_process, target_item


def test_attach_via_navigator_happy_path(monkeypatch, navigator_tree):
    """Happy path: EA found in tree, right-click sent, popup appears
    + ownership passes + selection drift check passes, VK_RETURN sent
    to popup. Envelope reports method='nav_tree_rclick_enter'."""
    fake_gui, fake_process, target_item = _setup_attach_environment(
        monkeypatch, navigator_tree,
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="SmartFibChandelierManager",
        mt5_pid=5000,
        mt5_tid=6000,
    )

    assert result["ok"] is True
    assert result["data"]["method"] == "nav_tree_rclick_enter"
    assert result["data"]["ea"] == "SmartFibChandelierManager"

    # Verify ENTER (VK_RETURN = 0x0D) keystroke was posted to popup
    enter_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D
    ]
    assert enter_calls, "VK_RETURN must be posted to popup on happy path"


def test_attach_via_navigator_fails_when_ea_not_in_tree(
    monkeypatch, navigator_tree,
):
    """EA name not present in Navigator → NAV_EA_NOT_FOUND, no right-click."""
    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree, ea_name=None,
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="NotAnEAName",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NAV_EA_NOT_FOUND"

    # No right-click WM_RBUTTONDOWN should be sent if EA wasn't found
    rbutton_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] in (0x0204, 0x0205)  # WM_RBUTTONDOWN, WM_RBUTTONUP
    ]
    assert not rbutton_calls


def test_attach_via_navigator_fails_popup_ownership_mismatch(
    monkeypatch, navigator_tree,
):
    """Popup appeared but PID doesn't match MT5 → NAV_POPUP_OWNERSHIP_MISMATCH,
    no VK_RETURN sent (we don't drive popups we don't own)."""
    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree,
        popup_owner_pid=99999,  # different from mt5_pid=5000
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="SmartFibChandelierManager",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NAV_POPUP_OWNERSHIP_MISMATCH"

    # NO ENTER should have been sent to a popup we don't own
    enter_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D
    ]
    assert not enter_calls


def test_attach_via_navigator_fails_popup_never_appears(
    monkeypatch, navigator_tree,
):
    """Right-click sent but no #32768 popup appears within budget →
    NAV_POPUP_NOT_FOUND."""
    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree,
        popup_hwnd=None,   # never appears
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="SmartFibChandelierManager",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NAV_POPUP_NOT_FOUND"


def test_attach_via_navigator_ensure_visible_before_item_rect(
    monkeypatch, navigator_tree,
):
    """Per Wave A.1d (live-caught 2026-05-18): TVM_GETITEMRECT returns
    NONE for items inside collapsed folders, so attach_via_navigator
    MUST call ensure_visible(target_item) BEFORE item_rect() to expand
    the matched item's parent chain. Otherwise the rect comes back
    (0,0,0,0), the click defaults to (cx_fallback, 0), and the click
    lands on whichever item happens to be at y=0 instead of the target."""
    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree,
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator, find_ea_node
    target = find_ea_node(navigator_tree, "MyNestedEA")
    attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="MyNestedEA",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    ensured = getattr(navigator_tree, "_ensured_visible", [])
    assert target in ensured, (
        f"attach_via_navigator must call ensure_visible({target}) for the "
        "matched item before reading its rect; collapsed parents return "
        "zero-rect from TVM_GETITEMRECT and the click misses."
    )


def test_attach_via_navigator_fails_zero_rect_after_ensure_visible(
    monkeypatch, navigator_tree,
):
    """Defensive: if item_rect() still returns (0,0,0,0) even after
    ensure_visible (e.g. tree itself is hidden, or some other layout
    pathology), MUST fail with NAV_TREE_RECT_ZERO rather than send a
    blind click at (cx_fallback, 0). Prevents the same wrong-item
    attach the original bug demonstrated."""
    # Inject a node whose item_rect returns all zeros even after ensure_visible
    experts = [i for i, (t, _) in navigator_tree._nodes.items()
               if t == "Expert Advisors"][0]
    bad_item = navigator_tree.add("ZeroRectEA", parent=experts,
                                  rect=(0, 0, 0, 0))

    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree, ea_name="ZeroRectEA",
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="ZeroRectEA",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NAV_TREE_RECT_ZERO"

    # And NO right-click should have fired against a zero rect
    rbutton_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] in (0x0204, 0x0205)
    ]
    assert not rbutton_calls


def test_attach_via_navigator_dismisses_popup_on_selection_drift(
    monkeypatch, navigator_tree,
):
    """If TVGN_CARET re-read shows we landed on a different item than
    expected (concurrent tree change), dismiss the popup with VK_ESCAPE
    and fail NAV_TREE_SELECTION_DRIFT — never send VK_RETURN under drift."""
    fake_gui, _, _ = _setup_attach_environment(
        monkeypatch, navigator_tree,
        drift_to="AdaptiveTrailEA",   # selection drifted from SmartFib
    )

    from mt5_cli.chart._navigator_walk import attach_via_navigator
    result = attach_via_navigator(
        reader=navigator_tree,
        tree_hwnd=12345,
        ea_name="SmartFibChandelierManager",
        mt5_pid=5000,
        mt5_tid=6000,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "NAV_TREE_SELECTION_DRIFT"
    assert "SmartFibChandelierManager" in result["error"]["message"]
    assert "AdaptiveTrailEA" in result["error"]["message"]

    # VK_ESCAPE (0x1B) MUST have been sent to dismiss the dangling popup
    escape_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x1B
    ]
    assert escape_calls, "VK_ESCAPE must be sent to dismiss popup on drift"

    # And VK_RETURN must NOT have been sent under drift
    enter_calls = [
        c for c in fake_gui.PostMessage.call_args_list
        if c.args[1] == 0x0100 and c.args[2] == 0x0D
    ]
    assert not enter_calls
