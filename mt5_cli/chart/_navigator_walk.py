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

# TVM_ENSUREVISIBLE = TV_FIRST + 20 = 0x1114. Expands parent chain +
# scrolls into view so TVM_GETITEMRECT returns a non-zero rect for the
# matched item. Without it, items under collapsed folders give zero rect
# and the click misses (Wave A.1d, caught 2026-05-18 on ExpertMACD).
TVM_ENSUREVISIBLE = 0x1114

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

# Safe X-coordinate fallback for the right-click WM_RBUTTONDOWN lParam
# when reader.item_rect returns a degenerate (right <= left) rect.
# Value is half the 292px Navigator tree client width Claude measured
# during the 2026-05-18 probe; any X inside the item's row triggers
# the same row-level right-click context menu.
_ITEM_CENTER_X_FALLBACK = 146


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

    def ensure_visible(self, item: int) -> None:
        """Expand the item's parent chain and scroll if needed so
        TVM_GETITEMRECT returns a meaningful rect. Without this,
        items inside collapsed folders return (0,0,0,0) from
        item_rect() and the click defaults to (cx_fallback, 0) —
        landing on whatever item happens to occupy the top of the
        tree instead of the matched target. Caught live 2026-05-18
        on ExpertMACD under collapsed Advisors folder."""
        ...


# Additional TreeView messages for the ctypes-backed real reader
TVM_GETITEMW = 0x113E  # Unicode variant
TVIF_TEXT = 0x0001

# Process access rights for OpenProcess (kernel32)
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020

# VirtualAllocEx / VirtualFreeEx flags
MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


def _build_tvitemw_struct(item: int, pszText_remote: int,
                          cch_text_max_chars: int) -> bytes:
    """Pack a TVITEMW struct for 64-bit Windows.

    Layout (natural alignment, 64-bit):
      offset  size  field
      0       4     UINT mask
      4       4     pad
      8       8     HTREEITEM hItem
      16      4     UINT state
      20      4     UINT stateMask
      24      8     LPWSTR pszText (remote pointer)
      32      4     int cchTextMax (in WCHARs)
      36      4     int iImage
      40      4     int iSelectedImage
      44      4     int cChildren
      48      8     LPARAM lParam
    Total: 56 bytes.

    Asks for TEXT only via mask=TVIF_TEXT (0x0001).
    """
    import struct  # noqa: PLC0415
    # 56-byte TVITEMW for x64 — pszText MUST land at offset 24 and
    # cchTextMax at offset 32 for MT5's TVM_GETITEMW to read them
    # correctly. Regression-locked by test_tvitemw_struct_is_56_bytes
    # and test_tvitemw_struct_field_offsets. Wave A.1b shipped with
    # spurious 8x and 4x padding that produced a 68-byte struct: pszText
    # was displaced by +8 bytes (to offset 32), and the trailing fields
    # iImage/iSelectedImage/cChildren/lParam were displaced by the full
    # +12 bytes. Net effect: silently broke item_text() on the live
    # Trading.com MT5 (caught 2026-05-18 during operator confirm).
    return struct.pack(
        "<I4xQIIQIIIIQ",
        TVIF_TEXT,           # mask              @ 0
        item,                # hItem             @ 8
        0,                   # state             @ 16
        0,                   # stateMask         @ 20
        pszText_remote,      # pszText           @ 24
        cch_text_max_chars,  # cchTextMax        @ 32 (in WCHARs)
        0,                   # iImage            @ 36
        0,                   # iSelectedImage    @ 40
        0,                   # cChildren         @ 44
        0,                   # lParam            @ 48
    )


