"""metatrader5-cli — agent-native control of the MetaTrader 5 terminal.

This is the library layer: account/market/rates/history reads, order and
position management with a live-trade safety gate, chart and screenshot
control, MQL5 scaffold/compile/deploy helpers, and a driver for MT5's native
Strategy Tester. The thin command-line layer lives in the ``mt5`` package and
installs the ``mt5`` console command.

``__version__`` is sourced from the installed package metadata so it always
matches what was installed.
"""
from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("metatrader5-cli")
except _metadata.PackageNotFoundError:  # pragma: no cover - running from a raw checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
