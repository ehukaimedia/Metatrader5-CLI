"""Chart-control submodule. Pure Win32; bridge layer is not referenced."""
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
