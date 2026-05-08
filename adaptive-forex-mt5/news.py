"""News-blackout helper for the autopilot executor.

CRITICAL invariant from the spec: when no news provider is wired
(`autopilot.news_source` is None), `is_blackout_active` MUST return True
(fail closed). The operator must wire a source before flipping
`autopilot.enabled` to true. This is enforced in code, not just docs.

Sources are registered at runtime via `register_source(name, fetcher)`.
The fetcher is a callable taking a pair string and returning an iterable
of timezone-aware datetimes representing high-impact event times.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable

# name → fetcher(pair) -> iterable[datetime]
_SOURCES: dict[str, Callable[[str], Iterable[datetime]]] = {}


def register_source(name: str, fetcher: Callable[[str], Iterable[datetime]]) -> None:
    """Plug in a news source. The fetcher is called fresh on every gate
    check, so it can reach over the network or read from a cache."""
    _SOURCES[name] = fetcher


def is_blackout_active(cfg: dict, pair: str) -> bool:
    """True when autopilot must skip placement due to a news-event window.

    Fails closed (returns True) when:
      - cfg.autopilot.news_source is None / missing
      - the configured source name isn't registered
      - the fetcher raises an exception
    """
    ap = cfg.get("autopilot") or {}
    source = ap.get("news_source")
    if source is None:
        return True  # null source — fail closed
    fetcher = _SOURCES.get(source)
    if fetcher is None:
        return True  # configured but not wired — fail closed
    before = float(ap.get("news_blackout_minutes_before", 15)) * 60
    after = float(ap.get("news_blackout_minutes_after", 30)) * 60
    now = datetime.now(timezone.utc)
    try:
        events = fetcher(pair)
    except Exception:
        return True  # fetcher errored — fail closed
    for event_ts in events:
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        delta = (event_ts - now).total_seconds()
        # delta > 0 → event is in the future. Block if within `before` seconds.
        # delta < 0 → event already happened. Block if within `after` seconds.
        if 0 <= delta <= before:
            return True
        if -after <= delta < 0:
            return True
    return False
