"""The quant agent playbook ships and never drifts ahead of the implemented CLI."""
import re
from pathlib import Path

from mt5.cli import _build_command_catalog

DOC = Path("mt5_cli/skills/QUANT_WORKFLOW.md")


def test_playbook_ships_as_package_data():
    assert DOC.exists()
    # pyproject globs *.md under mt5_cli.skills into the wheel
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"mt5_cli.skills" = ["*.md"]' in pyproject


def _catalog_paths() -> dict[str, set[str]]:
    paths: dict[str, set[str]] = {}
    for c in _build_command_catalog()["commands"]:
        flags: set[str] = set()
        for opt in c["options"]:
            flags.update(opt.get("flags", []))
        paths[c["command"]] = flags
    return paths


def _extract(raw: str) -> tuple[str, list[str]]:
    """From a 'mt5 ...' example, take the leading bare words as the command path
    and every --option (dropping the global --json) — ignoring values/placeholders."""
    path_tokens: list[str] = []
    opts: list[str] = []
    seen_non_path = False
    for tok in raw.split():
        if tok == "--json":
            continue
        if tok.startswith("--"):
            seen_non_path = True
            opts.append(tok.split("=", 1)[0])
        elif tok.startswith("<") or tok == "...":
            seen_non_path = True
        elif not seen_non_path:
            path_tokens.append(tok)
    return " ".join(path_tokens), opts


def test_playbook_commands_and_options_resolve_in_describe():
    paths = _catalog_paths()
    text = DOC.read_text(encoding="utf-8")
    examples = re.findall(r"`mt5 ([^`]+)`", text)
    assert examples, "playbook should contain mt5 command examples"
    for raw in examples:
        path, opts = _extract(raw)
        assert path in paths, f"unknown command path {path!r} (from `mt5 {raw}`)"
        for opt in opts:
            assert opt in paths[path], f"command {path!r} has no option {opt!r}"