class Win32NavigatorTreeReader:
    """ctypes-backed cross-process reader for MT5's Navigator SysTreeView32.

    Pattern: OpenProcess(MT5) → VirtualAllocEx remote buffers →
    WriteProcessMemory the request → SendMessageW the tree → ReadProcessMemory
    the response → VirtualFreeEx → CloseHandle on exit.

    64-bit pitfalls codified per Claude's probe 2026-05-18:
      - HTREEITEM is 8 bytes on 64-bit; pack as little-endian Q
      - VirtualAllocEx.restype = c_size_t (avoid 32-bit address truncation)
      - SendMessageW argtypes pin lParam to c_ssize_t for full 64-bit width
      - TVITEMW struct has natural-alignment padding (see _build_tvitemw_struct)

    This implementation has NO hermetic tests — the cross-process Win32
    surface is verified live during operator confirmation. Wave A.1
    contract acknowledges this gap explicitly. The orchestration that
    uses this reader IS hermetically tested via FakeNavigatorTreeReader.
    """

    _TEXT_BUFFER_BYTES = 260 * 2   # MAX_PATH WCHARs
    _RECT_BUFFER_BYTES = 16         # 4 LONGs
    _TVITEMW_BYTES = 56

    def __init__(self, tree_hwnd: int, mt5_pid: int):
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        self._tree_hwnd = tree_hwnd
        self._mt5_pid = mt5_pid
        self._ctypes = ctypes

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

        # CRITICAL pinning per Claude's probe:
        # VirtualAllocEx returns a pointer — restype must be c_size_t,
        # NOT the default c_int, to avoid 32-bit truncation of high addresses.
        self._kernel32.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t,
            wintypes.DWORD, wintypes.DWORD,
        ]
        self._kernel32.VirtualAllocEx.restype = ctypes.c_size_t

        self._kernel32.VirtualFreeEx.argtypes = [
            wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD,
        ]
        self._kernel32.VirtualFreeEx.restype = wintypes.BOOL

        self._kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.WriteProcessMemory.restype = wintypes.BOOL

        self._kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.ReadProcessMemory.restype = wintypes.BOOL

        # SendMessageW: lParam pinned to c_ssize_t for full 64-bit width
        # so we can pass remote pointers as lParam without truncation.
        self._user32.SendMessageW.argtypes = [
            ctypes.c_size_t, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
        ]
        self._user32.SendMessageW.restype = ctypes.c_ssize_t

        self._h_process = self._kernel32.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
            False, mt5_pid,
        )
        if not self._h_process:
            raise OSError(
                f"OpenProcess(pid={mt5_pid}) failed: "
                f"WinError {ctypes.get_last_error()}"
            )

    # Context-manager support so the caller can `with Win32NavigatorTreeReader(...)`
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self) -> None:
        if getattr(self, "_h_process", None):
            self._kernel32.CloseHandle(self._h_process)
            self._h_process = None

    # ---- Reader interface ------------------------------------------------

    def _send(self, msg: int, wparam: int = 0, lparam: int = 0) -> int:
        return int(self._user32.SendMessageW(
            self._tree_hwnd, msg, wparam, lparam,
        ))

    def root_item(self) -> int | None:
        h = self._send(TVM_GETNEXTITEM, TVGN_ROOT, 0)
        return h if h else None

    def first_child(self, item: int) -> int | None:
        h = self._send(TVM_GETNEXTITEM, TVGN_CHILD, item)
        return h if h else None

    def next_sibling(self, item: int) -> int | None:
        h = self._send(TVM_GETNEXTITEM, TVGN_NEXT, item)
        return h if h else None

    def selected_item(self) -> int | None:
        h = self._send(TVM_GETNEXTITEM, TVGN_CARET, 0)
        return h if h else None

    def ensure_visible(self, item: int) -> None:
        """TVM_ENSUREVISIBLE expands the item's parent chain and
        scrolls so its rect is laid out. Side effect contained: only
        the matched item's ancestors expand; siblings/unrelated
        folders are unaffected."""
        self._send(TVM_ENSUREVISIBLE, 0, item)

    def item_text(self, item: int) -> str:
        ctypes = self._ctypes
        text_remote = self._kernel32.VirtualAllocEx(
            self._h_process, 0, self._TEXT_BUFFER_BYTES,
            MEM_COMMIT, PAGE_READWRITE,
        )
        if not text_remote:
            return ""
        tvitem_remote = self._kernel32.VirtualAllocEx(
            self._h_process, 0, self._TVITEMW_BYTES,
            MEM_COMMIT, PAGE_READWRITE,
        )
        if not tvitem_remote:
            self._kernel32.VirtualFreeEx(
                self._h_process, text_remote, 0, MEM_RELEASE,
            )
            return ""
        try:
            cch = self._TEXT_BUFFER_BYTES // 2
            struct_bytes = _build_tvitemw_struct(item, text_remote, cch)
            buf_local = (ctypes.c_ubyte * len(struct_bytes)).from_buffer_copy(
                struct_bytes,
            )
            written = ctypes.c_size_t(0)
            self._kernel32.WriteProcessMemory(
                self._h_process, tvitem_remote, buf_local,
                len(struct_bytes), ctypes.byref(written),
            )
            self._send(TVM_GETITEMW, 0, tvitem_remote)
            text_local = (ctypes.c_uint16 * cch)()
            self._kernel32.ReadProcessMemory(
                self._h_process, text_remote, text_local,
                self._TEXT_BUFFER_BYTES, ctypes.byref(written),
            )
            chars: list[str] = []
            for ch in text_local:
                if ch == 0:
                    break
                chars.append(chr(ch))
            return "".join(chars)
        finally:
            self._kernel32.VirtualFreeEx(
                self._h_process, tvitem_remote, 0, MEM_RELEASE,
            )
            self._kernel32.VirtualFreeEx(
                self._h_process, text_remote, 0, MEM_RELEASE,
            )

    def item_rect(self, item: int) -> tuple[int, int, int, int]:
        """TVM_GETITEMRECT with HTREEITEM packed at offset 0 of the
        returned RECT buffer. Returns (left, top, right, bottom)
        client-area coords per Claude probe.
        """
        ctypes = self._ctypes
        rect_remote = self._kernel32.VirtualAllocEx(
            self._h_process, 0, self._RECT_BUFFER_BYTES,
            MEM_COMMIT, PAGE_READWRITE,
        )
        if not rect_remote:
            return (0, 0, 0, 0)
        try:
            import struct  # noqa: PLC0415
            hitem_packed = struct.pack("<Q", item)
            buf_local = (ctypes.c_ubyte * 8).from_buffer_copy(hitem_packed)
            written = ctypes.c_size_t(0)
            self._kernel32.WriteProcessMemory(
                self._h_process, rect_remote, buf_local, 8,
                ctypes.byref(written),
            )
            # wParam=False (0) → full-row rect; pass True (1) for item-only.
            # Full-row gives the click target we want.
            self._send(TVM_GETITEMRECT, 0, rect_remote)
            rect_local = (ctypes.c_long * 4)()
            self._kernel32.ReadProcessMemory(
                self._h_process, rect_remote, rect_local,
                self._RECT_BUFFER_BYTES, ctypes.byref(written),
            )
            return (
                int(rect_local[0]), int(rect_local[1]),
                int(rect_local[2]), int(rect_local[3]),
            )
        finally:
            self._kernel32.VirtualFreeEx(
                self._h_process, rect_remote, 0, MEM_RELEASE,
            )


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


