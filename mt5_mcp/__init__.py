"""mt5_mcp — a Model Context Protocol (MCP) server for metatrader5-cli.

Exposes the read and dry-run surface of the metatrader5-cli library as typed
MCP tools, so any MCP-capable agent (Claude, an LLM tool loop, etc.) can inspect
a running MetaTrader 5 terminal and validate orders over a standard protocol —
without scraping CLI --help text.

Safety by design: this server exposes reads and pre-flight validation only.
Live-money mutations (placing/closing orders, moving stops) are intentionally
NOT exposed here; they remain behind the CLI's explicit triple-lock
(cfg["live"] + MT5_LIVE=1 + --live).

Requires the optional `mcp` dependency: ``pip install metatrader5-cli[mcp]``.
The tool functions themselves import cleanly without `mcp`; only build_server()
and main() need it.
"""
