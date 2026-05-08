"""ntfy.sh push wrapper. ASCII-safe titles/bodies (ntfy strips unicode)."""
from __future__ import annotations

import urllib.request
from typing import Iterable

_UNICODE_FALLBACK = {
    "—": "-", "–": "-", "·": "*", "✗": "X", "✓": "v", "≈": "~", "→": "->",
}


def _ascii_safe(s: str) -> str:
    for k, v in _UNICODE_FALLBACK.items():
        s = s.replace(k, v)
    return s.encode("ascii", "ignore").decode("ascii")


def push(
    *,
    base_url: str,
    topic: str,
    title: str,
    body: str,
    tags: Iterable[str] | None = None,
    priority: int | None = None,
    timeout: float = 5.0,
) -> dict:
    url = f"{base_url.rstrip('/')}/{topic}"
    headers = {
        "Title": _ascii_safe(title),
        "Tags": ",".join(tags or []),
    }
    if priority is not None:
        headers["Priority"] = str(priority)
    req = urllib.request.Request(
        url,
        data=_ascii_safe(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return {"ok": True, "status": r.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}
