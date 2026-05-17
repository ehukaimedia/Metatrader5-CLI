"""Strategy Tester driver: drive MT5's native tester from the CLI.

Composes a tester run from four orthogonal pieces:

- cache.py      : per-run snapshot dirs (./results/<run-id>/)
- ini_builder.py: write the .ini file terminal64.exe /config: needs
- launcher.py   : subprocess wrapper for `terminal64.exe /config:<ini> /portable`
- results.py    : parse the HTML report + journal CSV + optimization XML

Higher-level modes:

- ea.py        : single / optimize / scanner / stress modes for EAs
- indicator.py : visual indicator test

Bridge isolation: this package MUST NOT import MetaTrader5. terminal64.exe
runs in /portable subprocess mode and produces its own artifacts on disk
— the Python SDK bridge is reserved for live runtime control.
"""
from . import cache, ea, indicator, ini_builder, launcher, results

__all__ = ["cache", "ea", "indicator", "ini_builder", "launcher", "results"]
