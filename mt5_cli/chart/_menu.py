"""Win32 main-menu walking helpers for the chart submodule.

Private to mt5_cli.chart. Used by:
- mt5_cli.chart.indicators_attach (Insert > Indicators > Custom > <name>)
- mt5_cli.chart.new_chart        (File > New Chart > <symbol>)

Bridge isolation: pure Win32 ctypes + pywin32. No MT5 SDK touch.

All public functions in this module use normalized EXACT match at each
menu segment, never substring. Substring would let a user-deployed
indicator name `MyATR` collide with the built-in `ATR` and post the
wrong WM_COMMAND.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

MF_BYPOSITION = 0x0400


def normalize_menu_text(text: str) -> str:
    """Lowercase, strip '&' accelerator markers, collapse whitespace,
    and drop the keyboard-shortcut suffix after the tab character.
    Used to compare menu labels against caller-supplied target names."""
    return " ".join(text.replace("&", "").split()).split("\t", 1)[0].strip().lower()


def menu_string(hmenu: int, index: int) -> str:
    """Read a menu item's display text via GetMenuStringW (Win32 ctypes)."""
    user32 = ctypes.windll.user32
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetMenuStringW(
        wintypes.HMENU(hmenu),
        wintypes.UINT(index),
        buffer,
        ctypes.sizeof(buffer) // ctypes.sizeof(ctypes.c_wchar),
        wintypes.UINT(MF_BYPOSITION),
    )
    return buffer.value


def find_submenu(parent_hmenu: int, name_lower: str):
    """Return the submenu hmenu under `parent_hmenu` whose normalized
    label exactly matches `name_lower`, or None if not found."""
    import win32gui  # noqa: PLC0415 (lazy; mocked at sys.modules in tests)
    count = win32gui.GetMenuItemCount(parent_hmenu)
    for i in range(count):
        if normalize_menu_text(menu_string(parent_hmenu, i)) == name_lower:
            submenu = win32gui.GetSubMenu(parent_hmenu, i)
            if submenu:
                return submenu
    return None


def find_leaf_command_id(parent_hmenu: int, leaf_name_lower: str):
    """Return the WM_COMMAND id for a leaf menu item under `parent_hmenu`
    whose normalized label exactly matches `leaf_name_lower`, or None."""
    import win32gui  # noqa: PLC0415
    count = win32gui.GetMenuItemCount(parent_hmenu)
    for i in range(count):
        if normalize_menu_text(menu_string(parent_hmenu, i)) == leaf_name_lower:
            command_id = win32gui.GetMenuItemID(parent_hmenu, i)
            if command_id != -1:
                return int(command_id)
    return None


def find_leaf_command_id_recursive(parent_hmenu: int, leaf_name_lower: str):
    """Recursively search `parent_hmenu` AND all nested submenus for a leaf
    whose normalized label exactly matches `leaf_name_lower`. Returns the
    first match's command_id, or None.

    Used for File > New Chart where the symbol may be a top-level favorite
    OR nested under a category submenu (Forex, Indices, Stocks, etc.).
    Pre-order: check the current level first, then descend into children
    left-to-right. This biases toward the most accessible match.
    """
    import win32gui  # noqa: PLC0415
    direct = find_leaf_command_id(parent_hmenu, leaf_name_lower)
    if direct is not None:
        return direct
    count = win32gui.GetMenuItemCount(parent_hmenu)
    for i in range(count):
        submenu = win32gui.GetSubMenu(parent_hmenu, i)
        if submenu:
            found = find_leaf_command_id_recursive(submenu, leaf_name_lower)
            if found is not None:
                return found
    return None
