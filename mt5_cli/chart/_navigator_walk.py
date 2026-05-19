"""Navigator panel tree walk + right-click activation for attach-ea.

The legacy attach_ea walked MT5's Insert > Experts menu, which MT5
populates at STARTUP from disk and never refreshes — newly deployed EAs
never appear there until MT5 restarts. This module replaces that path:
the Navigator panel's SysTreeView32 is filesystem-aware and always
reflects MQL5/Experts/ content. We find the EA there and synthesize the
right-click → Enter (Attach to Chart, the menu's default item) flow.

Bridge isolation: pure Win32 (lazy-imported pywin32). Never touches the
MT5 Python SDK.

Constants are empirical from Claude's probe on Trading.com MT5 build,
2026-05-18. See test_chart_navigator_walk.py for regression locks.

The ctypes-backed real NavigatorTreeReader (TVM_GETITEMRECT, 64-bit
VirtualAllocEx + SendMessageW for cross-process tree reads) is exercised
live during operator confirmation, not in pytest — that surface is the
intentional gap acknowledged in the Wave A.1 contract.
"""
from __future__ import annotations

import time
from typing import Protocol

from mt5_cli.reports import fail, ok

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

# CRITICAL: TVM_GETITEMRECT = TV_FIRST + 4 = 0x1104. NOT 0x1004 — that's
# ListView LVM_GETSUBITEMRECT and silently returns garbage when sent to
# a TreeView. Claude burned probe cycles on this typo; locked via
# regression test test_tvm_getitemrect_constant_is_0x1104.
TVM_GETITEMRECT = 0x1104

# TreeView traversal messages (TV_FIRST + N)
TVM_GETNEXTITEM = 0x110A
TVGN_ROOT = 0x0000
TVGN_NEXT = 0x0001
TVGN_CHILD = 0x0004
TVGN_CARET = 0x0009

# Generic Win32 input
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B

# ---------------------------------------------------------------------------
# Empirical timing constants (Trading.com MT5 build, probed 2026-05-18)
# ---------------------------------------------------------------------------

# Tree's internal selection state lags PostMessage WM_RBUTTONDOWN by
# ~20ms; without this settle, TVGN_CARET re-read races the click and
# can falsely flag NAV_TREE_SELECTION_DRIFT.
TREE_SELECTION_SETTLE_SECONDS = 0.02

# Hard budget for the #32768 right-click popup to appear. Claude's
# 5-trial probe measured 8.9-12.9ms avg ~11ms; 150ms is ~14x the
# observed avg so we cover MT5 under load and slower machines.
POPUP_APPEAR_TIMEOUT_SECONDS = 0.15

# Retry pattern inside the popup budget: initial sleep covers the
# common case in one shot, poll handles the rare slow case.
_POPUP_INITIAL_SLEEP_SECONDS = 0.05
_POPUP_POLL_INTERVAL_SECONDS = 0.01

# Folder text used by the tree walker; lowercase, matched
# case-insensitively. Locale-sensitive: non-English MT5 builds may use
# a localized label here. Out of scope for Wave A.1; if it surfaces in
# the field, we add a locale table.
_EXPERTS_FOLDER_TEXT = "expert advisors"


def _win32():
    """Lazy pywin32 import, mirroring mt5_cli.chart.chart._win32 pattern."""
    import win32con  # noqa: PLC0415
    import win32gui  # noqa: PLC0415
    import win32process  # noqa: PLC0415
    return win32gui, win32con, win32process


# ---------------------------------------------------------------------------
# NavigatorTreeReader interface (production = ctypes; tests = in-memory fake)
# ---------------------------------------------------------------------------


class NavigatorTreeReader(Protocol):
    """Interface for reading the Navigator's SysTreeView32.

    Production wires this to a ctypes-backed implementation that
    cross-process-reads tree items via TVM_GETITEMRECT etc. Tests
    inject FakeNavigatorTreeReader (in-memory). This split makes the
    pure-logic tree walk and activation orchestration hermetically
    testable without mocking the entire ctypes surface.
    """

    def root_item(self) -> int | None:
        ...

    def first_child(self, item: int) -> int | None:
        ...

    def next_sibling(self, item: int) -> int | None:
        ...

    def item_text(self, item: int) -> str:
        ...

    def item_rect(self, item: int) -> tuple[int, int, int, int]:
        ...

    def selected_item(self) -> int | None:
        ...


