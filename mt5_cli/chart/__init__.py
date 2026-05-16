"""Chart submodule.

Two layers:
- chart.py: pure Win32 GUI control (no MT5 SDK touch)
- indicators_attach.py: bridge-mediated SDK calls for chart indicators

Together they give agents hands to control MT5 chart state.
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
from .indicators_attach import (
    attach,
    detach,
    list_attached,
)

__all__ = [
    # Win32 primitives
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
    # Indicator attach/detach (bridge-mediated)
    "attach",
    "detach",
    "list_attached",
]