def find_navigator_panel(mt5_main_hwnd: int) -> int | None:
    """Walk MT5's child windows for the dockable Navigator panel.

    The panel's title bar contains 'Navigator' (case-insensitive).
    Locale-sensitive — non-English MT5 builds may use a localized
    label here; out of scope for Wave A.1.
    """
    win32gui, _, _ = _win32()
    found: list[int] = []

    def cb(hwnd, _extra):
        try:
            title = win32gui.GetWindowText(hwnd) or ""
        except Exception:  # noqa: BLE001
            return
        if "navigator" in title.lower():
            found.append(hwnd)

    win32gui.EnumChildWindows(mt5_main_hwnd, cb, None)
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
      NAV_TREE_RECT_ZERO             item_rect returned (0,0,0,0) even
                                     after ensure_visible — geometry
                                     unreadable; refusing to click blind
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

    # Wave A.1d: ensure the matched item is laid out before reading geometry.
    # Items inside collapsed folders return zero rect from TVM_GETITEMRECT;
    # this expands the parent chain only (no sibling/unrelated effects).
    reader.ensure_visible(target_item)

    # Click at center of item's rect (client-area coords per probe).
    left, top, right, bottom = reader.item_rect(target_item)
    if (left, top, right, bottom) == (0, 0, 0, 0):
        return fail(
            "NAV_TREE_RECT_ZERO",
            f"item_rect for EA {ea_name!r} still (0,0,0,0) after "
            "ensure_visible — tree geometry unreadable. Refusing to "
            "synthesize a click at a fallback coordinate that would "
            "land on an unrelated item.",
            data={"target_item": target_item, "expected": expected_text},
        )
    cx = (left + right) // 2 if right > left else _ITEM_CENTER_X_FALLBACK
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
    # GW_OWNER deliberately NOT used as a gate: per Claude's 2026-05-18 probe
    # on Trading.com's MT5 build, popups spawned internally by MT5 return
    # GW_OWNER == 0 even though they're legitimate. PID/TID match is the
    # reliable signal.
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
