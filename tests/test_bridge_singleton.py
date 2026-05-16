"""CI guard: only mt5_cli/bridge/mt5_backend.py may import MetaTrader5.

Uses AST parsing rather than a substring check so legitimate mentions
of "import MetaTrader5" in docstrings or comments are not false
positives (we hit this twice during Phase 2 - the bridge `__init__.py`
docstring and the chart submodule docstring). AST-level detection only
flags actual `import MetaTrader5` / `from MetaTrader5 import ...`
statements.

A secondary regex backstop catches dynamic imports
(`importlib.import_module("MetaTrader5")`, `__import__("MetaTrader5")`)
that AST alone would not flag, because at the AST level those are
function calls with a string argument, not import nodes.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"mt5_cli/bridge/mt5_backend.py"}
SCAN_DIRS = ("mt5_cli", "mt5", "mt5_mcp")


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


# Dynamic imports - importlib.import_module("MetaTrader5") or
# __import__("MetaTrader5") - bypass the AST Import / ImportFrom nodes
# above (at the AST level they are function calls with a string arg).
# This regex backstop catches the common forms, INCLUDING aliased imports:
#   import importlib; importlib.import_module("MetaTrader5")
#   import importlib as il; il.import_module("MetaTrader5")
#   from importlib import import_module; import_module("MetaTrader5")
#   __import__("MetaTrader5")
# Codex P3 #8 noted the original regex missed the "from importlib import
# import_module" + "import importlib as il" forms. The expanded pattern
# now matches the call site (`<anything>.import_module("MetaTrader5")`
# OR a bare `import_module("MetaTrader5")` call) regardless of how the
# name was bound.
_DYNAMIC_IMPORT_RE = re.compile(
    r"""(?:
        (?:[A-Za-z_][A-Za-z0-9_]*\.)?import_module    # qualified or bare import_module(
        \s*\(\s*['"]MetaTrader5['"]
        |
        __import__\s*\(\s*['"]MetaTrader5['"]         # __import__(
    )""",
    re.MULTILINE | re.VERBOSE,
)


def _dynamically_imports_metatrader5(py_path: Path) -> bool:
    try:
        source = py_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_DYNAMIC_IMPORT_RE.search(source))


def test_no_dynamic_metatrader5_imports():
    """Catch importlib.import_module('MetaTrader5') / __import__('MetaTrader5')
    which would bypass the AST scan above."""
    offenders: list[str] = []
    for d in SCAN_DIRS:
        path = ROOT / d
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            rel = py.relative_to(ROOT).as_posix()
            if rel in ALLOWED:
                continue
            if _dynamicallyimports_metatrader5_safe(py):
                offenders.append(rel)
    assert not offenders, (
        "Dynamic MetaTrader5 imports detected (importlib / __import__). "
        f"Offenders: {offenders}"
    )


# Alias to keep the test function readable while still routing through one
# implementation (kept separate so future contributors can extend the regex).
def _dynamicallyimports_metatrader5_safe(py_path: Path) -> bool:
    return _dynamically_imports_metatrader5(py_path)


@pytest.mark.parametrize("source,should_match", [
    # Forms that MUST match (Codex P3 #8 closure)
    ('importlib.import_module("MetaTrader5")', True),
    ("importlib.import_module('MetaTrader5')", True),
    ('__import__("MetaTrader5")', True),
    ("__import__('MetaTrader5')", True),
    ('import importlib as il\nil.import_module("MetaTrader5")', True),
    ('from importlib import import_module\nimport_module("MetaTrader5")', True),
    # Multi-line spacing should still match
    ('importlib.import_module(\n    "MetaTrader5"\n)', True),
    # False positives we must NOT match
    ('# importlib.import_module("MetaTrader5") in a comment', True),  # regex by design matches strings too; AST is the primary guard
    ('importlib.import_module("OtherPackage")', False),
    ('foo.import_module("MetaTrader5_lookalike")', False),
    ('import_module_other("MetaTrader5")', False),
])
def test_dynamic_import_regex_catches_known_forms(source, should_match):
    """Codex P3 #8: verify the expanded backstop catches all dynamic-import
    forms that bypass the AST scan, while not over-matching unrelated calls."""
    assert bool(_DYNAMIC_IMPORT_RE.search(source)) is should_match


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
