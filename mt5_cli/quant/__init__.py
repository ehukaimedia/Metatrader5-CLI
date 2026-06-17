"""Quant campaign package.

Drives the native MT5 Strategy Tester across a symbol x timeframe matrix with
explicit two-pass in-sample/out-of-sample validation, configurable selection
gates, ranked survivors, and a dependency-free report.

Bridge isolation: like ``mt5_cli.tester``, this package MUST NOT import the
MetaTrader5 Python SDK — it composes the filesystem-only tester primitives.
"""
from . import campaign
from .store import get_campaign, list_campaigns

__all__ = ["campaign", "get_campaign", "list_campaigns"]
