"""Chart submodule. Pure Win32 chart UI control; bridge layer not referenced.

Four surfaces:
- chart.py: window/MDI/title/toolbar/timeframe primitives + ensure_chart
  (which now opens a new chart via new_chart() when the symbol has none)
  + cycle_chart (MDI tab navigation) + close_chart (WM_CLOSE)
- indicators_attach.py: attach() — Insert > Indicators > Custom > <name>
- attach_ea.py:         attach_ea() — Insert > Experts > <name>
- new_chart.py:         new_chart() — File > New Chart > <symbol>

All three menu-poke modules share Win32 main-menu walking helpers in
the private _menu.py module.

Why menu poking (not the MT5 Python SDK): iCustom / ChartIndicatorAdd /
ChartIndicatorDelete / ChartIndicatorsTotal / ChartIndicatorName, and
the EA attach/detach surface, are all MQL5-language functions that run
inside the terminal process - NOT exposed by the Python SDK (verified
at MetaTrader5 5.0.5260). The GUI menu-poke path is the realistic
alternative.

The shipped surface gives agents what they need to drive MT5's chart
state programmatically:

  Opening    new_chart(symbol, timeframe=...)
  Closing    close_chart(chart_id)
  Cycling    cycle_chart(direction='next'|'prev')
  TF/symbol  switch_tf(tf, chart_id=...) / symbol(name, chart_id=...)
  Ensure     ensure_chart(symbol, timeframe=...) — additive (opens new
             when missing; preserves existing charts)
  Activate   activate_chart(hwnd, parent_hwnd=...)
  Indicators attach(indicator_name, chart_id=...)
  EAs        attach_ea(expert_name, chart_id=...)

Out of scope (logged for future): detach / list_attached for both
indicators and EAs (require fragile Indicators List dialog or
right-click context-menu introspection - users remove via the GUI,
agents verify via screenshot.take()).
"""
from .attach_ea import attach_ea
from .chart import (
    ChartWindow,
    WindowMatch,
    activate_chart,
    close_chart,
    current_title,
    cycle_chart,
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
    "close_chart",
    "current_title",
    "cycle_chart",
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
    "attach_ea",    # Insert > Experts > <name>
    "new_chart",    # File > New Chart > <symbol>
]
