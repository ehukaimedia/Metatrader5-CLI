"""Campaign id + manifest.json persistence under <root>/<campaign-id>/.

Reuses the tester cache conventions (sortable UTC ids, lazy dir creation).
The timestamp is injectable so the module stays deterministic and testable.
Stdlib-only; no MetaTrader5.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def make_campaign_id(label: str, *, at: str | None = None) -> str:
    """Sortable id: ``YYYY-MM-DDTHH-MM-SS_quant_<label>`` (UTC, filesystem-safe)."""
    stamp = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_quant_{label}"


def campaign_dir(cid: str, *, root: Path | str = "results") -> Path:
    """Return (creating if missing) the directory for a campaign id."""
    p = Path(root) / cid
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_manifest(cid: str, data: dict[str, Any], *, root: Path | str = "results") -> Path:
    path = campaign_dir(cid, root=root) / "manifest.json"
    path.write_text(json.dumps({"campaign_id": cid, "data": data}, indent=2), encoding="utf-8")
    return path


def get_campaign(cid: str, *, root: Path | str = "results") -> dict[str, Any] | None:
    """Return the parsed manifest ({"campaign_id", "data"}) or None if absent."""
    path = Path(root) / cid / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_campaigns(*, root: Path | str = "results") -> list[dict[str, Any]]:
    """Campaign dirs (those with a manifest.json), newest id first."""
    rp = Path(root)
    if not rp.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted((d for d in rp.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True):
        if (d / "manifest.json").exists():
            out.append({"campaign_id": d.name, "path": str(d)})
    return out
