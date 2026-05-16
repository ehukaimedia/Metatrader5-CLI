"""Attach a deployed Expert Advisor (.ex5) to a chart via Win32 GUI menu poke.

Mirror of mt5_cli.chart.attach but for the Insert > Experts menu chain.
The MT5 Python SDK exposes nothing for EA attachment (no ExpertAdd,
ExpertRemove, no per-chart EA state API) - same SDK gap as the chart
indicator surface, same realistic workaround: walk the GUI menu.

Bridge isolation: pure Win32. Never touches the MT5 SDK.

Scope (minimal, per the same user direction that shaped attach()):
- attach_ea(expert_name) - attach with DEFAULT parameters (auto-confirm
  the EA's input dialog). MT5 enforces ONE EA per chart, so attaching a
  new one replaces the previously-attached EA.

NOT shipped:
- detach_ea(chart_id) - would require the Experts > Remove or right-click
  context menu introspection. Users remove via right-click chart > Expert
  Advisors > Remove, or by attaching a different EA which replaces.
- list_attached_ea(chart_id) - the chart title shows the attached EA name
  in some MT5 versions; agents can read it via chart.current_title and
  parse. Programmatic enumeration via GUI is fragile.
"""
from __future__ import annotations

import time

from mt5_cli.chart._menu import (
    find_leaf_command_id_recursive,
    find_submenu,
    normalize_menu_text,
)
from mt5_cli.chart.chart import (
    _format_detected_charts,
    activate_chart,
    enumerate_chart_children,
    find_window,
)
from mt5_cli.reports import fail, ok

# Win32 message constants (avoid pulling win32con at module-import time)
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D

# Menu path to a deployed Expert Advisor. Names are normalized
# (lowercased, '&' stripped, '\t' shortcut suffix dropped, whitespace
# collapsed) before comparison - see _menu.normalize_menu_text.
#
# MT5's "Experts" submenu structure varies. Common shapes:
#   Insert > Experts > <ExpertName>             (top-level favorites)
#   Insert > Experts > Examples > <ExpertName>  (built-in samples)
#   Insert > Experts > Advisors > <ExpertName>  (custom .ex5 from
#                                                MQL5/Experts/Advisors/)
# Recursive walk handles all three.
_EA_MENU_PATH: tuple[str, ...] = ("insert", "experts")