# ---------------------------------------------------------------------------
# find_navigator_tree — Navigator panel → SysTreeView32 hwnd
# ---------------------------------------------------------------------------


def find_navigator_tree(navigator_panel_hwnd: int) -> int | None:
    """EnumChildWindows on the Navigator dockable panel for its
    SysTreeView32 child. Returns the tree hwnd or None.

    Caller decides whether None means "fall back to menu_legacy" or
    "fail closed" — this function reports observation only.
    """
    win32gui, _, _ = _win32()
    found: list[int] = []

    def cb(hwnd, _extra):
        try:
            if win32gui.GetClassName(hwnd) == "SysTreeView32":
                found.append(hwnd)
        except Exception:  # noqa: BLE001
            pass

    win32gui.EnumChildWindows(navigator_panel_hwnd, cb, None)
    return found[0] if found else None


# ---------------------------------------------------------------------------
# find_ea_node — pure-logic tree walk
# ---------------------------------------------------------------------------


def find_ea_node(reader: NavigatorTreeReader, ea_name: str) -> int | None:
    """Walk Navigator tree to find the EA leaf node under Expert Advisors.

    Tree shape (per Claude's empirical probe):
      root = 'MetaTrader 5'
        children: Accounts, Indicators, Expert Advisors, Services, Scripts
          under Expert Advisors:
            folder children (Advisors, Examples, Free Robots, ...) — may
              contain nested EAs
            flat user-EA leaves

    Match is case-insensitive on text. DFS-descends folders so EAs
    nested under Advisors/Examples/Free Robots are found.

    Returns the matching tree item handle or None.
    """
    root = reader.root_item()
    if root is None:
        return None
    target_lower = ea_name.lower()

    # Find the 'Expert Advisors' folder among root's direct children.
    experts_folder: int | None = None
    child = reader.first_child(root)
    while child is not None:
        if reader.item_text(child).lower() == _EXPERTS_FOLDER_TEXT:
            experts_folder = child
            break
        child = reader.next_sibling(child)
    if experts_folder is None:
        return None

    # DFS under Expert Advisors. Stack holds "next node to visit"; each
    # iteration walks siblings via next_sibling, descends into children
    # via first_child.
    stack: list[int | None] = [reader.first_child(experts_folder)]
    while stack:
        node = stack.pop()
        while node is not None:
            if reader.item_text(node).lower() == target_lower:
                return node
            kid = reader.first_child(node)
            if kid is not None:
                # Save sibling for later, descend now
                sibling = reader.next_sibling(node)
                if sibling is not None:
                    stack.append(sibling)
                node = kid
                continue
            node = reader.next_sibling(node)
    return None


# ---------------------------------------------------------------------------
# attach_via_navigator — full right-click + Enter orchestration
# ---------------------------------------------------------------------------


def _find_popup(win32gui) -> int | None:
    found: list[int] = []

    def cb(hwnd, _extra):
        try:
            if win32gui.GetClassName(hwnd) == "#32768":
                found.append(hwnd)
        except Exception:  # noqa: BLE001
            pass

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def _wait_for_popup(win32gui) -> int | None:
    """Poll for the right-click popup with retry inside the hard timeout.

    Initial sleep covers the common-case ~11ms appearance in one shot,
    then poll every 10ms until POPUP_APPEAR_TIMEOUT_SECONDS expires.
    """
    time.sleep(_POPUP_INITIAL_SLEEP_SECONDS)
    elapsed = _POPUP_INITIAL_SLEEP_SECONDS
    popup = _find_popup(win32gui)
    while popup is None and elapsed < POPUP_APPEAR_TIMEOUT_SECONDS:
        time.sleep(_POPUP_POLL_INTERVAL_SECONDS)
        elapsed += _POPUP_POLL_INTERVAL_SECONDS
        popup = _find_popup(win32gui)
    return popup


