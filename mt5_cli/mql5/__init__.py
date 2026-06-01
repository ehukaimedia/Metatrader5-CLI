"""MQL5 plugin host: compile, deploy, discover, and scaffold MQL5 sources.

This is the agent-native MQL5 surface — every function returns a standard
envelope (ok / fail) so the CLI and the MCP server can wrap it without
re-interpreting exceptions.

Bridge isolation: this package MUST NOT import MetaTrader5. All MT5
interaction here is via subprocess (metaeditor64.exe) and Win32 paths.
The MetaTrader5 SDK is reserved for mt5_cli/bridge/mt5_backend.py.
"""
from . import compiler, deployer, discovery, scaffold

__all__ = ["compiler", "deployer", "discovery", "scaffold"]
