"""Standard JSON envelope returned by every CLI command and library function.

Shape: {"ok": True, "data": {...}} or {"ok": False, "error": {"code": ..., "message": ..., "data": {...}}}
"""
from typing import Any


def ok(data: Any) -> dict:
    return {"ok": True, "data": data}


def fail(code: str, message: str, *, data: dict | None = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"ok": False, "error": err}
