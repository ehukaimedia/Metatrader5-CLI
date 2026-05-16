"""Transitional placeholder so pytest exits with code 0.

The legacy CLI lives at archive/legacy-mt5/ for cherry-pick reference only.
The new agnostic library at mt5_universal/ is built fresh during Phase 2 of
the implementation plan and brings real tests with it. Until then, this
single test keeps the suite green.

Delete this file when Phase 2 lands any real unit test.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_is_in_refactor_transition() -> None:
    """Legacy code archived; new agnostic library not yet built."""
    assert (REPO_ROOT / "archive" / "legacy-mt5").is_dir(), \
        "Legacy MT5 CLI source must be preserved under archive/legacy-mt5/ as cherry-pick reference."
    assert not (REPO_ROOT / "metatrader5_cli").exists(), \
        "metatrader5_cli/ package should be gone — its contents moved to archive/legacy-mt5/."
    # mt5_universal/ does NOT exist yet — Phase 2 builds it. This intentionally
    # does not assert its absence so this file doesn't need re-editing
    # mid-Phase-2; it self-deletes once any real test lands and pytest is happy.
