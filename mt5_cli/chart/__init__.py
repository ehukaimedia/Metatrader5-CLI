"""Chart submodule. Pure Win32 chart UI control; bridge layer not referenced.

Three surfaces:
- chart.py: window/MDI/title/toolbar/timeframe primitives via win32gui
- indicators_attach.py: attach a deployed .ex5 indicator to a chart by
  walking the Insert > Indicators > Custom menu and posting WM_COMMAND
- new_chart.py: open a fresh chart for a symbol by walking the
  File > New Chart menu chain (favorites + nested categories)

All three share Win32 main-menu walking helpers in the private
_menu.py module.

Why menu poking (not the MT5 Python SDK): iCustom / ChartIndicatorAdd /
ChartIndicatorDelete / ChartIndicatorsTotal / ChartIndicatorName are
MQL5-language functions that run inside the terminal process - NOT
exposed by the Python SDK (verified at MetaTrader5 5.0.5260). The
first Phase-2.8 implementation called those names through mt5_call();
production calls would AttributeError. The GUI menu-poke path is the
realistic alternative.

attach() is the entire indicator surface here. detach / list_attached
are NOT implemented; both require the MT5 Indicators List dialog
(Ctrl+I) introspection which is fragile across MT5 versions. Users
remove indicators via right-click "Delete Indicator" or Ctrl+I.
Agents verify attachment state via screenshot.take().
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
from .indicators_attach import attach
from .new_chart import new_chart

__all__ = [
    # Window / chart UI primitives
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
    # GUI menu-poke primitives
    "attach",       # Insert > Indicators > Custom > <name>
    "new_chart",    # File > New Chart > <symbol>
]