def attach_ea(
    expert_name: str,
    *,
    chart_id: int | None = None,
    window_substring: str = "MT5",
    settle_seconds: float = 0.5,
    auto_confirm: bool = True,
) -> dict:
    """Attach a deployed `.ex5` Expert Advisor to a chart via menu poking.

    Walks MT5's `Insert > Experts > ... > <expert_name>` chain
    (recursively, since EAs may live at the top level or under nested
    category submenus like Examples or Advisors) and posts WM_COMMAND.
    MT5 then shows the EA's parameter dialog; with `auto_confirm=True`
    (default) we post Enter after `settle_seconds` to accept defaults.

    Args:
        expert_name: Exact name as it appears in MT5's Experts menu
            (matches the .ex5 filename without extension). Matching is
            case-insensitive and ignores '&' accelerator markers.
        chart_id: Optional MDI child hwnd. If provided, the chart is
            activated before the menu poke so the EA lands on the right
            chart. If None, attaches to whichever chart is currently
            active.
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
        CHART_MENU_PATH_NOT_FOUND     Insert or Experts submenu missing
        CHART_EA_NOT_FOUND            expert_name not in the Experts
                                      submenu tree

    Notes:
        - MT5 enforces ONE EA per chart. Attaching a new EA replaces
          the previously-attached EA on that chart. There is no error
          if an EA was already attached; the new one wins.
        - Default-params only. For custom inputs, set MQL5 `input`
          defaults in the EA source, or attach manually via the dialog.
    """
    import win32gui  # noqa: PLC0415 (lazy; mocked in tests via sys.modules)

    match = find_window(window_substring)
    if not match:
        return fail(
            "CHART_WINDOW_NOT_FOUND",
            f"No MT5 window matched {window_substring!r}.",
        )

    if chart_id is not None:
        # Verify chart_id is actually an enumerated MDI chart child of
        # this MT5 window BEFORE activating. MDIClient accepts
        # SendMessage(WM_MDIACTIVATE, hwnd, 0) for ANY hwnd without
        # checking parentage and returns success, which makes
        # activate_chart's bool insufficient on its own - a stale or
        # wrong-parent hwnd would pass the bool check, the post-activate
        # WM_COMMAND would fire on the MT5 parent, and MT5 would attach
        # the EA to whichever chart is actually active. That is the exact
        # wrong-chart bug the explicit chart_id arg exists to prevent.
        # Mirror close_chart's enumerate-then-verify pattern.
        try:
            chart_children = enumerate_chart_children(match.hwnd)
        except Exception as exc:  # noqa: BLE001
            return fail(
                "CHART_ID_NOT_FOUND",
                f"Could not enumerate MT5 chart children to verify "
                f"chart_id {chart_id} before EA attach ({exc!r}). "
                "Refusing to post the menu command.",
            )
        if chart_id not in {c.hwnd for c in chart_children}:
            return fail(
                "CHART_ID_NOT_FOUND",
                f"chart_id {chart_id} is not an open MDI child of the "
                f"matched MT5 window. Detected charts: "
                f"{_format_detected_charts(chart_children)}",
            )
        # Even after enumeration confirms the hwnd, activate_chart can
        # still fail at the Win32 layer (e.g., MDIClient SendMessage
        # raises). Keep the bool check as a second gate.
        if not activate_chart(chart_id, match.hwnd, settle_seconds=0):
            return fail(
                "CHART_ID_NOT_FOUND",
                f"Could not activate chart_id {chart_id} before EA attach. "
                "Refusing to post the menu command because the EA could "
                "land on the wrong chart. Verify the hwnd via "
                "list_charts() and retry.",
            )

    menu = win32gui.GetMenu(match.hwnd)
    if not menu:
        return fail(
            "CHART_MENU_NOT_FOUND",
            "MT5 window has no menu bar attached (GetMenu returned 0).",
        )

    cursor = menu
    walked: list[str] = []
    for segment in _EA_MENU_PATH:
        submenu = find_submenu(cursor, segment)
        if submenu is None:
            return fail(
                "CHART_MENU_PATH_NOT_FOUND",
                f"Could not find {segment.title()!r} submenu while walking "
                f"Insert > Experts. Reached: "
                f"{' > '.join(walked) if walked else '(root)'}",
            )
        walked.append(segment.title())
        cursor = submenu

    # Recursive search under "Experts" because EAs may be top-level or
    # nested under Examples / Advisors / other category submenus.
    leaf_lower = normalize_menu_text(expert_name)
    command_id = find_leaf_command_id_recursive(cursor, leaf_lower)
    if command_id is None:
        return fail(
            "CHART_EA_NOT_FOUND",
            f"Expert Advisor {expert_name!r} not found anywhere under "
            "Insert > Experts. Verify it is deployed "
            "(Phase 3: `mt5 ea deploy <name>`) and the name matches the "
            ".ex5 filename without extension.",
        )

    # Post the menu activation; MT5 will show the EA parameter dialog.
    win32gui.PostMessage(match.hwnd, WM_COMMAND, command_id, 0)

    if auto_confirm:
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        # Post Enter to the foreground window (the parameter dialog
        # should be topmost at this point). Fall back to the MT5 main
        # window if foreground lookup fails.
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
        "expert_name": expert_name,
        "command_id": command_id,
        "chart_id": chart_id,
        "parent_hwnd": match.hwnd,
        "menu_path": f"Insert > Experts > {expert_name}",
        "auto_confirmed": bool(auto_confirm),
    })
