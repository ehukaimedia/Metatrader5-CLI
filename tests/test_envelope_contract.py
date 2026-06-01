"""Golden contract tests for the JSON envelope.

The envelope is the load-bearing promise agents build on. These tests pin its
exact field names and shape so a refactor can't silently change the contract
between releases (the single biggest integration risk for the agentic audience).
If one of these fails, the envelope contract changed — update integrators and
the docs deliberately, do not just bless the new shape.
"""
import json
from datetime import datetime, timezone

from mt5.emit import emit
from mt5_cli.reports import fail, ok


def test_ok_envelope_shape_is_frozen():
    env = ok({"symbol": "EURUSD", "bid": 1.1})
    assert env == {"ok": True, "data": {"symbol": "EURUSD", "bid": 1.1}}
    assert list(env.keys()) == ["ok", "data"]


def test_fail_envelope_shape_is_frozen():
    env = fail("MT5_INVALID_SYMBOL", "Unknown symbol.")
    assert env == {"ok": False, "error": {"code": "MT5_INVALID_SYMBOL", "message": "Unknown symbol."}}
    assert list(env.keys()) == ["ok", "error"]
    assert list(env["error"].keys()) == ["code", "message"]


def test_fail_envelope_with_data_attaches_error_data():
    env = fail("MT5_ORDER_REJECTED", "rejected", data={"mt5_retcode": 10004})
    assert env["ok"] is False
    assert env["error"]["data"] == {"mt5_retcode": 10004}


def test_emit_json_is_valid_json_with_frozen_top_level_keys(capsys):
    emit(ok({"n": 1}), json_mode=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)  # must be a single valid JSON object
    assert set(parsed.keys()) == {"ok", "data"}
    assert parsed["ok"] is True


def test_emit_json_stringifies_non_native_types_deterministically(capsys):
    # datetime is not JSON-native; emit() must serialize it (via default=str)
    # rather than crash, so the envelope contract never breaks on real payloads.
    dt = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    emit(ok({"when": dt}), json_mode=True)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["ok"] is True
    assert isinstance(parsed["data"]["when"], str)
