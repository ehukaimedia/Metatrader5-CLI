"""Quant campaign package.

Drives the native MT5 Strategy Tester across a symbol x timeframe matrix with
explicit two-pass in-sample/out-of-sample validation, configurable selection
gates, ranked survivors, and a dependency-free report.

Bridge isolation: like ``mt5_cli.tester``, this package MUST NOT import the
MetaTrader5 Python SDK — it composes the filesystem-only tester primitives.
Public campaign/list/get helpers are wired up in ``campaign``/``store`` and
re-exported once those land.
"""
