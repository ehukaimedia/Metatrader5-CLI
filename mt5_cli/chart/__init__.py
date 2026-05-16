"""Chart submodule. Pure Win32 chart UI control; bridge layer not referenced.

The MetaTrader5 Python SDK does NOT expose chart-indicator manipulation
(iCustom / ChartIndicatorAdd / ChartIndicatorDelete / ChartIndicatorsTotal
/ ChartIndicatorName are MQL5-language functions, not Python SDK
functions). The tool's HANDS for indicators end at Phase 3 compile +
deploy; users attach the resulting .ex5 via MT5's Navigator UI and
verify the attachment via screenshot.take().

If programmatic attach becomes a hard requirement later, the Win32 GUI
poking path (see screenshot._open_dom_panel for the pattern) is the
realistic implementation - not the MT5 Python SDK.
"""
from .chart import (
    ChartWindow,
    WindowMatch,
    activate_chart,
    current_title,
    ensure_chart,
    enumerate_chart_children,
    find_window,
    list_charts,
    normalize_timeframe,
    parse_chart_title,
    switch_tf,
    symbol,
    title_has_symbol_tf,
)

__all__ = [
    "ChartWindow",
    "WindowMatch",
    "activate_chart",
    "current_title",
    "ensure_chart",
    "enumerate_chart_children",
    "find_window",
    "list_charts",
    "normalize_timeframe",
    "parse_chart_title",
    "switch_tf",
    "symbol",
    "title_has_symbol_tf",
]
