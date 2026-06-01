"""The error registry must stay in lockstep with the codes actually emitted.

This AST-scans every fail("CODE", ...) call across the shipped packages and
asserts the set exactly equals mt5_cli.errors.ERROR_CODES — so a new code can
never ship undocumented, and a removed code can never leave a stale entry.
"""
import ast
from pathlib import Path

import mt5
import mt5_cli
from mt5_cli.errors import ERROR_CODES, RETRYABLE, catalog, is_retryable


def _codes_used_in_fail_calls() -> set[str]:
    roots = [Path(mt5_cli.__file__).parent, Path(mt5.__file__).parent]
    codes: set[str] = set()
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                    if name == "fail" and node.args:
                        a0 = node.args[0]
                        if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                            codes.add(a0.value)
    return codes


def test_registry_exactly_matches_codes_used_in_code():
    used = _codes_used_in_fail_calls()
    registered = set(ERROR_CODES)
    assert used - registered == set(), f"emitted but NOT registered in errors.py: {sorted(used - registered)}"
    assert registered - used == set(), f"registered but unused (stale): {sorted(registered - used)}"


def test_retryable_is_subset_of_registry():
    assert RETRYABLE <= set(ERROR_CODES)


def test_catalog_shape_and_completeness():
    cat = catalog()
    assert len(cat) == len(ERROR_CODES)
    assert set(cat[0]) == {"code", "description", "retryable"}
    assert is_retryable("MT5_CONNECTION_ERROR") is True
    assert is_retryable("MT5_INVALID_SYMBOL") is False
