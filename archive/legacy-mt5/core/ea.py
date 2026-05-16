"""
ea.py - Local MT5 Expert Advisor preset helpers.

This module only edits local preset/source-adjacent files. It does not attach
EAs to charts and does not call MT5 trading APIs.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


EA_FILENAME = "AdaptiveTrailEA.mq5"
DEFAULT_PRESET_FILENAME = "AdaptiveTrailEA.set"
_MAGIC_KEY = "MagicNumbers"
_DEFAULT_MAGICS = [113054]
_TP_RUNNER_DEFAULTS = {
    "Allow_TP_Removal": "false",
    "TP_Removal_Distance_Points": "10",
    "TP_Removal_Require_BE": "true",
}


def _fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "mt5_retcode": None}}


def _repo_experts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "mql5" / "Experts"


def _terminal_candidates() -> list[Path]:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    root = Path(appdata) / "MetaQuotes" / "Terminal"
    if not root.exists():
        return []
    candidates = []
    for child in root.iterdir():
        experts = child / "MQL5" / "Experts"
        if experts.is_dir():
            candidates.append(experts)
    candidates.sort(key=lambda p: (p / EA_FILENAME).exists(), reverse=True)
    return candidates


def resolve_experts_dir(experts_dir: str | None = None) -> Path:
    if experts_dir:
        return Path(experts_dir).expanduser()

    for candidate in _terminal_candidates():
        if (candidate / EA_FILENAME).exists():
            return candidate
    candidates = _terminal_candidates()
    if candidates:
        return candidates[0]
    return _repo_experts_dir()


def parse_magic_values(values: list[str] | tuple[str, ...] | str) -> list[int]:
    if isinstance(values, str):
        raw_items = [values]
    else:
        raw_items = list(values)

    magics: list[int] = []
    for raw in raw_items:
        for token in str(raw).split(","):
            token = token.strip()
            if not token:
                continue
            if not re.fullmatch(r"[+-]?\d+", token):
                raise ValueError(f"Invalid magic number {token!r}.")
            magic = int(token)
            if magic == 0:
                raise ValueError("Magic 0 is reserved for manual trades and is not allowed.")
            if magic not in magics:
                magics.append(magic)

    if not magics:
        raise ValueError("At least one magic number is required.")
    return magics


def parse_symbol_values(values: list[str] | tuple[str, ...] | str) -> list[str]:
    if isinstance(values, str):
        raw_items = [values]
    else:
        raw_items = list(values)

    symbols: list[str] = []
    for raw in raw_items:
        for token in str(raw).split(","):
            symbol = token.strip()
            if not symbol:
                continue
            if symbol not in symbols:
                symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required.")
    return symbols


def _format_magics(magics: list[int]) -> str:
    return ",".join(str(magic) for magic in magics)


def _format_symbols(symbols: list[str]) -> str:
    return ",".join(symbols)


def _extract_set_value(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith(f"{_MAGIC_KEY}="):
        return None
    value = stripped.split("=", 1)[1]
    return value.split("||", 1)[0].strip()


def _set_line_value(lines: list[str], key: str, value: str) -> list[str]:
    line = f"{key}={value}"
    for idx, existing in enumerate(lines):
        if existing.strip().startswith(f"{key}="):
            lines[idx] = line
            return lines
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(line)
    return lines


def _source_default_magics(experts_dir: Path) -> list[int]:
    source_candidates = [experts_dir / EA_FILENAME, _repo_experts_dir() / EA_FILENAME]
    pattern = re.compile(r'input\s+string\s+MagicNumbers\s*=\s*"([^"]*)"')
    for source in source_candidates:
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8", errors="ignore")
        match = pattern.search(text)
        if match:
            try:
                return parse_magic_values(match.group(1))
            except ValueError:
                pass
    return list(_DEFAULT_MAGICS)


def _read_preset_lines(preset_path: Path) -> list[str]:
    if not preset_path.exists():
        return []
    return preset_path.read_text(encoding="utf-16", errors="ignore").splitlines()


def _write_preset_lines(preset_path: Path, lines: list[str]) -> None:
    preset_path.parent.mkdir(parents=True, exist_ok=True)
    preset_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")


def current_magics(*, experts_dir: str | None = None, preset_name: str = DEFAULT_PRESET_FILENAME) -> dict:
    resolved_dir = resolve_experts_dir(experts_dir)
    preset_path = resolved_dir / preset_name
    lines = _read_preset_lines(preset_path)
    for line in lines:
        value = _extract_set_value(line)
        if value is not None:
            try:
                magics = parse_magic_values(value)
            except ValueError as exc:
                return _fail("EA_INVALID_MAGIC", str(exc))
            return {
                "ok": True,
                "data": {
                    "magics": magics,
                    "magic_numbers": _format_magics(magics),
                    "preset_path": str(preset_path),
                    "source": "preset",
                },
            }

    magics = _source_default_magics(resolved_dir)
    return {
        "ok": True,
        "data": {
            "magics": magics,
            "magic_numbers": _format_magics(magics),
            "preset_path": str(preset_path),
            "source": "source_default",
        },
    }


def set_magics(
    magics: list[int],
    *,
    experts_dir: str | None = None,
    preset_name: str = DEFAULT_PRESET_FILENAME,
) -> dict:
    resolved_dir = resolve_experts_dir(experts_dir)
    preset_path = resolved_dir / preset_name
    lines = _read_preset_lines(preset_path)
    lines = _set_line_value(lines, _MAGIC_KEY, _format_magics(magics))

    _write_preset_lines(preset_path, lines)
    return {
        "ok": True,
        "data": {
            "magics": magics,
            "magic_numbers": _format_magics(magics),
            "preset_path": str(preset_path),
            "updated": True,
        },
    }


def add_magics(
    additions: list[int],
    *,
    experts_dir: str | None = None,
    preset_name: str = DEFAULT_PRESET_FILENAME,
) -> dict:
    current = current_magics(experts_dir=experts_dir, preset_name=preset_name)
    if not current["ok"]:
        return current
    magics = list(current["data"]["magics"])
    for magic in additions:
        if magic not in magics:
            magics.append(magic)
    return set_magics(magics, experts_dir=experts_dir, preset_name=preset_name)


def set_tp_runner(
    *,
    enabled: bool,
    distance_points: int | None = None,
    require_be: bool = True,
    experts_dir: str | None = None,
    preset_name: str = DEFAULT_PRESET_FILENAME,
) -> dict:
    if distance_points is not None and distance_points < 0:
        return _fail("EA_INVALID_INPUT", "distance_points must be >= 0.")

    resolved_dir = resolve_experts_dir(experts_dir)
    preset_path = resolved_dir / preset_name
    lines = _read_preset_lines(preset_path)
    lines = _set_line_value(lines, "Allow_TP_Removal", "true" if enabled else "false")
    if distance_points is not None:
        lines = _set_line_value(lines, "TP_Removal_Distance_Points", str(distance_points))
    lines = _set_line_value(lines, "TP_Removal_Require_BE", "true" if require_be else "false")
    _write_preset_lines(preset_path, lines)

    current = current_magics(experts_dir=str(resolved_dir), preset_name=preset_name)
    magics = current["data"]["magics"] if current.get("ok") else []
    return {
        "ok": True,
        "data": {
            "tp_runner_enabled": enabled,
            "tp_removal_distance_points": distance_points,
            "tp_removal_require_be": require_be,
            "magics": magics,
            "preset_path": str(preset_path),
            "updated": True,
        },
    }


def set_manual_magic0(
    *,
    enabled: bool,
    symbols: list[str] | None = None,
    experts_dir: str | None = None,
    preset_name: str = DEFAULT_PRESET_FILENAME,
) -> dict:
    resolved_dir = resolve_experts_dir(experts_dir)
    preset_path = resolved_dir / preset_name
    lines = _read_preset_lines(preset_path)
    lines = _set_line_value(lines, "Allow_Manual_Magic_0", "true" if enabled else "false")
    if symbols is not None:
        lines = _set_line_value(lines, "Manual_Magic_0_Symbols", _format_symbols(symbols))
    _write_preset_lines(preset_path, lines)

    return {
        "ok": True,
        "data": {
            "manual_magic0_enabled": enabled,
            "manual_magic0_symbols": symbols or [],
            "preset_path": str(preset_path),
            "updated": True,
        },
    }


def remove_magics(
    removals: list[int],
    *,
    experts_dir: str | None = None,
    preset_name: str = DEFAULT_PRESET_FILENAME,
) -> dict:
    current = current_magics(experts_dir=experts_dir, preset_name=preset_name)
    if not current["ok"]:
        return current
    magics = [magic for magic in current["data"]["magics"] if magic not in removals]
    if not magics:
        return _fail("EA_INVALID_MAGIC", "Refusing to write an empty MagicNumbers list.")
    return set_magics(magics, experts_dir=experts_dir, preset_name=preset_name)
