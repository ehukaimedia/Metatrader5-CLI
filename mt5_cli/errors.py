"""Canonical registry of error codes emitted in fail() envelopes.

Every ``error.code`` an agent can receive is listed here with a one-line
description. ``RETRYABLE`` flags codes that are worth retrying after a pause or
a reconnect (the rest are terminal — fix the request, don't retry).

This module is the single source of truth: ``test_errors.py`` asserts the set of
codes here exactly matches the codes actually passed to fail() across the
codebase, so the catalog can never silently drift. ``mt5 describe --json``
exposes it so agents can enumerate the full taxonomy without reading source.
"""
from __future__ import annotations

#: code -> human-readable, one-line description
ERROR_CODES: dict[str, str] = {
    # --- Connection / generic MT5 ---
    "MT5_CONNECTION_ERROR": "Could not connect to the MetaTrader 5 terminal.",
    "MT5_INTERNAL_ERROR": "Unexpected internal error; see message for details.",
    "MT5_INVALID_ARGUMENT": "An argument value was invalid.",
    "MT5_INVALID_PARAMS": "Invalid or missing command parameters.",
    "MT5_INVALID_SYMBOL": "The symbol is unknown or not in Market Watch.",
    "MT5_INVALID_TIMEFRAME": "Unrecognized timeframe string.",
    "MT5_NO_DATA": "The terminal returned no data for the request.",
    "MT5_ORDER_REJECTED": "The broker rejected the order (see error.data.mt5_retcode).",
    "MT5_TICKET_NOT_FOUND": "No order or position with the given ticket.",
    "MT5_MARKET_BOOK_SUBSCRIBE_FAILED": "Could not subscribe to market depth (DOM) for the symbol.",
    "MT5_MARKET_BOOK_UNAVAILABLE": "Market depth (DOM) is unavailable for the symbol.",
    # --- Risk gauntlet / live-trade gate ---
    "RISK_INVALID_INPUT": "A required risk input was missing or invalid.",
    "RISK_LIVE_GATE_BLOCKED": "Live trading not armed (needs cfg.live + MT5_LIVE=1 + --live).",
    "RISK_NO_STOP_LOSS": "Order rejected: a stop loss is required.",
    "RISK_INSUFFICIENT_MARGIN": "Not enough free margin for the order.",
    "RISK_MAX_LOT_EXCEEDED": "Requested volume exceeds the configured max lot.",
    "RISK_MAX_POSITIONS": "Open-position limit reached.",
    "RISK_MAX_DAILY_LOSS": "Daily loss limit reached.",
    "RISK_SPREAD_TOO_WIDE": "Current spread exceeds the configured limit.",
    "RISK_HEDGE_BLOCKED": "Hedging is disabled for this account profile.",
    "RISK_RATE_LIMIT": "Order rate limit exceeded; retry after a short wait.",
    "RISK_STRATEGY_ID_TOO_LONG": "strategy_id exceeds the allowed length.",
    "RISK_SYMBOL_NOT_ALLOWED": "The symbol is not in the allowed-symbols list.",
    # --- Chart UI control ---
    "CHART_WINDOW_NOT_FOUND": "The MT5 main/chart window could not be located.",
    "CHART_ID_NOT_FOUND": "No chart with the given id.",
    "CHART_NO_CHARTS_OPEN": "No charts are open in the terminal.",
    "CHART_ONLY_ONE_OPEN": "Only one chart is open (cannot cycle/close).",
    "CHART_INVALID_TIMEFRAME": "Unrecognized chart timeframe.",
    "CHART_INVALID_DIRECTION": "Invalid cycle direction.",
    "CHART_TOOLBAR_NOT_FOUND": "The chart toolbar was not found.",
    "CHART_TOOLBAR_BUTTON_NOT_FOUND": "A toolbar button was not found.",
    "CHART_MENU_NOT_FOUND": "The expected menu was not found.",
    "CHART_MENU_PATH_NOT_FOUND": "The menu path could not be navigated.",
    "CHART_MENU_ITEM_NOT_FOUND": "A menu item was not found.",
    "CHART_EA_NOT_FOUND": "The Expert Advisor was not found under Insert > Experts.",
    "CHART_INDICATOR_NOT_FOUND": "The indicator was not found under Insert > Indicators.",
    "CHART_SYMBOL_NOT_FOUND_IN_MENU": "The symbol was not found in the symbol menu.",
    "CHART_NEW_CHART_NOT_DETECTED": "A newly opened chart could not be detected.",
    "CHART_NEW_CHART_SNAPSHOT_FAILED": "Could not snapshot chart state for new-chart detection.",
    "CHART_NEW_CHART_VERIFY_FAILED": "New-chart creation could not be verified.",
    "CHART_CLOSE_VERIFY_FAILED": "Chart close could not be verified.",
    "CHART_VERIFY_FAILED": "A chart action could not be verified.",
    "CHART_SYMBOL_VERIFY_FAILED": "The chart symbol change could not be verified.",
    "CHART_TIMEFRAME_VERIFY_FAILED": "The chart timeframe change could not be verified.",
    # --- Navigator tree (EA attach) ---
    "NAV_TREE_NOT_FOUND": "The Navigator panel/tree was not found (open View > Navigator).",
    "NAV_EA_NOT_FOUND": "The EA was not found in the Navigator tree.",
    "NAV_TREE_RECT_ZERO": "The Navigator tree item geometry was unreadable.",
    "NAV_TREE_SELECTION_DRIFT": "The tree selection drifted from the target item.",
    "NAV_POPUP_NOT_FOUND": "The expected Navigator popup was not found.",
    "NAV_POPUP_OWNERSHIP_MISMATCH": "A popup belonged to a different window than expected.",
    # --- MQL5 authoring / deploy ---
    "EA_NOT_FOUND": "No such Expert Advisor source.",
    "INDICATOR_NOT_FOUND": "No such indicator source.",
    "EA_NOT_COMPILED": "The EA .ex5 build is missing; compile first.",
    "INDICATOR_NOT_COMPILED": "The indicator .ex5 build is missing; compile first.",
    "MQL5_COMPILE_FAILED": "MQL5 compilation failed (see message).",
    "MQL5_COMPILE_TIMEOUT": "MQL5 compilation timed out.",
    "METAEDITOR_NOT_FOUND": "metaeditor64.exe could not be located.",
    "SOURCE_NOT_FOUND": "The MQL5 source file was not found.",
    "DEPLOY_TARGET_NOT_WRITABLE": "The deploy target directory is not writable.",
    "NOTHING_TO_DEPLOY": "No matching files to deploy.",
    "ALREADY_EXISTS": "The target file already exists.",
    "UNKNOWN_TEMPLATE": "Unknown scaffold template.",
    # --- Strategy Tester ---
    "TESTER_FAILED": "The Strategy Tester run failed.",
    "TESTER_TIMEOUT": "The tester run timed out.",
    "TESTER_PARSE_ERROR": "Could not parse the tester report.",
    "TESTER_REPORT_MISSING": "The expected tester report was not produced.",
    "INI_NOT_FOUND": "The tester .ini file was not found.",
    "SET_FILE_NOT_FOUND": "The parameter .set file was not found.",
    "RUN_NOT_FOUND": "No tester run with the given id.",
    "UNKNOWN_MODELLING": "Unknown modelling mode.",
    "UNKNOWN_OPT_MODE": "Unknown optimization mode.",
    "STRESS_BASELINE_FAILED": "The ideal-execution baseline run failed; no robustness score is possible.",
    "INVALID_DELAYS": "A delay must be 'random' or an integer 0..600000 ms.",
    # --- Terminal discovery ---
    "TERMINAL_ALREADY_RUNNING": "terminal64.exe is already running; close it for a batch launch.",
    "TERMINAL_NOT_FOUND": "terminal64.exe could not be located.",
    "TERMINAL_DATA_DIR_NOT_FOUND": "The terminal data directory could not be resolved.",
    # --- Alerts ---
    "ALERTS_FILE_NOT_FOUND": "The alerts file was not found.",
    "ALERTS_FILE_FORMAT": "The alerts file had an unexpected format.",
    "ALERTS_FILE_READ_ERROR": "The alerts file could not be read.",
    "ALERTS_PATH_UNRESOLVED": "The alerts file path could not be resolved.",
    # --- Wake alerts ---
    "WAKE_AUDIT_WRITE_FAILED": "The wake audit log could not be written.",
    "WAKE_POLICY_INVALID": "The wake policy configuration is invalid.",
    "WAKE_STATE_READ_ERROR": "The wake dedupe state could not be read.",
    "WAKE_STATE_WRITE_FAILED": "The wake dedupe state could not be written.",
    # --- Screenshot ---
    "SCREENSHOT_WINDOW_NOT_FOUND": "The target window for the screenshot was not found.",
}

#: codes worth retrying (after a pause, reconnect, or transient-state change).
#: Everything else is terminal — fix the request rather than retry.
RETRYABLE: frozenset[str] = frozenset({
    "MT5_CONNECTION_ERROR",
    "MT5_INTERNAL_ERROR",
    "MT5_NO_DATA",
    "RISK_RATE_LIMIT",
    "MT5_MARKET_BOOK_SUBSCRIBE_FAILED",
    "TESTER_TIMEOUT",
    "MQL5_COMPILE_TIMEOUT",
    "TERMINAL_ALREADY_RUNNING",
})


def is_retryable(code: str) -> bool:
    """Return True if an agent should consider retrying after this error."""
    return code in RETRYABLE


def catalog() -> list[dict]:
    """Return the full error taxonomy as a list of {code, description, retryable}."""
    return [
        {"code": code, "description": desc, "retryable": code in RETRYABLE}
        for code, desc in sorted(ERROR_CODES.items())
    ]
