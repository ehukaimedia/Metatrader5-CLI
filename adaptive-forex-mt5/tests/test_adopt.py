"""Phase-3 adopt.py: allowlist loader + validator + expiry filter."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import adopt


def _entry(**overrides):
    base = {
        "ticket": 204841232,
        "symbol": "GBPJPY",
        "account": 9999,
        "mode": "trail_only",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "operator_note": "GBPJPY manual long",
    }
    base.update(overrides)
    return base


def test_load_returns_empty_when_file_missing(tmp_path):
    """Missing allowlist file is the safe default — no adoptions."""
    path = tmp_path / "managed_positions.json"
    assert adopt.load(path) == []


def test_load_parses_valid_entries(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps([_entry(), _entry(ticket=999, symbol="USDJPY")]))
    rows = adopt.load(path)
    assert len(rows) == 2
    assert {r["ticket"] for r in rows} == {204841232, 999}


def test_load_filters_expired(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps([
        _entry(ticket=1),  # not expired
        _entry(ticket=2, expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()),
    ]))
    rows = adopt.load(path)
    assert {r["ticket"] for r in rows} == {1}


def test_load_skips_entries_missing_required_fields(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps([
        {"ticket": 1, "symbol": "GBPJPY"},  # missing account / mode / expiry / note
        _entry(ticket=2),
    ]))
    rows = adopt.load(path)
    assert {r["ticket"] for r in rows} == {2}


def test_load_handles_malformed_json(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text("{not json")
    assert adopt.load(path) == []


def test_load_handles_non_list_root(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps({"ticket": 1}))  # dict, not list
    assert adopt.load(path) == []


def test_adopted_tickets_returns_set_of_ints(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps([_entry(ticket=1), _entry(ticket=2)]))
    tickets = adopt.adopted_tickets(path)
    assert tickets == {1, 2}


def test_lookup_returns_entry_by_ticket(tmp_path):
    path = tmp_path / "managed_positions.json"
    path.write_text(json.dumps([_entry(ticket=1), _entry(ticket=2)]))
    e = adopt.lookup(path, 1)
    assert e and e["ticket"] == 1
    assert adopt.lookup(path, 999) is None


def test_default_path_is_under_adaptive_forex_mt5():
    p = adopt.default_path()
    # Just verify it points at the expected filename next to journal/state
    assert p.name == "managed_positions.json"
