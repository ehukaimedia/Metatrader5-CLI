"""Open a new MT5 chart via the File > New Chart menu chain.

Bridge isolation: pure Win32. Does NOT use the MT5 SDK. If the requested
symbol is not currently in Market Watch, the menu won't list it and
this function returns CHART_SYMBOL_NOT_FOUND_IN_MENU. Add the symbol
to Market Watch first (right-click Market Watch > Symbols, or use
mt5_cli.market.search() to discover what's available).

MT5's `File > New Chart` submenu structure varies by broker. Common
shapes:
- Top-level: a flat list of recently-used / favorite symbols
- Top-level + categories: a few favorites at the top, then nested
  Forex / Indices / Stocks / etc. submenus that hold the rest

The walker recursively searches the entire New Chart subtree (pre-order)
so the symbol is found regardless of which category MT5 has put it in.
"""
from __future__ import annotations

import time

from mt5_cli.chart._menu import (
    find_leaf_command_id_recursive,
    find_submenu,
    normalize_menu_text,
)
from mt5_cli.chart.chart import (
    enumerate_chart_children,
    find_window,
    switch_tf,
)
from mt5_cli.reports import fail, ok

WM_COMMAND = 0x0111


def new_chart(
    symbol: str,
    *,
    timeframe: str | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
) -> dict:
    """Open a new MT5 chart for `symbol` via File > New Chart > <symbol>.

    Args:
        symbol: The instrument (e.g., "USDJPY"). Match is case-insensitive
            and ignores '&' accelerator markers in menu labels.
        timeframe: Optional. When provided, switch_tf() runs on the new
            chart after it settles. Use any of the standard TF strings
            (M1, M5, M15, M30, H1, H4, D1, W1, MN).
        window_substring: MT5 window matcher (default "MT5").
        settle_seconds: Delay after posting WM_COMMAND before enumerating
            children to find the new chart's hwnd, and again before the
            optional TF switch.

    Returns ok({hwnd, symbol, timeframe, parent_hwnd, command_id,
    menu_path}) on success.

    Failure envelopes:
        CHART_WINDOW_NOT_FOUND          no MT5 top-level window matched
        CHART_MENU_NOT_FOUND            MT5 window has no menu bar
        CHART_MENU_PATH_NOT_FOUND       File or New Chart submenu missing
        CHART_SYMBOL_NOT_FOUND_IN_MENU  symbol absent from every New Chart
                                        submenu - add to Market Watch first
        CHART_TIMEFRAME_VERIFY_FAILED   chart opened but switch_tf failed
                                        (returned with partial-success data)
    """
    import win32gui  # noqa: PLC0415 (lazy; mocked in tests via sys.modules)

    symbol_upper = symbol.upper()

    match = find_window(window_substring)
    if not match:
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"No MT5 window matched {window_substring!r}.",
        )

    menu = win32gui.GetMenu(match.hwnd)
    if not menu:
        return fail(
            "CHART_MENU_NOT_FOUND",
            "MT5 window has no menu bar attached (GetMenu returned 0).",
        )

    file_menu = find_submenu(menu, "file")
    if file_menu is None:
        return fail(
            "CHART_MENU_PATH_NOT_FOUND",
            "Could not find 'File' submenu in the MT5 main menu.",
        )

    new_chart_menu = find_submenu(file_menu, "new chart")
    if new_chart_menu is None:
        return fail(
            "CHART_MENU_PATH_NOT_FOUND",
            "Could not find 'New Chart' submenu under 'File'.",
        )

    # Snapshot existing charts before posting, so we can identify the new
    # one by hwnd diff after the menu activation settles.
    try:
        before = {c.hwnd for c in enumerate_chart_children(match.hwnd)}
    except Exception:  # noqa: BLE001
        before = set()

    leaf_lower = normalize_menu_text(symbol_upper)
    command_id = find_leaf_command_id_recursive(new_chart_menu, leaf_lower)
    if command_id is None:
        return fail(
            "CHART_SYMBOL_NOT_FOUND_IN_MENU",
            f"Symbol {symbol_upper!r} not found in File > New Chart submenu "
            "(searched recursively through all category submenus). Add the "
            "symbol to MT5 Market Watch first (right-click Market Watch > "
            "Symbols), or call mt5_cli.market.search() to discover available "
            "symbols.",
        )

    win32gui.PostMessage(match.hwnd, WM_COMMAND, command_id, 0)
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    # Find the newly-opened chart by diffing the child enumeration.
    new_chart_hwnd = None
    try:
        after = enumerate_chart_children(match.hwnd)
    except Exception:  # noqa: BLE001
        after = []
    for chart_window in after:
        if chart_window.hwnd not in before:
            new_chart_hwnd = chart_window.hwnd
            break
    if new_chart_hwnd is None:
        # Fallback: assume the newly active chart is the one we just opened.
        for chart_window in after:
            if chart_window.active:
                new_chart_hwnd = chart_window.hwnd
                break

    base_data = {
        "hwnd": new_chart_hwnd,
        "symbol": symbol_upper,
        "timeframe": None,
        "parent_hwnd": match.hwnd,
        "command_id": command_id,
        "menu_path": f"File > New Chart > {symbol_upper}",
    }

    if timeframe:
        tf_result = switch_tf(
            timeframe,
            window_substring=window_substring,
            settle_seconds=settle_seconds,
            chart_id=new_chart_hwnd,
        )
        if not tf_result.get("ok"):
            # The chart WAS opened; only the TF switch failed. Return as
            # partial success with a warning so the caller can decide.
            base_data["tf_switch_warning"] = tf_result.get("error", {})
            return ok(base_data)
        base_data["timeframe"] = timeframe.upper()

    return ok(base_data)
