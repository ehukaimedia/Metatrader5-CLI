"""CI guard: only mt5_universal/bridge/mt5_backend.py may import MetaTrader5.

Uses AST parsing rather than a substring check so legitimate mentions
of "import MetaTrader5" in docstrings or comments are not false
positives (we hit this twice during Phase 2 — the bridge `__init__.py`
docstring and the chart submodule docstring). AST-level detection only
flags actual `import MetaTrader5` / `from MetaTrader5 import ...`
statements.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"mt5_universal/bridge/mt5_backend.py"}
SCAN_DIRS = ("mt5_universal", "mt5", "mt5_mcp")


def _imports_metatrader5(py_path: Path) -> bool:
    """Return True iff py_path contains an actual `import MetaTrader5` /
    `from MetaTrader5 import ...` statement (not a docstring mention)."""
    try:
        source = py_path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        tree = ast.parse(source, filename=str(py_path))
    except SyntaxError:
        # Don't mask syntax errors as "no import"; surface them.
        pytest.fail(f"SyntaxError parsing {py_path}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "MetaTrader5" or alias.name.startswith("MetaTrader5."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "MetaTrader5" or (
                node.module and node.module.startswith("MetaTrader5.")
            ):
                return True
    return False


def test_only_bridge_imports_metatrader5():
    offenders: list[str] = []
    for d in SCAN_DIRS:
        path = ROOT / d
        if not path.exists():
            continue  # mt5/ and mt5_mcp/ land in Phase 3 / Phase 5
        for py in path.rglob("*.py"):
            rel = py.relative_to(ROOT).as_posix()
            if rel in ALLOWED:
                continue
            if _imports_metatrader5(py):
                offenders.append(rel)
    assert not offenders, (
        f"Only {sorted(ALLOWED)} may import MetaTrader5. "
        f"Offenders detected: {offenders}"
    )


def test_allowed_files_actually_exist():
    """Sanity: every path in ALLOWED is a real file."""
    for rel in ALLOWED:
        assert (ROOT / rel).exists(), f"ALLOWED path missing on disk: {rel}"


def test_allowed_files_do_import_metatrader5():
    """Sanity: the bridge file itself MUST contain the import,
    otherwise this guard is misconfigured."""
    for rel in ALLOWED:
        path = ROOT / rel
        if not path.exists():
            continue
        assert _imports_metatrader5(path), (
            f"{rel} is on the allow-list but does not import MetaTrader5. "
            "Did the bridge implementation move?"
        )