def attach_via_navigator(
    *,
    reader: NavigatorTreeReader,
    tree_hwnd: int,
    ea_name: str,
    mt5_pid: int,
    mt5_tid: int,
) -> dict:
    """Right-click the EA in Navigator tree → Enter activates 'Attach to Chart'.

    'Attach to Chart' is item #1 in the EA's right-click context menu
    on Trading.com's build (probably MT5 invariant): it's the menu's
    DEFAULT highlighted action, so VK_RETURN alone activates it — no
    DOWN-arrow navigation needed and the activation is portable across
    builds because we target the default action, not a positional index.

    Failure codes (all authoritative for the Navigator path — caller
    must NOT silently fall back to menu_legacy on any of these):
      NAV_EA_NOT_FOUND               EA not in Navigator tree
      NAV_POPUP_NOT_FOUND            #32768 popup never appeared in budget
      NAV_POPUP_OWNERSHIP_MISMATCH   popup PID/TID don't match MT5 — not ours
      NAV_TREE_SELECTION_DRIFT       caret post-click landed on a different
                                     item than expected; popup VK_ESCAPE'd
    """
    win32gui, _, win32process = _win32()

    # G0 — pure-logic find. No Win32 yet.
    target_item = find_ea_node(reader, ea_name)
    if target_item is None:
        return fail(
            "NAV_EA_NOT_FOUND",
            f"EA {ea_name!r} not found in Navigator's Expert Advisors tree.",
        )
    expected_text = reader.item_text(target_item)

    # Click at center of item's rect (client-area coords per probe).
    left, top, right, bottom = reader.item_rect(target_item)
    cx = (left + right) // 2 if right > left else 146
    cy = (top + bottom) // 2
    lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)

    win32gui.PostMessage(tree_hwnd, WM_RBUTTONDOWN, 0, lparam)
    win32gui.PostMessage(tree_hwnd, WM_RBUTTONUP, 0, lparam)

    # Settle tree's internal selection state before the G2 caret re-read.
    time.sleep(TREE_SELECTION_SETTLE_SECONDS)

    # Wait for #32768 popup within the hard timeout budget.
    popup_hwnd = _wait_for_popup(win32gui)
    if popup_hwnd is None:
        return fail(
            "NAV_POPUP_NOT_FOUND",
            f"Right-click sent to Navigator tree but no #32768 popup "
            f"appeared within {int(POPUP_APPEAR_TIMEOUT_SECONDS * 1000)}ms.",
        )

    # G1 — popup ownership: PID + TID both must match MT5. Belt-and-suspenders.
    # GW_OWNER is captured below as diagnostic-only; never a gate (per Claude
    # probe, MT5 internal-spawn popups may have GW_OWNER == 0).
    try:
        popup_tid, popup_pid = win32process.GetWindowThreadProcessId(popup_hwnd)
    except Exception as exc:  # noqa: BLE001
        return fail(
            "NAV_POPUP_OWNERSHIP_MISMATCH",
            f"Could not read popup ownership: {exc!r}",
            data={"popup_hwnd": popup_hwnd},
        )
    if popup_pid != mt5_pid or popup_tid != mt5_tid:
        return fail(
            "NAV_POPUP_OWNERSHIP_MISMATCH",
            f"Navigator popup hwnd={popup_hwnd} owner mismatch "
            f"(expected MT5 pid={mt5_pid} tid={mt5_tid}, "
            f"got pid={popup_pid} tid={popup_tid}).",
            data={"popup_hwnd": popup_hwnd,
                  "popup_pid": popup_pid, "popup_tid": popup_tid},
        )

    # G2 — selection drift: caret should now be on the item we clicked.
    selected = reader.selected_item()
    if selected != target_item:
        actual_text = (
            reader.item_text(selected) if selected is not None else "(none)"
        )
        # Dismiss the dangling popup cleanly so the operator isn't left
        # with a stuck menu on screen.
        win32gui.PostMessage(popup_hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
        win32gui.PostMessage(popup_hwnd, WM_KEYUP, VK_ESCAPE, 0)
        return fail(
            "NAV_TREE_SELECTION_DRIFT",
            f"Navigator selection drift: expected {expected_text!r}, "
            f"actual {actual_text!r}. Popup dismissed with VK_ESCAPE.",
            data={"expected": expected_text, "actual": actual_text,
                  "popup_hwnd": popup_hwnd},
        )

    # Both gates green → activate the default item (Attach to Chart).
    win32gui.PostMessage(popup_hwnd, WM_KEYDOWN, VK_RETURN, 0)
    win32gui.PostMessage(popup_hwnd, WM_KEYUP, VK_RETURN, 0)

    return ok({
        "method": "nav_tree_rclick_enter",
        "ea": expected_text,
        "popup_hwnd": popup_hwnd,
        "tree_item_rect": (left, top, right, bottom),
    })
