"""Envelope -> stdout formatter.

Every CLI command produces an envelope dict (ok/fail) from a library
call, then passes it to `emit(envelope, json_mode)` which either:
- prints the envelope as JSON to stdout (json_mode=True; for agents)
- prints a compact human-readable summary (json_mode=False; for shells)

The exit code is ALWAYS 0 - the envelope's `ok` field carries the
success status. This is the contract from spec section 3: agents
parse the envelope, they do not interpret exit codes.
"""
from __future__ import annotations

import json
import sys


def emit(envelope: dict, json_mode: bool) -> None:
    """Write an envelope to stdout in either JSON or human format."""
    if json_mode:
        sys.stdout.write(json.dumps(envelope, default=_json_default))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    # Human-readable summary
    if envelope.get("ok"):
        data = envelope.get("data")
        if data is None:
            print("OK")
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {_render(v)}")
        elif isinstance(data, list):
            if not data:
                print("(empty)")
            else:
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        if i:
                            print("  ---")
                        for k, v in item.items():
                            print(f"  {k}: {_render(v)}")
                    else:
                        print(f"  {_render(item)}")
        else:
            print(_render(data))
    else:
        err = envelope.get("error", {})
        code = err.get("code", "UNKNOWN")
        msg = err.get("message", "(no message)")
        print(f"FAIL [{code}] {msg}", file=sys.stderr)


def _render(value) -> str:
    """Best-effort scalar/list/dict -> string for human output."""
    if isinstance(value, (list, tuple)):
        return ", ".join(_render(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, default=_json_default)
    return str(value)


def _json_default(value):
    """Fallback for non-JSON-native types in envelope payloads."""
    # datetime, Decimal, etc. - just stringify
    return str(value)
