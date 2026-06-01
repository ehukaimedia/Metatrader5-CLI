"""Read MT5's alerts.dat file.

The MT5 alert store is a binary file with a stable fixed-record shape in the
Trading.com MT5 build used by this workspace. This module keeps the parser
narrow and fail-fast: if a future terminal build changes the layout,
``list_alerts`` returns a failure envelope instead of guessing.

Read-only by design. The write path (``set``/``delete``) is deferred until the
record layout is round-trip validated against a live terminal — it is preserved
on the ``alert-write-path-deferred`` branch, not shipped here, so the CLI can
never write an unvalidated record into a user's live alerts.dat.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

from mt5_cli.reports import fail, ok

# Phase 6 will centralize MT5 path discovery in config/paths.py. Until then,
# alert reuses the deployer's pure-filesystem terminal-data-dir resolver so we
# don't hand-roll a third hash-dir scanner. Migration = swap this one import.
from mt5_cli.mql5.deployer import resolve_terminal_data_dir

HEADER_COUNT_OFFSET = 0x1AC
RECORDS_OFFSET = 0x1B0
RECORD_SIZE = 1205
SYMBOL_OFFSET = 4
SYMBOL_CHARS = 32
PRICE_OFFSET = 68
SOURCE_OFFSET = 96
SOURCE_CHARS = 256

CODE_TO_CONDITION = {
    0: "Bid >",
    1: "Bid <",
    2: "Ask >",
    3: "Ask <",
}


def list_alerts(
    alerts_path: str | None = None,
    cfg: dict | None = None,
    *,
    data_path: str | None = None,
) -> dict:
    path, resolved_via = _resolve_alerts_path(alerts_path, cfg, data_path)
    if path is None:
        return _unresolved_path_failure()
    loaded = _load_alert_records(path)
    if not loaded.get("ok"):
        return loaded
    records = loaded["data"]["records"]
    return ok(
        {
            "path": str(path),
            "resolved_via": resolved_via,
            "count": len(records),
            "alerts": [_record_payload(i, record) for i, record in enumerate(records)],
        }
    )


def _resolve_alerts_path(
    alerts_path: str | None,
    cfg: dict | None,
    data_path: str | None = None,
) -> tuple[Path | None, str]:
    """Resolve the alerts.dat path and report how it was resolved.

    Returns ``(path, resolved_via)``. The default (no explicit override) is
    discovered from the active MT5 terminal data dir — never a machine-specific
    literal — so the CLI is portable across installs. When ``data_path`` (the
    connected terminal's data dir, threaded from the CLI bridge) is supplied it
    pins the correct install on multi-terminal machines; otherwise the deployer
    falls back to its newest-hash-dir heuristic. ``resolved_via`` is
    ``explicit`` / ``env`` / ``config`` for caller overrides, or the deployer
    resolver's own provenance (``explicit_data_path`` / ``env_var`` /
    ``fallback_newest_hash``) for the discovered default. ``path`` is ``None``
    (``resolved_via`` ``unresolved``) when no terminal data dir can be located.
    """
    if alerts_path:
        return Path(alerts_path), "explicit"
    if os.environ.get("MT5_ALERTS_PATH"):
        return Path(os.environ["MT5_ALERTS_PATH"]), "env"
    if cfg:
        configured = cfg.get("alerts_path") or cfg.get("mt5_alerts_path")
        if configured:
            return Path(configured), "config"
    # The resolver gates candidates on an MQL5/ subdir, not bases/; every real
    # terminal data dir has both. data_path (when present) pins the connected
    # install; otherwise discovery falls back to the newest hash dir.
    data_dir, via = resolve_terminal_data_dir(data_path)
    if data_dir is None:
        return None, "unresolved"
    return data_dir / "bases" / "alerts.dat", via


def _unresolved_path_failure() -> dict:
    return fail(
        "ALERTS_PATH_UNRESOLVED",
        "Could not locate the MT5 terminal data dir. Set MT5_ALERTS_PATH to the "
        "alerts.dat file, set MT5_TERMINAL_DATA_DIR to the terminal data dir, or "
        "run the MT5 terminal at least once.",
    )


def _load_alert_records(path: Path) -> dict:
    if not path.exists():
        return fail("ALERTS_FILE_NOT_FOUND", f"alerts.dat not found: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        return fail("ALERTS_FILE_READ_ERROR", f"Could not read alerts.dat: {exc}")

    if len(data) < RECORDS_OFFSET:
        return fail("ALERTS_FILE_FORMAT", "alerts.dat is too small for the expected MT5 header.")
    count = _read_i32(data, HEADER_COUNT_OFFSET)
    expected_size = RECORDS_OFFSET + (count * RECORD_SIZE)
    if count < 0 or expected_size != len(data):
        return fail(
            "ALERTS_FILE_FORMAT",
            "alerts.dat does not match the expected fixed-record layout.",
            data={"count": count, "size": len(data), "expected_size": expected_size},
        )

    raw_records = [
        data[RECORDS_OFFSET + (i * RECORD_SIZE): RECORDS_OFFSET + ((i + 1) * RECORD_SIZE)]
        for i in range(count)
    ]
    return ok({"path": str(path), "records": raw_records})


def _record_payload(index: int, record: bytes) -> dict:
    code = _read_i32(record, 0)
    price = _read_f64(record, PRICE_OFFSET)
    symbol = _read_fixed_utf16(record, SYMBOL_OFFSET, SYMBOL_CHARS)
    source = _read_fixed_utf16(record, SOURCE_OFFSET, SOURCE_CHARS)
    condition = CODE_TO_CONDITION.get(code, f"UNKNOWN({code})")
    return {
        "id": index,
        "symbol": symbol,
        "condition": condition,
        "price": price,
        "source": source,
        "condition_code": code,
    }


def _read_i32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _read_f64(data: bytes | bytearray, offset: int) -> float:
    return struct.unpack_from("<d", data, offset)[0]


def _read_fixed_utf16(data: bytes | bytearray, offset: int, chars: int) -> str:
    raw = bytes(data[offset:offset + (chars * 2)])
    text = raw.decode("utf-16-le", errors="ignore")
    return text.split("\x00", 1)[0].strip()
