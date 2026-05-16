"""Chart-indicator attach/detach/list primitives.

Gives agents hands to manage user-compiled MQL5 indicators on an MT5
chart. The tool does NOT compute any indicator math; the user's MQL5
(`.ex5`) is the source of all indicator behavior. The tool just:
  - loads the user's compiled indicator via mt5.iCustom(...)
  - attaches the resulting handle to a chart via ChartIndicatorAdd
  - removes attached indicators by name via ChartIndicatorDelete
  - enumerates attached indicators via ChartIndicatorsTotal + ChartIndicatorName

This module DOES talk to the MT5 SDK (via the bridge's mt5_call) -
unlike chart.py which is pure Win32. That's a deliberate split:
chart.py controls the GUI (window/toolbar/menu), this module manages
indicator state through the SDK.

Public surface (re-exported from mt5_cli.chart.__init__):
- attach(chart_id, indicator_name, params=None, sub_window=0)
- detach(chart_id, indicator_short_name, sub_window=0)
- list_attached(chart_id, sub_window=0)
"""
from __future__ import annotations

from mt5_cli.bridge import (
    TIMEFRAME_D1,
    TIMEFRAME_H1,
    TIMEFRAME_H4,
    TIMEFRAME_M1,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_M30,
    TIMEFRAME_MN1,
    TIMEFRAME_W1,
    mt5_call,
)
from mt5_cli.chart.chart import current_title
from mt5_cli.reports import fail, ok

_TF_NAME_TO_CONST = {
    "M1": TIMEFRAME_M1,
    "M5": TIMEFRAME_M5,
    "M15": TIMEFRAME_M15,
    "M30": TIMEFRAME_M30,
    "H1": TIMEFRAME_H1,
    "H4": TIMEFRAME_H4,
    "D1": TIMEFRAME_D1,
    "W1": TIMEFRAME_W1,
    "MN": TIMEFRAME_MN1,
    "MN1": TIMEFRAME_MN1,
}

# MT5 SDK returns -1 for INVALID_HANDLE on iCustom failure.
_INVALID_HANDLE = -1


def attach(
    chart_id: int,
    indicator_name: str,
    params: list | None = None,
    sub_window: int = 0,
    window_substring: str = "MT5",
) -> dict:
    """Attach a user-compiled MQL5 indicator (`.ex5`) to a chart sub-window.

    Workflow:
      1. Look up the chart's symbol + timeframe via current_title(chart_id).
      2. Load the indicator handle via mt5.iCustom(symbol, tf, name, *params).
      3. Attach the handle to the chart via mt5.ChartIndicatorAdd(chart_id, sub_window, handle).

    Returns envelope: ok({handle, chart_id, sub_window, indicator_name}) or
    fail(CHART_INDICATOR_LOAD_FAILED / CHART_INDICATOR_ATTACH_FAILED /
    CHART_INVALID_TIMEFRAME / CHART_ID_NOT_FOUND).
    """
    title_env = current_title(window_substring=window_substring, chart_id=chart_id)
    if not title_env.get("ok"):
        return title_env

    title_data = title_env.get("data", {})
    symbol_name = title_data.get("symbol")
    timeframe_name = title_data.get("timeframe")
    if not symbol_name or not timeframe_name:
        return fail(
            "CHART_INDICATOR_TARGET_UNKNOWN",
            f"Could not resolve symbol/timeframe for chart_id={chart_id}.",
        )

    tf_const = _TF_NAME_TO_CONST.get(timeframe_name.upper())
    if tf_const is None:
        return fail(
            "CHART_INVALID_TIMEFRAME",
            f"Unsupported timeframe for indicator attach: {timeframe_name}",
        )

    args = list(params or [])
    handle = mt5_call("iCustom", symbol_name, tf_const, indicator_name, *args)
    if handle is None or int(handle) == _INVALID_HANDLE:
        return fail(
            "CHART_INDICATOR_LOAD_FAILED",
            f"mt5.iCustom returned invalid handle for indicator '{indicator_name}' "
            f"on {symbol_name},{timeframe_name}. Verify the .ex5 is deployed and "
            "the param signature matches.",
        )

    added = mt5_call("ChartIndicatorAdd", chart_id, sub_window, int(handle))
    if not added:
        return fail(
            "CHART_INDICATOR_ATTACH_FAILED",
            f"mt5.ChartIndicatorAdd returned False for chart_id={chart_id}, "
            f"sub_window={sub_window}, handle={handle}.",
        )

    return ok({
        "handle": int(handle),
        "chart_id": chart_id,
        "sub_window": sub_window,
        "indicator_name": indicator_name,
        "symbol": symbol_name,
        "timeframe": timeframe_name,
    })


def detach(
    chart_id: int,
    indicator_short_name: str,
    sub_window: int = 0,
) -> dict:
    """Remove a named indicator from the chart's sub-window."""
    removed = mt5_call(
        "ChartIndicatorDelete",
        chart_id,
        sub_window,
        indicator_short_name,
    )
    if not removed:
        return fail(
            "CHART_INDICATOR_DETACH_FAILED",
            f"mt5.ChartIndicatorDelete returned False for chart_id={chart_id}, "
            f"sub_window={sub_window}, indicator_short_name='{indicator_short_name}'. "
            "The indicator may not be attached, or the short name may not match.",
        )
    return ok({
        "removed": True,
        "chart_id": chart_id,
        "sub_window": sub_window,
        "indicator_short_name": indicator_short_name,
    })


def list_attached(chart_id: int, sub_window: int = 0) -> dict:
    """Enumerate indicators currently attached to the chart's sub-window."""
    total = mt5_call("ChartIndicatorsTotal", chart_id, sub_window) or 0
    names: list[str] = []
    for idx in range(int(total)):
        name = mt5_call("ChartIndicatorName", chart_id, sub_window, idx)
        if name is not None:
            names.append(str(name))
    return ok({
        "chart_id": chart_id,
        "sub_window": sub_window,
        "indicators": names,
    })
