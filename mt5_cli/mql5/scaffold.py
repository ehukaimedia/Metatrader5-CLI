"""Scaffold new MQL5 EAs and indicators from packaged minimal templates.

The tool ships ONE minimal template per asset type. Anything beyond the
minimal skeleton (parameters, calculation, entry/exit logic) is the
user's to author in their own workspace. Locked decision: hands, not
strategies — no scalper / swing / oscillator / overlay variants ship.

Bridge isolation: pure filesystem; never touches the MT5 Python SDK.
"""
from __future__ import annotations

from pathlib import Path

from mt5_cli.reports import fail, ok

_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_EA_TEMPLATE = "ea_minimal.mq5"
_IND_TEMPLATE = "indicator_minimal.mq5"

# The CLI accepts `--template minimal` for forward compatibility, but
# only "minimal" maps to a real template per the locked decision above.
_VALID_TEMPLATES = {"minimal"}


def _scaffold(
    name: str,
    target_dir: Path,
    template_filename: str,
    template: str = "minimal",
) -> dict:
    if template not in _VALID_TEMPLATES:
        return fail(
            "UNKNOWN_TEMPLATE",
            f"Template {template!r} is not available. Valid choices: "
            f"{sorted(_VALID_TEMPLATES)}. The tool ships only minimal "
            "skeletons; strategy logic is yours to author.",
        )
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{name}.mq5"
    if dest.exists():
        return fail(
            "ALREADY_EXISTS",
            f"{dest} already exists; refusing to overwrite.",
        )
    template_path = _TEMPLATE_ROOT / template_filename
    text = template_path.read_text(encoding="utf-8").replace("{{name}}", name)
    dest.write_text(text, encoding="utf-8")
    return ok({"source": str(dest), "template": template})


def list_templates() -> dict[str, list[str]]:
    """Enumerate shipped templates by asset type."""
    return {"ea": [_EA_TEMPLATE], "indicator": [_IND_TEMPLATE]}


def create_ea(
    name: str,
    *,
    target_dir: Path | str = Path("ea"),
    template: str = "minimal",
) -> dict:
    return _scaffold(name, Path(target_dir), _EA_TEMPLATE, template=template)


def create_indicator(
    name: str,
    *,
    target_dir: Path | str = Path("indicators"),
    template: str = "minimal",
) -> dict:
    return _scaffold(name, Path(target_dir), _IND_TEMPLATE, template=template)
