"""News-blackout helper. CRITICAL invariant: when autopilot.news_source is
null (no news provider wired), is_blackout_active MUST return True (fail
closed). Otherwise the autopilot would auto-trade across red-news events."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import news


def _cfg(*, source=None, before=15, after=30):
    return {
        "autopilot": {
            "news_source": source,
            "news_blackout_minutes_before": before,
            "news_blackout_minutes_after": after,
        }
    }


def setup_function(_):
    # Reset registry between tests
    news._SOURCES.clear()


def test_null_source_fails_closed():
    """No source wired → blackout always active. Operator must wire one
    before flipping autopilot.enabled."""
    assert news.is_blackout_active(_cfg(source=None), "USDJPY") is True


def test_unregistered_source_fails_closed():
    """Source named in config but not registered → also fail closed."""
    assert news.is_blackout_active(_cfg(source="ghost"), "USDJPY") is True


def test_event_in_blackout_window_blocks():
    now = datetime.now(timezone.utc)
    news.register_source("test", lambda pair: [now + timedelta(minutes=5)])
    assert news.is_blackout_active(_cfg(source="test", before=15), "USDJPY") is True


def test_event_after_window_passes():
    now = datetime.now(timezone.utc)
    news.register_source("test", lambda pair: [now + timedelta(minutes=60)])
    # Event is 60 minutes from now, blackout window before=15. 60 > 15 → safe.
    assert news.is_blackout_active(_cfg(source="test", before=15, after=30), "USDJPY") is False


def test_event_within_after_window_blocks():
    now = datetime.now(timezone.utc)
    news.register_source("test", lambda pair: [now - timedelta(minutes=10)])
    # Event was 10 minutes ago; after=30 means we still avoid for 20 more min.
    assert news.is_blackout_active(_cfg(source="test", after=30), "USDJPY") is True


def test_event_after_after_window_passes():
    now = datetime.now(timezone.utc)
    news.register_source("test", lambda pair: [now - timedelta(minutes=45)])
    assert news.is_blackout_active(_cfg(source="test", after=30), "USDJPY") is False


def test_no_events_for_pair_passes():
    news.register_source("test", lambda pair: [])
    assert news.is_blackout_active(_cfg(source="test"), "USDJPY") is False
