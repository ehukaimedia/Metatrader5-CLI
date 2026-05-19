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
from mt5_cli.chart._navigator_walk import (
    Win32NavigatorTreeReader,
    attach_via_navigator,
    find_navigator_panel,
    find_navigator_tree,
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

    # Wave A.1 path: try the Navigator tree first. The Navigator panel
    # is filesystem-aware (reflects MQL5/Experts/ in real time), unlike
    # the Insert > Experts menu which MT5 populates at startup and
    # never refreshes. Newly deployed EAs only show up in Navigator,
    # not the menu — which is why menu-walk-only attach broke for
    # any deploy → attach cycle without an MT5 restart.
    nav_result = _try_navigator_attach(match.hwnd, expert_name)

    if nav_result["ok"]:
        result = nav_result
    elif nav_result["error"]["code"] == "NAV_TREE_NOT_FOUND":
        # Navigator plumbing genuinely unusable — fall back to legacy
        # menu walk so the surface still functions on builds where the
        # Navigator panel structure differs.
        result = _attach_via_menu_legacy(match.hwnd, expert_name)
    else:
        # Any other Navigator error code is AUTHORITATIVE: NAV_EA_NOT_FOUND,
        # NAV_TREE_SELECTION_DRIFT, NAV_POPUP_NOT_FOUND, and
        # NAV_POPUP_OWNERSHIP_MISMATCH each represent a real Navigator-path
        # verdict and must NOT be silently overruled by menu_legacy.
        return nav_result

    # On success, surface the chart_id and run auto-confirm against
    # whatever parameter dialog MT5 raises (both Navigator and menu_legacy
    # paths land us at the EA's inputs dialog with defaults highlighted).
    if result["ok"]:
        result["data"]["chart_id"] = chart_id
        result["data"]["parent_hwnd"] = match.hwnd
        result["data"]["auto_confirmed"] = bool(auto_confirm)
        if auto_confirm:
            _post_enter_to_param_dialog(match.hwnd, settle_seconds)
        if settle_seconds > 0:
            time.sleep(settle_seconds)

    return result


def _try_navigator_attach(main_hwnd: int, expert_name: str) -> dict:
    """Locate Navigator panel + tree, build cross-process reader, attach.

    Returns one of:
      ok({...})                       Navigator path succeeded
      fail(NAV_TREE_NOT_FOUND)        Plumbing absent — caller should
                                      fall back to menu_legacy
      fail(NAV_EA_NOT_FOUND, ...)     Authoritative — do NOT fall back
      fail(NAV_TREE_SELECTION_DRIFT, NAV_POPUP_*, ...) — authoritative
    """
    import win32process  # noqa: PLC0415 (lazy; mocked in tests)

    panel_hwnd = find_navigator_panel(main_hwnd)
    if panel_hwnd is None:
        return fail(
            "NAV_TREE_NOT_FOUND",
            "Navigator panel not found inside MT5 main window. The panel "
            "may be hidden — open View > Navigator (or Ctrl+N).",
        )

    tree_hwnd = find_navigator_tree(panel_hwnd)
    if tree_hwnd is None:
        return fail(
            "NAV_TREE_NOT_FOUND",
            "SysTreeView32 child not found in Navigator panel.",
        )

    try:
        mt5_tid, mt5_pid = win32process.GetWindowThreadProcessId(main_hwnd)
    except Exception as exc:  # noqa: BLE001
        return fail(
            "NAV_TREE_NOT_FOUND",
            f"Could not read MT5 PID/TID from main hwnd: {exc!r}",
        )

    try:
        reader = Win32NavigatorTreeReader(tree_hwnd, mt5_pid)
    except OSError as exc:
        return fail(
            "NAV_TREE_NOT_FOUND",
            f"Could not open MT5 process for cross-process tree reads: {exc!r}",
        )

    try:
        return attach_via_navigator(
            reader=reader,
            tree_hwnd=tree_hwnd,
            ea_name=expert_name,
            mt5_pid=mt5_pid,
            mt5_tid=mt5_tid,
        )
    finally:
        reader.close()


def _attach_via_menu_legacy(main_hwnd: int, expert_name: str) -> dict:
    """Legacy Insert > Experts menu walk (Wave A and before).

    Kept as a fallback for builds where the Navigator panel structure
    differs. Subject to the menu's startup-only refresh limitation —
    won't find EAs deployed since MT5 was launched.
    """
    import win32gui  # noqa: PLC0415

    menu = win32gui.GetMenu(main_hwnd)
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

    leaf_lower = normalize_menu_text(expert_name)
    command_id = find_leaf_command_id_recursive(cursor, leaf_lower)
    if command_id is None:
        return fail(
            "CHART_EA_NOT_FOUND",
            f"Expert Advisor {expert_name!r} not found anywhere under "
            "Insert > Experts. Verify it is deployed "
            "(Phase 3: `mt5 ea deploy <name>`) and the name matches the "
            ".ex5 filename without extension. Note: the Insert > Experts "
            "menu is populated at MT5 startup and does NOT refresh from "
            "disk — restart MT5 if the EA was deployed since launch.",
        )

    win32gui.PostMessage(main_hwnd, WM_COMMAND, command_id, 0)

    return ok({
        "method": "menu_legacy",
        "expert_name": expert_name,
        "command_id": command_id,
        "menu_path": f"Insert > Experts > {expert_name}",
    })


def _post_enter_to_param_dialog(mt5_main_hwnd: int,
                                settle_seconds: float) -> None:
    """Post Enter to whatever dialog MT5 raised after EA activation.

    Both attach paths (Navigator-tree right-click→Enter, menu_legacy
    WM_COMMAND) land us at the EA's parameter dialog. We post Enter to
    the foreground window to accept defaults; fall back to MT5 main if
    foreground lookup fails.
    """
    import win32gui  # noqa: PLC0415

    if settle_seconds > 0:
        time.sleep(settle_seconds)
    try:
        fg = win32gui.GetForegroundWindow()
    except Exception:  # noqa: BLE001
        fg = 0
    target_hwnd = fg or mt5_main_hwnd
    win32gui.PostMessage(target_hwnd, WM_KEYDOWN, VK_RETURN, 0)
    time.sleep(0.05)
    win32gui.PostMessage(target_hwnd, WM_KEYUP, VK_RETURN, 0)
