#!/usr/bin/env python3
"""Agent-style integration example for the metatrader5-cli CLI.

This script demonstrates how an LLM agent (or any automation) can drive a
running MetaTrader 5 terminal by *shelling out* to the ``mt5`` console command
and parsing its JSON envelopes.

What it does, in order:
  1. ``mt5 --json status``               - check the terminal connection
  2. ``mt5 --json market info EURUSD``    - read a symbol's quote/metadata
  3. ``mt5 --json order dryrun EURUSD buy --volume 0.01 --sl 1.16``
                                          - validate an order WITHOUT placing it

This example is strictly READ-ONLY / DRY-RUN. The ``order dryrun`` command runs
the same validation an order would go through, but it never sends anything to
the broker, so no live order is ever placed. There are no live-trade gates to
trip here by design.

Requirements:
  * Windows with the ``mt5`` console command on PATH (``pip install metatrader5-cli``).
  * A running, logged-in MetaTrader 5 terminal that ``mt5`` can attach to.
    Without one, ``status`` returns an ``ok: false`` envelope and this script
    reports the error instead of crashing.

Contract recap (see ``mt5 describe --json`` for the full machine catalog):
  * Every ``mt5`` command accepts ``--json`` (in any position), prints a single
    JSON envelope on stdout, and ALWAYS exits 0. Callers branch on the
    envelope's ``ok`` boolean, never on the process exit code.
  * Success: ``{"ok": true, "data": {...}}``
  * Failure: ``{"ok": false, "error": {"code": "...", "message": "...", "data": {...}}}``

Uses only the Python standard library (subprocess, json, sys).

MetaTrader(R) and MT5 are trademarks of MetaQuotes Ltd. This example is part of
an independent project that is not affiliated with or endorsed by MetaQuotes.
"""
from __future__ import annotations

import json
import subprocess
import sys


def run(*args: str) -> dict:
    """Run ``mt5 --json <args...>`` and return the parsed JSON envelope.

    We always inject ``--json`` so the command emits a machine-readable
    envelope, and we capture stdout as text. Because ``mt5`` ALWAYS exits 0,
    we do not inspect the return code; the envelope's ``ok`` field is the
    source of truth.

    Returns the decoded envelope dict. On the rare chance the command could not
    be launched or did not emit valid JSON, we synthesize a failure envelope in
    the same shape so callers can handle everything uniformly.
    """
    try:
        completed = subprocess.run(
            ["mt5", "--json", *args],
            capture_output=True,
            text=True,
            check=False,  # mt5 always exits 0; we read the envelope, not the code
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "error": {
                "code": "MT5_CLI_NOT_FOUND",
                "message": (
                    "The 'mt5' command was not found on PATH. "
                    "Install it with: pip install metatrader5-cli"
                ),
            },
        }

    out = completed.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": {
                "code": "MT5_CLI_BAD_OUTPUT",
                "message": "Could not parse mt5 output as JSON.",
                "data": {"stdout": out, "stderr": completed.stderr.strip()},
            },
        }


def report_error(label: str, envelope: dict) -> None:
    """Print a failed envelope's error in a clear, consistent format."""
    error = envelope.get("error", {})
    code = error.get("code", "UNKNOWN")
    message = error.get("message", "(no message)")
    print(f"[FAIL] {label}: {code} - {message}")
    if "data" in error:
        print(f"       data: {json.dumps(error['data'])}")


def main() -> int:
    # --- Step 1: confirm the terminal is connected -------------------------
    print("1) Checking terminal status ...")
    status = run("status")
    if not status["ok"]:
        report_error("status", status)
        # A terminal connection problem makes the rest pointless, so stop here.
        print("\nCannot continue without a connected MT5 terminal.")
        return 1
    print(f"   [OK] status: {json.dumps(status['data'])}")

    # --- Step 2: read EURUSD market info -----------------------------------
    symbol = "EURUSD"
    print(f"\n2) Fetching market info for {symbol} ...")
    market = run("market", "info", symbol)
    if not market["ok"]:
        report_error(f"market info {symbol}", market)
        # Branch on the specific error code where it helps the caller.
        if market["error"].get("code") == "MT5_INVALID_SYMBOL":
            print(f"       Hint: add {symbol} to Market Watch in the terminal.")
        return 1
    data = market["data"]
    # Print a couple of well-known fields; fall back gracefully if absent.
    bid = data.get("bid")
    ask = data.get("ask")
    print(f"   [OK] {symbol}: bid={bid} ask={ask}")

    # --- Step 3: validate a buy order WITHOUT placing it -------------------
    # 'order dryrun' runs the full order check (margin, stops, risk) and
    # returns what WOULD happen. It never contacts the broker to trade.
    print(f"\n3) Dry-running a {symbol} buy (no order is placed) ...")
    dryrun = run(
        "order", "dryrun", symbol, "buy",
        "--volume", "0.01",
        "--sl", "1.16",
    )
    if not dryrun["ok"]:
        report_error(f"order dryrun {symbol}", dryrun)
        code = dryrun["error"].get("code")
        # A few codes the caller might want to handle distinctly:
        if code == "RISK_NO_STOP_LOSS":
            print("       Hint: provide a stop loss with --sl.")
        elif code == "RISK_INSUFFICIENT_MARGIN":
            print("       Hint: reduce --volume or fund the account.")
        return 1
    print(f"   [OK] dry-run validated: {json.dumps(dryrun['data'])}")

    print("\nDone. All steps were read-only / dry-run; nothing was traded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
