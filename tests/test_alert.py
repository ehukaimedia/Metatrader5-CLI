import struct
from pathlib import Path


def _write_utf16(buf: bytearray, offset: int, chars: int, value: str) -> None:
    """Write a NUL-padded fixed-width UTF-16-LE field (test scaffold).

    The production module is read-only, so the test builds sample alerts.dat
    records itself rather than importing a write helper.
    """
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
    _write_utf16(record, SOURCE_OFFSET, 256, "alert")
    record[1133] = 5
    record[1137] = 5
    path.write_bytes(bytes(header) + bytes(record))
    return path


def _fake_terminal_root(tmp_path: Path) -> tuple[Path, Path]:
    """Build a fake %APPDATA%\\MetaQuotes\\Terminal root with one install.

    Mirrors the layout the deployer resolver scans: a 32-char hash dir with an
    MQL5/ subdir (the resolver's gate) plus a bases/ subdir holding a valid
    alerts.dat.
    """
    root = tmp_path / "Terminal"
    hash_dir = root / "1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D"
    (hash_dir / "MQL5").mkdir(parents=True)
    bases = hash_dir / "bases"
    bases.mkdir(parents=True)
    _sample_alert_file(bases / "alerts.dat")
    return root, hash_dir


def test_list_alerts_parses_fixed_record_file(tmp_path):
    from mt5_cli.alert import list_alerts

    path = _sample_alert_file(tmp_path / "alerts.dat")
    env = list_alerts(str(path))

    assert env["ok"] is True
    assert env["data"]["count"] == 1
    assert env["data"]["alerts"][0]["symbol"] == "AUDUSD"
    assert env["data"]["alerts"][0]["condition"] == "Bid <"
    assert env["data"]["alerts"][0]["price"] == 0.7186


def test_default_path_discovers_terminal_data_dir(tmp_path, monkeypatch):
    from mt5_cli.alert import list_alerts
    from mt5_cli.mql5 import deployer

    root, hash_dir = _fake_terminal_root(tmp_path)
    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS", [root])
    monkeypatch.delenv("MT5_ALERTS_PATH", raising=False)
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)

    env = list_alerts()

    assert env["ok"] is True
    assert env["data"]["path"] == str(hash_dir / "bases" / "alerts.dat")
    assert env["data"]["resolved_via"] == "fallback_newest_hash"
    assert env["data"]["alerts"][0]["symbol"] == "AUDUSD"


def test_list_alerts_pins_connected_terminal_via_data_path(tmp_path, monkeypatch):
    from mt5_cli.alert import list_alerts

    _root, hash_dir = _fake_terminal_root(tmp_path)
    monkeypatch.delenv("MT5_ALERTS_PATH", raising=False)
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)

    # data_path threaded from the connected terminal pins the exact install,
    # never the newest-mtime guess.
    env = list_alerts(data_path=str(hash_dir))

    assert env["ok"] is True
    assert env["data"]["resolved_via"] == "explicit_data_path"
    assert env["data"]["path"] == str(hash_dir / "bases" / "alerts.dat")


def test_unresolved_terminal_dir_returns_failure_envelope(tmp_path, monkeypatch):
    from mt5_cli.alert import list_alerts
    from mt5_cli.mql5 import deployer

    monkeypatch.setattr(deployer, "_CANDIDATE_DATA_DIRS", [tmp_path / "missing"])
    monkeypatch.delenv("MT5_ALERTS_PATH", raising=False)
    monkeypatch.delenv("MT5_TERMINAL_DATA_DIR", raising=False)

    env = list_alerts()

    assert env["ok"] is False
    assert env["error"]["code"] == "ALERTS_PATH_UNRESOLVED"


def test_alert_module_has_no_hardcoded_user_path():
    import mt5_cli.alert.alert as alert_mod

    src = Path(alert_mod.__file__).read_text(encoding="utf-8")
    assert r"\Users\arsen" not in src
    assert "D0E8209F77C8CF37AD8BF550E51FF075" not in src
