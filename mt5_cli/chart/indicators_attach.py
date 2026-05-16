"""Chart-indicator attach via Win32 GUI menu poking.

The MetaTrader5 Python SDK does NOT expose programmatic indicator
attachment (iCustom / ChartIndicatorAdd / ChartIndicatorDelete /
ChartIndicatorsTotal / ChartIndicatorName are MQL5-language functions
that run inside the terminal process - NOT Python SDK functions).

This module attaches user-deployed `.ex5` indicators by walking the
MT5 main-menu chain `Insert -> Indicators -> Custom -> <indicator_name>`
and posting `WM_COMMAND`. Same pattern as
`mt5_cli/screenshot/screenshot.py::_open_dom_panel`.

Scope (minimal, per user direction):
- `attach(indicator_name, ...)` - attach with DEFAULT parameters
- `detach` / `list_attached` are NOT implemented. They would require
  the MT5 Indicators List dialog (Ctrl+I) introspection - fragile
  across MT5 versions. Users remove indicators via right-click
  "Delete Indicator" or Ctrl+I. Agents verify attachment state via
  `screenshot.take()`.

Bridge isolation: this module never touches the MT5 SDK. Win32 only.
"""
from __future__ import annotations

import time

from mt5_cli.chart._menu import (
    find_leaf_command_id,
    find_submenu,
    normalize_menu_text,
)
from mt5_cli.chart.chart import activate_chart, find_window
from mt5_cli.reports import fail, ok

# Win32 message constants (avoid pulling win32con at module-import time)
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D

# The menu path to a user-deployed custom indicator. Names are
# normalized (lowercased, '&' stripped, whitespace collapsed) before
# comparison so accelerator-key prefixes and label variants do not
# break the walk. See _menu.normalize_menu_text.
_INDICATOR_MENU_PATH: tuple[str, ...] = ("insert", "indicators", "custom")


def attach(
    indicator_name: str,
    *,
    chart_id: int | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    auto_confirm: bool = True,
) -> dict:
    """Attach a deployed `.ex5` indicator to a chart via menu poking.

    Walks MT5's `Insert > Indicators > Custom > <indicator_name>` chain
    and posts WM_COMMAND. MT5 then shows the indicator's parameter
    dialog; with `auto_confirm=True` (default) we post Enter after
    `settle_seconds` to accept default inputs.

    Args:
        indicator_name: Exact name as it appears in MT5's Custom menu.
            For a deployed `MyEMA.ex5` this is `"MyEMA"`. Matching is
            case-insensitive and ignores `&` accelerator markers.
        chart_id: Optional MDI child hwnd. If provided, the chart is
            activated before the menu poke so the indicator lands on
            the right chart. If None, attaches to whichever chart is
            currently active.
        window_substring: MT5 window matcher (default "MT5").
        settle_seconds: Delay between menu activation and the Enter
            post for the parameter dialog.
        auto_confirm: When True (default), post Enter to accept the
            parameter dialog with default inputs. Set False if the
            caller plans to fill the dialog themselves.

    Returns ok({...}) with the menu command id, chart hwnd, and the
    resolved menu path. fail envelope otherwise:
        CHART_WINDOW_NOT_FOUND        no MT5 top-level window matched
        CHART_MENU_NOT_FOUND          MT5 window has no menu bar
        CHART_MENU_PATH_NOT_FOUND     Insert / Indicators / Custom missing
        CHART_INDICATOR_NOT_FOUND     indicator_name not in Custom submenu

    Notes:
        - Default-params only. Custom indicator inputs require dialog
          field-fill, which is out of scope here. Either set defaults
          via MQL5 `input` defaults, or attach manually for one-offs.
        - This is the entire indicator attach surface. There is no
          `detach()` or `list_attached()`; see the module docstring.
    """
    import win32gui  # noqa: PLC0415

    match = find_window(window_substring)
    if not match:
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"No MT5 window matched {window_substring!r}.",
        )

    if chart_id is not None:
        activate_chart(chart_id, match.hwnd, settle_seconds=0)

    menu = win32gui.GetMenu(match.hwnd)
    if not menu:
        return fail(
            "CHART_MENU_NOT_FOUND",
            "MT5 window has no menu bar attached (GetMenu returned 0).",
        )

    cursor = menu
    walked: list[str] = []
    for segment in _INDICATOR_MENU_PATH:
        submenu = find_submenu(cursor, segment)
        if submenu is None:
            return fail(
                "CHART_MENU_PATH_NOT_FOUND",
                f"Could not find {segment.title()!r} submenu while walking "
                f"Insert > Indicators > Custom. Reached: "
                f"{' > '.join(walked) if walked else '(root)'}",
            )
        walked.append(segment.title())
        cursor = submenu

    leaf_lower = normalize_menu_text(indicator_name)
    command_id = find_leaf_command_id(cursor, leaf_lower)
    if command_id is None:
        return fail(
            "CHART_INDICATOR_NOT_FOUND",
            f"Indicator {indicator_name!r} not found in "
            "Insert > Indicators > Custom. Verify it is deployed "
            "(Phase 3: `mt5 indicator deploy <name>`) and the name "
            "matches the .ex5 filename without extension.",
        )

    # Post the menu activation; MT5 will show the parameter dialog.
    win32gui.PostMessage(match.hwnd, WM_COMMAND, command_id, 0)

    if auto_confirm:
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        # Post Enter to the foreground window (the parameter dialog
        # should be topmost at this point). Falling back to the MT5
        # main window if foreground lookup fails.
        try:
            fg = win32gui.GetForegroundWindow()
        except Exception:  # noqa: BLE001
            fg = 0
        target_hwnd = fg or match.hwnd
        win32gui.PostMessage(target_hwnd, WM_KEYDOWN, VK_RETURN, 0)
        time.sleep(0.05)
        win32gui.PostMessage(target_hwnd, WM_KEYUP, VK_RETURN, 0)

    if settle_seconds > 0:
        time.sleep(settle_seconds)

    return ok({
        "indicator_name": indicator_name,
        "command_id": command_id,
        "chart_id": chart_id,
        "parent_hwnd": match.hwnd,
        "menu_path": " > ".join(("Insert", "Indicators", "Custom", indicator_name)),
        "auto_confirmed": bool(auto_confirm),
    })
