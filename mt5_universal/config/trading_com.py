"""Trading.com order-placement settings.

Single-broker scope: the tool currently supports Trading.com only. When
a second broker is added later, refactor through a BrokerProfile ABC at
that time. Do NOT pre-build the abstraction.

Settings here are merged into the standard config loader's defaults so
every primitive that reads cfg picks them up without a separate lookup.
"""

# Trading.com order-placement quirks (from broker spec):
#   - FOK filling only (no IOC, no RETURN on market orders)
#   - No hedging - must close existing same-symbol position before flipping
#   - 22:00 UTC daily rollover spike (spreads widen 10-15x)
TRADING_COM_DEFAULTS: dict = {
    "filling": "FOK",
    "allow_hedging": False,
    "rollover_utc_hour": 22,
}

# Known broker retcodes and human-readable help. Used by orders/positions
# error reporting to give agents actionable explanations.
RETCODE_HELP: dict[int, str] = {
    10004: "Requote - broker rejected because price moved.",
    10006: "Trade request rejected.",
    10008: "Order placed but not filled yet. Poll the fill via 'mt5 order poll-fill <ticket>'.",
    10009: "Order request completed normally.",
    10010: "Only part of the request was completed.",
    10013: "Invalid request.",
    10014: "Invalid volume in the request.",
    10015: "Invalid price in the request.",
    10016: "Invalid stops in the request.",
    10017: "Trade is disabled.",
    10019: "Not enough money to complete the request.",
    10021: "No quotes to process the request.",
    10027: "Algo/autotrading disabled in MT5 terminal UI. Enable Tools > Options > Expert Advisors > Allow algorithmic trading.",
    10030: "Wrong filling mode. Trading.com is FOK-only; pin filling=FOK in your config.",
}


def retcode_help(retcode: int) -> str:
    """Return a human-readable explanation for a known MT5 trade retcode."""
    return RETCODE_HELP.get(retcode, f"Retcode {retcode}: see MT5 docs.")
