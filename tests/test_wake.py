import json
import struct
from datetime import datetime, timezone
from pathlib import Path


def _write_utf16(buf: bytearray, offset: int, chars: int, value: str) -> None:
    encoded = value[: chars - 1].encode("utf-16-le")
    buf[offset:offset + chars * 2] = b"\x00" * (chars * 2)
    buf[offset:offset + len(encoded)] = encoded


def _sample_alert_file(path: Path) -> Path:
    from mt5_cli.alert.alert import (
        HEADER_COUNT_OFFSET,
        PRICE_OFFSET,
        RECORD_SIZE,
        RECORDS_OFFSET,
        SOURCE_OFFSET,
        SYMBOL_OFFSET,
    )

    header = bytearray(RECORDS_OFFSET)
    header[:8] = b"\xf4\x01\x00\x00T\x00\x00\x00"
    struct.pack_into("<i", header, HEADER_COUNT_OFFSET, 1)
    record = bytearray(RECORD_SIZE)
    struct.pack_into("<i", record, 0, 1)
    _write_utf16(record, SYMBOL_OFFSET, 32, "AUDUSD")
    struct.pack_into("<d", record, PRICE_OFFSET, 0.7186)
    _write_utf16(record, SOURCE_OFFSET, 256, "top-down thesis")
    path.write_bytes(bytes(header) + bytes(record))
    return path


def _now() -> datetime:
    return datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def test_watch_alerts_emits_default_notify_wake_and_audit(tmp_path):
    from mt5_cli.wake import watch_alerts

    alerts_path = _sample_alert_file(tmp_path / "alerts.dat")
    audit_path = tmp_path / "wake-audit.jsonl"
    state_path = tmp_path / "wake-state.json"

    env = watch_alerts(
        str(alerts_path),
        cfg={"login": 12345, "server": "Demo"},
        state_path=str(state_path),
        audit_path=str(audit_path),
        now=_now,
    )

    assert env["ok"] is True
    assert env["data"]["schema"] == "wake_watch.v1"
    assert env["data"]["count"] == 1
    event = env["data"]["events"][0]
    assert event["schema"] == "wake.v1"
    assert event["policy_id"] == "default-notify-only"
    assert event["permission_mode"] == "notify_only"
    assert event["account"]["login"] == "***"
    assert event["execution"]["decision"] == "notified"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
    assert audit["schema"] == "wake_audit.v1"
    assert audit["event_id"] == event["event_id"]
    assert state_path.exists()


def test_watch_alerts_dedupe_state_suppresses_replay(tmp_path):
    from mt5_cli.wake import watch_alerts

    alerts_path = _sample_alert_file(tmp_path / "alerts.dat")
    kwargs = {
        "state_path": str(tmp_path / "wake-state.json"),
        "audit_path": str(tmp_path / "wake-audit.jsonl"),
        "now": _now,
    }

    first = watch_alerts(str(alerts_path), **kwargs)
    second = watch_alerts(str(alerts_path), **kwargs)

    assert first["data"]["count"] == 1
    assert second["ok"] is True
    assert second["data"]["count"] == 0
    assert len((tmp_path / "wake-audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_auto_dryrun_policy_calls_order_dryrun(tmp_path):
    from mt5_cli.wake import watch_alerts

    alerts_path = _sample_alert_file(tmp_path / "alerts.dat")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "wake_policies": [
                    {
                        "id": "audusd-breakdown",
                        "match": {"symbol": "AUDUSD", "condition": "Bid <"},
                        "permission_mode": "auto_dryrun",
                        "trade_template": {
                            "action": "place_market",
                            "side": "buy",
                            "volume": 0.01,
                            "sl": 0.7,
                            "tp": 0.73,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def dryrun_stub(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "data": {"dry_run": True, "retcode": 10009}}

    env = watch_alerts(
        str(alerts_path),
        policy_path=str(policy_path),
        state_path=str(tmp_path / "state.json"),
        audit_path=str(tmp_path / "audit.jsonl"),
        dryrun_func=dryrun_stub,
        now=_now,
    )

    assert env["ok"] is True
    event = env["data"]["events"][0]
    assert event["execution"]["decision"] == "dryrun_passed"
    assert captured["symbol"] == "AUDUSD"
    assert captured["side"] == "buy"
    assert captured["order_type"] == "market"
    assert captured["is_live_intent"] is False


def test_policy_max_volume_blocks_before_dryrun(tmp_path):
    from mt5_cli.wake import watch_alerts

    alerts_path = _sample_alert_file(tmp_path / "alerts.dat")
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "wake_policies": [
                    {
                        "id": "too-large",
                        "match": {"symbol": "AUDUSD"},
                        "permission_mode": "auto_dryrun",
                        "limits": {"max_volume": 0.001},
                        "trade_template": {
                            "action": "place_market",
                            "side": "buy",
                            "volume": 0.01,
                            "sl": 0.7,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def dryrun_stub(**kwargs):
        raise AssertionError("dryrun must not run when policy limits block")

    env = watch_alerts(
        str(alerts_path),
        policy_path=str(policy_path),
        state_path=str(tmp_path / "state.json"),
        audit_path=str(tmp_path / "audit.jsonl"),
        dryrun_func=dryrun_stub,
        now=_now,
    )

    event = env["data"]["events"][0]
    assert event["execution"]["decision"] == "policy_blocked"
    assert event["execution"]["dryrun"]["error"]["code"] == "RISK_MAX_LOT_EXCEEDED"


def test_invalid_policy_returns_failure_envelope():
    from mt5_cli.wake import load_policies

    env = load_policies(
        cfg={
            "wake_policies": [
                {
                    "id": "bad",
                    "permission_mode": "auto_dryrun",
                    "trade_template": {"action": "close_position"},
                }
            ]
        }
    )

    assert env["ok"] is False
    assert env["error"]["code"] == "WAKE_POLICY_INVALID"


def test_auto_trade_permission_mode_is_not_supported():
    from mt5_cli.wake import load_policies

    env = load_policies(
        cfg={
            "wake_policies": [
                {
                    "id": "bad-mode",
                    "permission_mode": "auto_trade",
                    "trade_template": {
                        "action": "place_market",
                        "side": "buy",
                        "volume": 0.01,
                        "sl": 0.7,
                    },
                }
            ]
        }
    )

    assert env["ok"] is False
    assert env["error"]["code"] == "WAKE_POLICY_INVALID"


def test_external_wake_adapters_are_not_supported():
    from mt5_cli.wake import load_policies

    env = load_policies(
        cfg={
            "wake_policies": [
                {
                    "id": "bad-adapter",
                    "permission_mode": "notify_only",
                    "adapters": ["audit", "mt5_push"],
                }
            ]
        }
    )

    assert env["ok"] is False
    assert env["error"]["code"] == "WAKE_POLICY_INVALID"


def test_invalid_trade_template_numeric_field_returns_failure_envelope():
    from mt5_cli.wake import load_policies

    env = load_policies(
        cfg={
            "wake_policies": [
                {
                    "id": "bad-volume",
                    "permission_mode": "auto_dryrun",
                    "trade_template": {
                        "action": "place_market",
                        "side": "buy",
                        "volume": "large",
                        "sl": 0.7,
                    },
                }
            ]
        }
    )

    assert env["ok"] is False
    assert env["error"]["code"] == "WAKE_POLICY_INVALID"
