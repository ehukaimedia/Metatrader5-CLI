"""Compute a stable hash of the deterministic setup the bot has produced.

The fingerprint pins reviewer verdicts to the exact setup snapshot — without
it, the autopilot executor (phase 2) could re-confirm READY against a
different cousin setup that arrived a few bars later.
"""
from __future__ import annotations

import hashlib
import json


def _round(value, digits: int):
    if value is None:
        return None
    return round(float(value), digits)


def compute(scan: dict) -> str:
    """Return a 16-hex-char fingerprint of the setup defined by `scan`.

    Inputs (must be present unless explicitly optional):
      pair, direction
      setup.{entry, sl, tp}
      poi.{id, top, bottom}                 (optional — None-safe)
      reasoning.structure.last_confirmed_event.{type, level.time}  (optional)
      bar_time
      digits                                (defaults to 5 if not provided)
    """
    digits = int(scan.get("digits") or 5)
    setup = scan.get("setup") or {}
    poi = scan.get("poi") or {}
    reasoning = (scan.get("reasoning") or {}).get("structure") or {}
    last_event = reasoning.get("last_confirmed_event") or {}
    level = last_event.get("level") or {}

    payload = {
        "pair": scan.get("pair"),
        "direction": scan.get("direction"),
        "entry": _round(setup.get("entry"), digits),
        "sl": _round(setup.get("sl"), digits),
        "tp": _round(setup.get("tp"), digits),
        "poi_id": poi.get("id"),
        "poi_top": _round(poi.get("top"), digits),
        "poi_bottom": _round(poi.get("bottom"), digits),
        "event_type": last_event.get("type"),
        "event_time": level.get("time"),
        "bar_time": scan.get("bar_time"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(raw, digest_size=8).hexdigest()
